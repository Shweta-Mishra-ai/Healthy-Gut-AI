"""Programmatic quality assurance for generated articles.

This runs deterministic, verifiable checks against the actual output —
it does not trust the LLM's self-report. Every check here answers a
concrete SEO/content question a real reviewer would ask, so a low score
always comes with a specific, actionable reason.
"""

import re

WORD_TARGETS = {
    "pillar": (2500, 3000),
    "supporting": (1000, 1500),
}

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def assess_quality(result: dict, topic: str, primary_keyword: str, article_type: str) -> dict:
    flags: list[str] = []
    score = 100

    article_md = result.get("optimized_article_markdown", "") or ""
    meta = result.get("meta_description", "") or ""
    slug = result.get("url_slug", "") or ""
    faqs = result.get("faqs", []) or []
    kw = (primary_keyword or "").lower().strip()

    word_count = len(article_md.split())
    target_min, target_max = WORD_TARGETS.get(article_type, WORD_TARGETS["supporting"])
    if word_count < target_min * 0.6:
        flags.append(f"Word count ({word_count}) is far below the {target_min}-{target_max} target for '{article_type}'.")
        score -= 25
    elif word_count < target_min:
        flags.append(f"Word count ({word_count}) is below the {target_min}-{target_max} target for '{article_type}'.")
        score -= 10
    elif word_count > target_max * 1.3:
        flags.append(f"Word count ({word_count}) significantly exceeds the {target_min}-{target_max} target.")
        score -= 5

    if not (110 <= len(meta) <= 165):
        flags.append(f"Meta description is {len(meta)} characters — SEO best practice is ~120-160.")
        score -= 10

    if kw:
        opening = article_md.lower()[:250]
        if kw not in opening:
            flags.append("Primary keyword doesn't appear in the article's opening/title area.")
            score -= 15
        if kw not in meta.lower():
            flags.append("Primary keyword is missing from the meta description.")
            score -= 10

    if slug and not _SLUG_RE.match(slug):
        flags.append(f"URL slug '{slug}' isn't clean lowercase-hyphenated format.")
        score -= 5

    if len(faqs) < 2:
        flags.append(f"Only {len(faqs)} FAQ(s) generated — 2+ recommended for FAQ schema value.")
        score -= 5

    readability = result.get("metrics", {}).get("readability", {}).get("fleschReadingEase")
    if readability is not None:
        if readability < 30:
            flags.append(f"Readability score ({readability}) is very difficult — dense for a general audience.")
            score -= 10
        elif readability > 90:
            flags.append(f"Readability score ({readability}) is unusually simplistic for medical content.")
            score -= 5

    disclaimer_present = any(
        marker in article_md.lower()
        for marker in ("disclaimer", "not a substitute for professional", "consult a")
    )
    if not disclaimer_present:
        flags.append("No medical disclaimer detected in the article body.")
        score -= 15

    score = max(0, min(100, score))
    return {"score": score, "flags": flags, "word_count": word_count}
