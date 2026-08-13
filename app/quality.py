"""Programmatic quality assurance for generated articles.

This runs deterministic, verifiable checks against the actual output —
it does not trust the LLM's self-report. Every check here answers a
concrete SEO/content question a real reviewer would ask, so a low score
always comes with a specific, actionable reason.
"""

import re

from app.language import MIN_SCRIPT_PURITY, find_foreign_script_chars, script_purity

WORD_TARGETS = {
    "pillar": (2500, 3000),
    "supporting": (1000, 1500),
}

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# A Hindi article legitimately carries a Devanagari slug (browsers and search
# engines handle the percent-encoded form fine), so the ASCII-only pattern
# flagged every well-formed Hindi URL as malformed. Mixed Devanagari/Latin is
# also normal — the keyword is usually kept in Latin.
_SLUG_RE_DEVANAGARI = re.compile(r"^[a-z0-9\u0900-\u097F]+(-[a-z0-9\u0900-\u097F]+)*$")

# Shared with app/llm_providers.py::_ensure_disclaimer — kept here as the
# single source of truth so the two checks can't drift out of sync (which
# is exactly what happened before: this list was English-only while the
# generation-side safety net already recognized Hindi markers).
DISCLAIMER_MARKERS = (
    "disclaimer", "not a substitute for professional", "consult a", "consult your doctor",
    "अस्वीकरण", "चिकित्सा सलाह",  # Hindi: "disclaimer", "medical advice"
)

# Languages whose script purity is worth reporting on. The ranges themselves,
# and the purity floor, live in app/language.py — that module is the gate that
# rejects a contaminated generation outright, and this is the report on what
# got through, so the two must agree on what "in-script" means.
_LANGUAGE_SCRIPT_RANGES = {"hi": True}
_MIN_SCRIPT_PURITY = MIN_SCRIPT_PURITY


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
        # The keyword-in-body/meta check assumes the keyword is written in the
        # same script as the article. That's true for English content, but for
        # Hindi articles the SEO keyword is almost always kept in English/Latin
        # script on purpose (that's how people actually search), while the
        # article body is written in Devanagari — so this exact-substring check
        # would fail on every single well-written Hindi article and dock 25
        # points for a non-issue. Only enforce it for scripts where a literal
        # substring match is actually meaningful.
        kw_is_latin = bool(re.fullmatch(r"[a-z0-9\s\-']+", kw))
        skip_keyword_check = language in _LANGUAGE_SCRIPT_RANGES and kw_is_latin
        if not skip_keyword_check:
            opening = article_md.lower()[:250]
            if kw not in opening:
                flags.append("Primary keyword doesn't appear in the article's opening/title area.")
                score -= 15
            if kw not in meta.lower():
                flags.append("Primary keyword is missing from the meta description.")
                score -= 10

    slug_pattern = _SLUG_RE_DEVANAGARI if language == "hi" else _SLUG_RE
    if slug and not slug_pattern.match(slug):
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
        purity = script_purity(body_for_check, language)
        if purity < _MIN_SCRIPT_PURITY:
            flags.append(
                f"Requested language was '{language}' but only {purity:.0%} of the article's letters are "
                f"in the expected script — likely mixed-language output. Review before publishing."
            )
            score -= 20

    # A single stray character from an unrelated writing system (Han,
    # Cyrillic, ...) is the visible symptom of a model losing the thread
    # mid-generation. app/language.py rejects the bad response outright at
    # generation time; this catches anything that reached scoring by another
    # path (cached content from an older build, or an imported article).
    foreign = find_foreign_script_chars(article_md)
    if foreign:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(foreign.items()))
        flags.append(f"Article contains characters from another writing system ({detail}) — do not publish as-is.")
        score -= 25

    compliance = result.get("compliance")
    if isinstance(compliance, dict):
        counts = compliance.get("counts", {})
        if counts.get("blocker"):
            flags.append(
                f"{counts['blocker']} compliance blocker(s) found — see the Compliance tab. "
                f"These must be fixed before publishing."
            )
        elif counts.get("warning"):
            flags.append(f"{counts['warning']} compliance warning(s) need an editor's confirmation.")
        score -= compliance.get("score_penalty", 0)

    score = max(0, min(100, score))
    return {"score": score, "flags": flags, "word_count": word_count}
