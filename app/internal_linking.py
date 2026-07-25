"""Internal linking suggestions for SEO cluster building.

Surfaces previously APPROVED articles that are topically related to a new
one, so an editor can add internal links during publishing. Deliberately
scoped to approved articles only — suggesting links to drafts that might
still get rejected would be bad practice, and this keeps the feature
consistent with the human-review workflow (app/review.py) rather than
working around it.

Built on the same TF-IDF approach as app/rag/retriever.py, but indexed
dynamically over whatever's in the reviews table at request time (the
corpus here grows with usage, unlike the static knowledge base).
"""

import json
import logging

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db import get_connection, get_lock

logger = logging.getLogger("healthy_gut_ai.internal_linking")

MIN_LINK_SCORE = 0.12


def _load_approved_candidates(exclude_review_id: str = None) -> list[dict]:
    conn = get_connection()
    with get_lock():
        rows = conn.execute(
            "SELECT id, topic, primary_keyword, article_json FROM reviews WHERE status = 'approved'"
        ).fetchall()

    candidates = []
    for row in rows:
        if exclude_review_id and row["id"] == exclude_review_id:
            continue
        try:
            article = json.loads(row["article_json"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping review %s — article_json unparseable", row["id"])
            continue
        meta = article.get("meta_description", "") or ""
        url_slug = article.get("url_slug", "") or ""
        candidates.append({
            "id": row["id"],
            "topic": row["topic"],
            "keyword": row["primary_keyword"],
            "url_slug": url_slug,
            "text": f"{row['topic']} {row['primary_keyword']} {meta}",
        })
    return candidates


def find_related_articles(topic: str, keyword: str, exclude_review_id: str = None, top_k: int = 5) -> list[dict]:
    """Returns up to top_k previously-approved articles related to the given
    topic/keyword, ranked by TF-IDF similarity. Returns an empty list (never
    raises) if there's nothing approved yet to link to — an empty corpus is
    an expected, normal state, not an error."""
    topic = (topic or "").strip()
    keyword = (keyword or "").strip()
    if not topic and not keyword:
        return []

    candidates = _load_approved_candidates(exclude_review_id)
    if not candidates:
        return []

    query = f"{topic} {keyword}".strip()
    texts = [c["text"] for c in candidates] + [query]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # Can happen if every candidate text is empty/whitespace after tokenizing.
        logger.info("TF-IDF vectorization produced no vocabulary for internal linking query %r", query)
        return []

    query_vec = matrix[-1]
    doc_vecs = matrix[:-1]
    scores = cosine_similarity(query_vec, doc_vecs)[0]

    ranked = sorted(zip(scores, candidates), key=lambda pair: pair[0], reverse=True)
    results = []
    for score, c in ranked[:top_k]:
        if score >= MIN_LINK_SCORE:
            results.append({
                "id": c["id"], "topic": c["topic"], "keyword": c["keyword"],
                "url_slug": c["url_slug"], "relevance_score": round(float(score), 4),
            })
    return results
