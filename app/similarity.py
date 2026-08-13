"""Near-duplicate and keyword-cannibalisation detection.

Two articles on the same keyword compete with each other in search results
instead of ranking — the site splits its own authority between them, and
often neither wins. It is the single most common self-inflicted SEO problem
on content-scaled sites, and it is invisible from inside a single
generation request: each article looks fine on its own.

This compares a freshly generated article against everything already in the
review store and reports (a) bodies that are near-identical and (b) articles
already targeting the same primary keyword. Runs on the same TF-IDF
machinery as app/rag/retriever.py, so it adds no new dependency and no
network call.
"""

import json
import logging
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db import get_connection, get_lock

logger = logging.getLogger("gutfolio.similarity")

# Cosine similarity on TF-IDF unigrams+bigrams. Two independently written
# articles on adjacent gut-health topics typically land around 0.3-0.5
# because they share vocabulary; genuine near-duplicates sit well above 0.7.
NEAR_DUPLICATE_THRESHOLD = 0.72
RELATED_THRESHOLD = 0.45

_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_keyword(kw: str) -> str:
    """"Acid-Reflux, Relief" and "acid reflux relief" are the same keyword as
    far as search competition is concerned, so punctuation and repeated
    whitespace are both collapsed before comparing."""
    return re.sub(r"\s+", " ", _WORD_RE.sub(" ", (kw or "").lower())).strip()


def _load_corpus(exclude_id: str = None) -> list[dict]:
    conn = get_connection()
    with get_lock():
        rows = conn.execute(
            "SELECT id, topic, primary_keyword, status, article_json FROM reviews ORDER BY created_at DESC LIMIT 500"
        ).fetchall()

    corpus = []
    for row in rows:
        if exclude_id and row["id"] == exclude_id:
            continue
        try:
            article = json.loads(row["article_json"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping review %s in similarity scan — article_json unparseable", row["id"])
            continue
        body = article.get("optimized_article_markdown", "") or ""
        if not body.strip():
            continue
        corpus.append({
            "id": row["id"],
            "topic": row["topic"],
            "keyword": row["primary_keyword"],
            "status": row["status"],
            "body": body,
        })
    return corpus


def check_duplication(article_markdown: str, primary_keyword: str, exclude_id: str = None,
                      top_k: int = 3) -> dict:
    """Compares one article against the stored corpus.

    Returns {status, near_duplicates, related, keyword_conflicts}. `status`
    is 'duplicate' when something crosses the near-duplicate threshold,
    'cannibalisation_risk' when another article already targets the same
    keyword, 'clear' otherwise. Never raises — an empty corpus is the normal
    state on a fresh install, not an error.
    """
    body = (article_markdown or "").strip()
    empty = {"status": "clear", "near_duplicates": [], "related": [], "keyword_conflicts": [], "corpus_size": 0}
    if not body:
        return empty

    corpus = _load_corpus(exclude_id)
    if not corpus:
        return empty

    kw_norm = _normalize_keyword(primary_keyword)
    keyword_conflicts = [
        {"id": c["id"], "topic": c["topic"], "keyword": c["keyword"], "status": c["status"]}
        for c in corpus
        if kw_norm and _normalize_keyword(c["keyword"]) == kw_norm
    ][:top_k]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000)
        matrix = vectorizer.fit_transform([c["body"] for c in corpus] + [body])
    except ValueError:
        logger.info("Similarity scan skipped — no usable vocabulary in corpus")
        return {**empty, "corpus_size": len(corpus), "keyword_conflicts": keyword_conflicts}

    scores = cosine_similarity(matrix[-1], matrix[:-1])[0]
    ranked = sorted(zip(scores, corpus), key=lambda pair: pair[0], reverse=True)

    near_duplicates, related = [], []
    for score, c in ranked[:top_k * 2]:
        entry = {
            "id": c["id"], "topic": c["topic"], "keyword": c["keyword"],
            "status": c["status"], "similarity": round(float(score), 4),
        }
        if score >= NEAR_DUPLICATE_THRESHOLD and len(near_duplicates) < top_k:
            near_duplicates.append(entry)
        elif score >= RELATED_THRESHOLD and len(related) < top_k:
            related.append(entry)

    if near_duplicates:
        status = "duplicate"
    elif keyword_conflicts:
        status = "cannibalisation_risk"
    else:
        status = "clear"

    return {
        "status": status,
        "near_duplicates": near_duplicates,
        "related": related,
        "keyword_conflicts": keyword_conflicts,
        "corpus_size": len(corpus),
    }


def duplication_summary(check: dict) -> str:
    """One-line, human-readable verdict for the review queue and the UI."""
    if check["status"] == "duplicate":
        top = check["near_duplicates"][0]
        return (f"Near-duplicate of '{top['topic']}' ({top['similarity']:.0%} similar) — "
                f"publishing both will split their search rankings.")
    if check["status"] == "cannibalisation_risk":
        conflict = check["keyword_conflicts"][0]
        return (f"'{conflict['topic']}' already targets the keyword '{conflict['keyword']}' — "
                f"consider merging, or retarget this article to a different keyword.")
    return "No duplicate or competing article found in the library."
