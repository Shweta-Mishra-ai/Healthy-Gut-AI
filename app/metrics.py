import re


def _phrase_pattern(phrase: str) -> re.Pattern:
    """Whole-word match for a (possibly multi-word) keyword. A plain substring
    count found "gas" three times in "Gastritis and gastroenteritis ... vegas"
    and "ibs" in "ribs"."""
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", re.IGNORECASE)


def count_phrase(text: str, phrase: str) -> int:
    phrase = (phrase or "").strip()
    if not phrase or not text:
        return 0
    return len(_phrase_pattern(phrase).findall(text))


def contains_phrase(text: str, phrase: str) -> bool:
    return count_phrase(text, phrase) > 0


def keyword_density(text: str, kw: str) -> dict:
    if not text or not text.strip():
        return {"totalWords": 0, "keywordCount": 0, "keywordDensityPercent": 0.0}
    words = re.findall(r"\S+", text.lower())
    total = len(words) or 1
    kw_clean = re.sub(r"\s+", " ", (kw or "").lower().strip())
    if not kw_clean:
        return {"totalWords": total, "keywordCount": 0, "keywordDensityPercent": 0.0}
    # Whole occurrences of the full keyword phrase (multi-word keywords like
    # "IBS diet" included), not substrings inside other words.
    count = count_phrase(text, kw_clean)
    kw_word_count = len(kw_clean.split()) or 1
    density = round((count * kw_word_count) / total * 100, 2)
    return {
        "totalWords": total,
        "keywordCount": count,
        "keywordDensityPercent": density,
    }


def count_syllables(word: str) -> int:
    return len(re.findall(r"[aeiouy]+", word.lower())) or 1


_SENTENCE_END_RE = re.compile(r"[.!?।॥]")  # includes Devanagari danda/double-danda


_MD_PREFIX_RE = re.compile(r"^(#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)")
_ENDS_SENTENCE_RE = re.compile(r"[.!?।॥:;]$")


def _prose_for_readability(text: str) -> str:
    """Markdown reduced to sentences. Headings, list items and table rows have
    no full stop, so the raw text counted a whole bullet list as one sentence:
    twenty short, simple bullets scored -61 ("very difficult") while the same
    words as prose scored 92. Each block element now ends its own sentence,
    tables and rules are dropped, and link/emphasis syntax is removed."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("|") or re.fullmatch(r"[-*_]{3,}", s):
            continue
        s = _MD_PREFIX_RE.sub("", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
        s = re.sub(r"https?://\S+", "", s)
        s = re.sub(r"[*_`]", "", s).strip()
        if not s:
            continue
        if not _ENDS_SENTENCE_RE.search(s):
            s += "."
        out.append(s)
    return " ".join(out)


def readability(text: str, language: str = "en") -> dict:
    if not text or not text.strip():
        return {
            "fleschReadingEase": 0.0, "gunningFogIndex": 0.0, "avgSentenceLength": 0.0,
            "gradeLevel": "n/a", "note": "empty text",
        }
    text = _prose_for_readability(text)
    words = re.findall(r"\S+", text)
    nw = len(words) or 1
    sentences = len(_SENTENCE_END_RE.findall(text)) or 1
    avg_sentence_length = round(nw / sentences, 2)

    if language != "en":
        # Flesch Reading Ease and Gunning Fog are both calibrated on English
        # syllable-per-word and word-per-sentence norms via a vowel-cluster
        # syllable heuristic ([aeiouy]+) that only matches Latin vowels. On
        # Devanagari text that heuristic silently returns "1 syllable" for
        # every single word regardless of actual complexity, which used to
        # produce nonsense scores (e.g. -180, "very difficult, specialist
        # level" on a perfectly simple sentence) and a false quality-score
        # penalty on every Hindi article. Rather than report a wrong number,
        # only the (now correctly Devanagari-aware) sentence length is given.
        return {
            "fleschReadingEase": None,
            "gunningFogIndex": None,
            "avgSentenceLength": avg_sentence_length,
            "gradeLevel": "n/a",
            "note": "English-calibrated readability formulas don't apply to this language.",
        }

    syllables = sum(count_syllables(w) for w in words) or nw
    flesch = round(206.835 - 1.015 * (nw / sentences) - 84.6 * (syllables / nw), 2)
    flesch = max(-200.0, min(206.835, flesch))

    complex_words = sum(1 for w in words if count_syllables(w) >= 3)
    gunning_fog = round(0.4 * (avg_sentence_length + 100 * (complex_words / nw)), 2)

    if flesch >= 70:
        grade = "Easy (general audience)"
    elif flesch >= 50:
        grade = "Moderate (high-school level)"
    elif flesch >= 30:
        grade = "Difficult (college level)"
    else:
        grade = "Very difficult (specialist level)"

    return {
        "fleschReadingEase": flesch,
        "gunningFogIndex": gunning_fog,
        "avgSentenceLength": avg_sentence_length,
        "gradeLevel": grade,
    }
