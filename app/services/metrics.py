import re

def keyword_density(text, keyword):
    words = re.findall(r'\w+', text.lower())
    total = len(words)
    count = sum(1 for w in words if keyword.lower() in w)

    density = (count / total * 100) if total > 0 else 0

    return {
        "total_words": total,
        "keyword_count": count,
        "density": round(density, 2)
    }


def readability(text):
    sentences = re.split(r'[.!?]', text)
    words = re.findall(r'\w+', text)

    num_words = len(words)
    num_sentences = len(sentences) if sentences else 1

    avg_sentence_length = num_words / num_sentences if num_sentences else 0

    return {
        "words": num_words,
        "sentences": num_sentences,
        "avg_sentence_length": round(avg_sentence_length, 2)
    }
