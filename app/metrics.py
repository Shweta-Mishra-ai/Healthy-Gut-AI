import re


def keyword_density(text: str, kw: str) -> dict:
    if not text or not text.strip():
        return {"totalWords": 0, "keywordCount": 0, "keywordDensityPercent": 0.0}
    words = re.findall(r"\S+", text.lower())
    total = len(words) or 1
    kw_clean = re.sub(r"\s+", " ", (kw or "").lower().strip())
    if not kw_clean:
        return {"totalWords": total, "keywordCount": 0, "keywordDensityPercent": 0.0}
    # Count occurrences of the full keyword phrase (handles multi-word keywords
    # like "IBS diet", which the old single-word-token check could never match).
    normalized_text = re.sub(r"\s+", " ", text.lower())
    count = normalized_text.count(kw_clean)
    kw_word_count = len(kw_clean.split()) or 1
    density = round((count * kw_word_count) / total * 100, 2)
    return {
        "totalWords": total,
        "keywordCount": count,
        "keywordDensityPercent": density,
    }


def count_syllables(word: str) -> int:
    return len(re.findall(r"[aeiouy]+", word.lower())) or 1


def readability(text: str) -> dict:
    if not text or not text.strip():
        return {"fleschReadingEase": 0.0, "note": "empty text"}
    words = re.findall(r"\S+", text)
    nw = len(words) or 1
    sentences = len(re.findall(r"[.!?]", text)) or 1
    syllables = sum(count_syllables(w) for w in words) or nw
    score = round(206.835 - 1.015 * (nw / sentences) - 84.6 * (syllables / nw), 2)
    # Flesch score is unbounded by formula but conventionally clamp for display
    score = max(-200.0, min(206.835, score))
    return {"fleschReadingEase": score}
