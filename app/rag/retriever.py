"""Lightweight retrieval-augmented generation (RAG) module.

Uses TF-IDF + cosine similarity rather than neural embeddings deliberately:
for a corpus this size (tens to low hundreds of chunks), TF-IDF gives
comparable relevance ranking to embeddings without requiring a torch/
sentence-transformers install (large, slow on constrained hosts) or a
vector-DB service to run and pay for. If the knowledge base grows into the
thousands of chunks, swap `TfidfVectorizer` here for a real embedding model
+ a vector store (Chroma/pgvector) — the `retrieve()` interface below would
not need to change for callers.
"""

import logging
import threading

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.rag.knowledge_base import KNOWLEDGE_BASE

logger = logging.getLogger("healthy_gut_ai.rag")


class Retriever:
    def __init__(self, corpus: list[dict]):
        self._corpus = corpus
        self._lock = threading.Lock()
        texts = [f"{c['title']}. {c['content']}" for c in corpus]
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self._vectorizer.fit_transform(texts)

    def max_relevance(self, query: str) -> float:
        """Raw top similarity score, with no fallback substitution — used to
        detect when a topic is genuinely outside this tool's specialization
        (gut/digestive health), rather than just retrieving 'something'."""
        query = (query or "").strip()
        if not query:
            return 0.0
        with self._lock:
            query_vec = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._matrix)[0]
        return float(max(scores)) if len(scores) else 0.0

    def retrieve(self, query: str, top_k: int = 3, min_score: float = 0.03) -> list[dict]:
        """Return up to top_k corpus chunks most relevant to `query`,
        each with a similarity score. Falls back to the general gut-health
        chunk if nothing scores above min_score, so callers always get
        *some* grounding context rather than an empty list."""
        query = (query or "").strip()
        if not query:
            return [self._fallback_chunk()]

        with self._lock:
            query_vec = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._matrix)[0]

        ranked = sorted(zip(scores, self._corpus), key=lambda pair: pair[0], reverse=True)
        results = [
            {**chunk, "relevance_score": round(float(score), 4)}
            for score, chunk in ranked[:top_k]
            if score >= min_score
        ]
        if not results:
            logger.info("No chunk scored above min_score for query=%r; using fallback", query)
            return [self._fallback_chunk()]
        return results

    def _fallback_chunk(self) -> dict:
        for chunk in self._corpus:
            if chunk["id"] == "microbiome":
                return {**chunk, "relevance_score": 0.0}
        return {**self._corpus[0], "relevance_score": 0.0}

    def size(self) -> int:
        return len(self._corpus)


retriever = Retriever(KNOWLEDGE_BASE)


def build_rag_context(topic: str, keyword: str, top_k: int = 3) -> tuple[str, list[dict]]:
    """Returns (joined context text for the LLM prompt, list of matched chunks for citation/debug)."""
    query = f"{topic} {keyword}".strip()
    chunks = retriever.retrieve(query, top_k=top_k)
    context_text = " ".join(f"[{c['title']}] {c['content']}" for c in chunks)
    return context_text, chunks


DOMAIN_MIN_SCORE = 0.30

_GUT_HEALTH_TERMS = (
    "gut", "digest", "bowel", "stomach", "intestin", "ibs", "ibd", "celiac", "coeliac",
    "gerd", "reflux", "heartburn", "sibo", "microbiome", "probiotic", "prebiotic",
    "fodmap", "fiber", "fibre", "diarrhea", "diarrhoea", "constipation", "bloat",
    "gastritis", "diverticul", "crohn", "colitis", "lactose", "gluten", "fermented",
    "gastro", "colon", "rectal", "flatulence", "abdominal", "nausea", "ulcer",
)


def is_in_domain(topic: str, keyword: str) -> bool:
    """True if the topic/keyword is plausibly gut/digestive-health related.
    This tool is intentionally scoped to gut health — generating on wildly
    unrelated topics (e.g. 'infectious disease epidemiology') produces
    off-topic, low-trust content rather than a genuinely useful article.

    Uses a hybrid check: an explicit gut-health term allowlist (reliable for
    the common case) plus a high TF-IDF similarity bar as a fallback for
    phrasing the term list doesn't cover. TF-IDF alone on this small a
    corpus over-matches on generic medical words ("disease", "chronic")
    shared across every chunk, so it can't be the only signal.
    """
    combined = f"{topic} {keyword}".lower()
    if any(term in combined for term in _GUT_HEALTH_TERMS):
        return True
    return retriever.max_relevance(combined) >= DOMAIN_MIN_SCORE
