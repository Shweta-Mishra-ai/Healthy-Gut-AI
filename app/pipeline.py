"""Scoring shared by every path that produces or changes an article body:
fresh generation and reviewer edits. Keeping one implementation means an
edited article is held to exactly the same bar as a generated one."""
from app.compliance import scan_article
from app.config import settings
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.schemas import GenerateRequest
from app.seo import build_seo_pack
from app.similarity import check_duplication, duplication_summary


def enrich_article(result: dict, req: GenerateRequest, review_id: str | None = None) -> dict:
    """Everything computed from the finished article, in the order the later
    steps depend on: metrics -> compliance -> quality (which folds the
    compliance penalty in) -> SEO pack -> duplicate scan."""
    article_md = result.get("optimized_article_markdown", "")
    result["metrics"] = {
        "wordCount": len(article_md.split()),
        "readability": readability(article_md, req.language.value),
        "keywordDensity": keyword_density(article_md, req.primary_keyword),
    }
    result["compliance"] = scan_article(article_md, req.language.value)
    result["quality"] = assess_quality(
        result, req.topic, req.primary_keyword, req.article_type.value, req.language.value
    )
    result["seo"] = build_seo_pack(
        result, req.topic, req.primary_keyword, req.geo_target, req.language.value,
        site_url=settings.PUBLIC_SITE_URL,
    )
    # The generated schema_json_ld from the model is a stub at best and
    # invalid at worst; replace it with the graph built from the real article.
    result["schema_json_ld"] = result["seo"]["structured_data"]

    duplication = check_duplication(article_md, req.primary_keyword, exclude_id=review_id)
    duplication["summary"] = duplication_summary(duplication)
    result["duplication"] = duplication
    return result
