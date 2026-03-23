from fastapi import APIRouter
from app.services.generator import generate_article
from app.services.optimizer import optimize_article
from app.services.metrics import keyword_density, readability
from app.services.evaluator import evaluate

router = APIRouter()

@router.post("/generate")
def generate(data: dict):
    topic = data.get("topic")
    keyword = data.get("keyword")
    geo = data.get("geo", "India")
    article_type = data.get("type", "supporting")

    draft = generate_article(topic, keyword, article_type)

    optimized = optimize_article(draft, keyword, geo)

    metrics_data = {
        "keyword_density": keyword_density(optimized["optimized_article_markdown"], keyword),
        "readability": readability(optimized["optimized_article_markdown"])
    }

    evaluation = evaluate(optimized["optimized_article_markdown"])

    return {
        "article": optimized,
        "metrics": metrics_data,
        "evaluation": evaluation
    }
