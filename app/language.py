"""Script-integrity checks for non-English generations.

Why this exists: the free-tier multilingual models this app falls back to
(Llama 3.3 via Groq/OpenRouter) are reliable at Hindi *most* of the time,
but under load they degrade in a very specific way — they emit tokens from
a different script entirely, usually CJK (Chinese/Japanese/Korean) or
Cyrillic, in the middle of otherwise-fine Devanagari text. Sometimes a
whole section comes back in the wrong script.

Nothing downstream could see that before: `quality.py` measured Devanagari
purity but only *flagged* a low score after the fact, and the article was
still cached, registered for review, and returned to the browser looking
broken. This module makes the contamination a hard, checkable condition at
generation time so a bad response can be rejected and retried against the
next provider (or repaired) instead of being served.

The check is deliberately a script check, not a language check: detecting
"is this really Hindi?" needs a language model, but "does this Hindi
article contain Han characters?" is exact, cheap, and catches the actual
failure mode.
"""

import re
import unicodedata

# Unicode ranges per supported generation language. Keep in sync with the
# Language enum in app/schemas.py.
SCRIPT_RANGES = {
    "hi": [("ऀ", "ॿ")],  # Devanagari
    "en": [("A", "Z"), ("a", "z")],  # Basic Latin letters
}

# Scripts that should never appear in output for any language this app
# supports. Han/Hiragana/Katakana/Hangul are the observed failure mode;
# Cyrillic, Arabic, Hebrew and Thai are included because they fail the
# same way and are just as unreadable to the intended audience.
FOREIGN_SCRIPT_RANGES = (
    ("぀", "ゟ", "Hiragana"),
    ("゠", "ヿ", "Katakana"),
    ("㐀", "䶿", "Han"),
    ("一", "鿿", "Han"),
    ("豈", "﫿", "Han"),
    ("가", "힯", "Hangul"),
    ("ᄀ", "ᇿ", "Hangul"),
    ("Ѐ", "ӿ", "Cyrillic"),
    ("؀", "ۿ", "Arabic"),
    ("֐", "׿", "Hebrew"),
    ("฀", "๿", "Thai"),
)

# Below this share of in-script letters, a non-English article is treated as
# a failed generation rather than a flawed one. Deliberately lower than a
# "good article" bar: technical terms, drug names and the SEO keyword itself
# are legitimately kept in Latin script inside Hindi copy.
MIN_SCRIPT_PURITY = 0.55

# A handful of stray characters can come from a legitimately quoted source
# name. A *systematic* script break shows up as many. Anything at or above
# this count is treated as contamination regardless of overall purity, so a
# long article can't hide a whole bad paragraph behind a good average.
MAX_FOREIGN_CHARS = 3


def _in_any_range(ch: str, ranges) -> bool:
    return any(lo <= ch <= hi for lo, hi in ranges)


def script_purity(text: str, language: str) -> float:
    """Fraction of alphabetic characters that belong to `language`'s script.

    Returns 1.0 when there's nothing to measure (empty text, or text with no
    letters at all) — an empty string is not a script violation.
    """
    ranges = SCRIPT_RANGES.get(language)
    if not ranges or not text:
        return 1.0
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for ch in letters if _in_any_range(ch, ranges)) / len(letters)


def find_foreign_script_chars(text: str) -> dict[str, int]:
    """Counts characters from scripts that should never appear, keyed by
    script name (e.g. {"Han": 14}). Empty dict means the text is clean."""
    found: dict[str, int] = {}
    if not text:
        return found
    for ch in text:
        for lo, hi, name in FOREIGN_SCRIPT_RANGES:
            if lo <= ch <= hi:
                found[name] = found.get(name, 0) + 1
                break
    return found


def strip_foreign_script(text: str) -> str:
    """Removes characters from disallowed scripts, collapsing the whitespace
    they leave behind. Used as a last-resort repair on the mock/fallback path
    only — the primary handling is to reject and regenerate, because deleting
    words silently changes meaning."""
    if not text:
        return text
    cleaned = []
    for ch in text:
        if any(lo <= ch <= hi for lo, hi, _ in FOREIGN_SCRIPT_RANGES):
            continue
        cleaned.append(ch)
    out = "".join(cleaned)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.;:!?।])", r"\1", out)
    return out


def check_language(text: str, language: str) -> dict:
    """Single verdict on whether `text` is usable output for `language`.

    Returns {ok, purity, foreign_scripts, reason}. `ok=False` means the
    generation should be treated as a provider failure, not a quality
    warning — see app/llm_providers.py.
    """
    foreign = find_foreign_script_chars(text)
    foreign_total = sum(foreign.values())
    purity = script_purity(text, language)

    if foreign_total >= MAX_FOREIGN_CHARS:
        scripts = ", ".join(f"{name} x{count}" for name, count in sorted(foreign.items()))
        return {
            "ok": False,
            "purity": round(purity, 4),
            "foreign_scripts": foreign,
            "reason": f"output contains characters from a different writing system ({scripts})",
        }

    if language in SCRIPT_RANGES and language != "en" and purity < MIN_SCRIPT_PURITY:
        return {
            "ok": False,
            "purity": round(purity, 4),
            "foreign_scripts": foreign,
            "reason": (
                f"only {purity:.0%} of letters are in the expected script for '{language}' "
                f"(minimum {MIN_SCRIPT_PURITY:.0%}) — the model answered in the wrong language"
            ),
        }

    return {"ok": True, "purity": round(purity, 4), "foreign_scripts": foreign, "reason": ""}


def describe_char(ch: str) -> str:
    """Human-readable name for a character, for log lines that would
    otherwise print an unrenderable box."""
    try:
        return unicodedata.name(ch)
    except ValueError:
        return f"U+{ord(ch):04X}"
