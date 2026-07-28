from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.constants import OUT_OF_SCOPE_MESSAGE
from app.internal_linking import find_related_articles
from app.rag.retriever import is_in_domain, retriever

router = APIRouter()

PILLAR_SECTIONS = [
    ("Overview", 400), ("Causes/Triggers", 450), ("Symptoms", 450),
    ("Diet & Management", 650), ("When to See a Doctor", 300), ("FAQs/Closing", 250),
]
SUPPORTING_SECTIONS = [
    ("Overview", 175), ("Causes/Triggers", 225), ("Symptoms", 225),
    ("Diet & Management", 350), ("When to See a Doctor", 175),
]


@router.get("/internal-links")
def internal_links(topic: str, keyword: str = "", exclude_id: str = "", top_k: int = 5):
    if not (topic or "").strip():
        return JSONResponse(status_code=422, content={"error": "topic parameter cannot be empty or whitespace-only"})
    top_k = max(1, min(top_k, 20))
    results = find_related_articles(topic.strip(), keyword.strip(), exclude_review_id=exclude_id or None, top_k=top_k)
    return {"topic": topic.strip(), "keyword": keyword.strip(), "suggestions": results}


@router.get("/rag/preview")
def rag_preview(topic: str, keyword: str = "", top_k: int = 3):
    """Shows which knowledge-base chunks would be retrieved for a query, with
    similarity scores — useful for demonstrating that retrieval is real
    (ranked by relevance) rather than a hardcoded lookup."""
    if not (topic or "").strip():
        return JSONResponse(status_code=422, content={"error": "topic parameter cannot be empty or whitespace-only"})
    top_k = max(1, min(top_k, 10))
    query = f"{topic.strip()} {keyword.strip()}".strip()
    chunks = retriever.retrieve(query, top_k=top_k)
    return {
        "query": query,
        "corpus_size": retriever.size(),
        "matches": [
            {"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"], "excerpt": c["content"][:160] + "..."}
            for c in chunks
        ],
    }


@router.get("/outline")
def outline_preview(topic: str, keyword: str = "", geo: str = "", article_type: str = "supporting"):
    """Deterministic outline preview — no LLM call, instant and free. Shows
    the section structure, word budget per section, and which knowledge-base
    topics will ground the article, so the user can sanity-check before
    spending a generation on a topic that's out of scope or misconfigured."""
    if not (topic or "").strip():
        return JSONResponse(status_code=422, content={"error": "topic parameter cannot be empty or whitespace-only"})
    in_scope = is_in_domain(topic.strip(), keyword.strip())
    sections = PILLAR_SECTIONS if article_type == "pillar" else SUPPORTING_SECTIONS
    target_min, target_max = (2500, 3000) if article_type == "pillar" else (1000, 1500)
    matches = retriever.retrieve(f"{topic.strip()} {keyword.strip()}".strip(), top_k=3) if in_scope else []

    return {
        "topic": topic.strip(),
        "keyword": keyword.strip(),
        "geo_target": geo.strip(),
        "article_type": article_type,
        "in_scope": in_scope,
        "scope_note": None if in_scope else OUT_OF_SCOPE_MESSAGE,
        "target_word_count": f"{target_min}-{target_max}",
        "planned_sections": [{"heading": h, "target_words": w} for h, w in sections],
        "grounding_sources": [{"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"]} for c in matches],
    }
