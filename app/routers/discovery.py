from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.compliance import scan_article
from app.config import settings
from app.constants import OUT_OF_SCOPE_MESSAGE
from app.internal_linking import find_related_articles
from app.language import check_language
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.rag.retriever import is_in_domain, retriever
from app.schemas import AnalyzeRequest
from app.seo import build_seo_pack
from app.similarity import check_duplication, duplication_summary

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


@router.post("/analyze")
def analyze_existing_article(payload: AnalyzeRequest):
    """Audits an article that already exists — no generation, no provider
    call, no cost.

    This is the same scoring pipeline a generated article goes through
    (metrics, YMYL compliance, quality, SEO pack, duplicate scan), pointed at
    text the caller supplies. It lets an editor check a page that's already
    live, or a draft written by a human, against the same bar as anything
    this app produces.
    """
    article_md = payload.article_markdown
    language = payload.language.value
    topic = payload.topic or (article_md.strip().splitlines()[0].lstrip("# ").strip()[:200] if article_md.strip() else "")

    result = {"optimized_article_markdown": article_md, "meta_description": "", "faqs": []}
    result["metrics"] = {
        "wordCount": len(article_md.split()),
        "readability": readability(article_md, language),
        "keywordDensity": keyword_density(article_md, payload.primary_keyword),
    }
    result["compliance"] = scan_article(article_md, language)
    quality = assess_quality(result, topic, payload.primary_keyword, payload.article_type.value, language)
    seo = build_seo_pack(result, topic, payload.primary_keyword, payload.geo_target, language,
                         site_url=settings.PUBLIC_SITE_URL)
    duplication = check_duplication(article_md, payload.primary_keyword)
    duplication["summary"] = duplication_summary(duplication)

    return {
        "topic": topic,
        "language": language,
        "language_check": check_language(article_md, language),
        "metrics": result["metrics"],
        "compliance": result["compliance"],
        "quality": quality,
        "seo": seo,
        "duplication": duplication,
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
