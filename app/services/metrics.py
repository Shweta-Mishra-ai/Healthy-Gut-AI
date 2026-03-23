import re

def count_sentences(text: str) -> int:
    matches = re.findall(r'[.!?]', text)
    return len(matches) if matches else 1

def count_syllables(word: str) -> int:
    matches = re.findall(r'[aeiouy]+', word.lower())
    return len(matches) if matches else 1

def flesch_reading_ease(text: str) -> float:
    words = [w for w in re.split(r'\s+', text) if w]
    num_words = len(words) or 1
    num_sentences = count_sentences(text)
    num_syllables = sum(count_syllables(w) for w in words)
    asl = num_words / num_sentences
    asw = num_syllables / num_words
    score = 206.835 - 1.015 * asl - 84.6 * asw
    return round(score, 2)

def calculate_readability(article: str) -> dict:
    if not article:
        return {"fleschReadingEase": 0}
    return {"fleschReadingEase": flesch_reading_ease(article)}

def calculate_keyword_density(article: str, keyword: str) -> dict:
    if not article or not keyword:
        return {"totalWords": 0, "keywordCount": 0, "keywordDensityPercent": 0.0}
    words = [w for w in re.split(r'\s+', article.lower()) if w]
    total = len(words)
    count = sum(1 for w in words if keyword.lower() in w)
    density = round((count / total) * 100, 2) if total > 0 else 0.0
    return {
        "totalWords": total,
        "keywordCount": count,
        "keywordDensityPercent": density
    }
