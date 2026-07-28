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

# Shared with app/llm_providers.py::_ensure_disclaimer — kept here as the
# single source of truth so the two checks can't drift out of sync (which
# is exactly what happened before: this list was English-only while the
# generation-side safety net already recognized Hindi markers).
DISCLAIMER_MARKERS = (
    "disclaimer", "not a substitute for professional", "consult a", "consult your doctor",
    "अस्वीकरण", "चिकित्सा सलाह",  # Hindi: "disclaimer", "medical advice"
)

# Unicode block ranges used to measure script purity for non-English languages.
# Only Hindi is supported as a generation language today (see app/schemas.py
# Language enum) — extend this dict if more languages are added.
_LANGUAGE_SCRIPT_RANGES = {
    "hi": ("\u0900", "\u097F"),  # Devanagari
}
_MIN_SCRIPT_PURITY = 0.5


def _script_purity(text: str, lo: str, hi: str) -> float:
    """Fraction of alphabetic characters falling inside the target script's
    Unicode range. Returns 1.0 for empty/no-letter text (nothing to flag)."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 1.0
    in_script = sum(1 for ch in letters if lo <= ch <= hi)
    return in_script / len(letters)


def assess_quality(result: dict, topic: str, primary_keyword: str, article_type: str, language: str = "en") -> dict:
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

    variants = result.get("meta_description_variants", []) or []
    if len(variants) < 2:
        flags.append(f"Only {len(variants)} meta description variant(s) available — 2-3 recommended for A/B testing.")
        score -= 5
    else:
        bad_length = [v for v in variants if not (100 <= len(v) <= 170)]
        if bad_length:
            flags.append(f"{len(bad_length)} of {len(variants)} meta description variants are outside the ~120-160 character range.")
            score -= 3

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

    disclaimer_present = any(marker in article_md.lower() for marker in DISCLAIMER_MARKERS)
    if not disclaimer_present:
        flags.append("No medical disclaimer detected in the article body.")
        score -= 15

    if language in _LANGUAGE_SCRIPT_RANGES:
        # Exclude the auto-appended sources/references section — citation
        # titles are expected to keep English proper nouns even in a
        # non-English article, and shouldn't count against language purity.
        body_for_check = re.split(r"##\s*(Sources Referenced|संदर्भित स्रोत|References)", article_md)[0]
        lo, hi = _LANGUAGE_SCRIPT_RANGES[language]
        purity = _script_purity(body_for_check, lo, hi)
        if purity < _MIN_SCRIPT_PURITY:
            flags.append(
                f"Requested language was '{language}' but only {purity:.0%} of the article's letters are "
                f"in the expected script — likely mixed-language output from the LLM. Review before publishing."
            )
            score -= 20

    score = max(0, min(100, score))
    return {"score": score, "flags": flags, "word_count": word_count}
