from app.metrics import keyword_density, readability


def test_keyword_density_normal():
    r = keyword_density("IBS is common. IBS affects many.", "IBS")
    assert r["totalWords"] == 6
    assert r["keywordCount"] == 2
    assert r["keywordDensityPercent"] > 0


def test_keyword_density_empty_text():
    r = keyword_density("", "IBS")
    assert r["totalWords"] == 0
    assert r["keywordCount"] == 0
    assert r["keywordDensityPercent"] == 0.0


def test_keyword_density_empty_keyword():
    r = keyword_density("some article text here", "")
    assert r["keywordCount"] == 0


def test_readability_empty_text():
    r = readability("")
    assert r["fleschReadingEase"] == 0.0


def test_readability_single_word():
    r = readability("Hi")
    assert "fleschReadingEase" in r


def test_readability_normal_text():
    text = "This is a simple sentence. It has two sentences total."
    r = readability(text)
    assert isinstance(r["fleschReadingEase"], float)


def test_readability_hindi_returns_na_not_nonsense_score():
    """Regression test: the syllable-count regex ([aeiouy]+) only matches
    Latin vowels, so every Devanagari word silently fell back to "1
    syllable" regardless of actual length, and the sentence-boundary regex
    only recognized '.!?' — not the Devanagari danda '।' — so a whole
    multi-sentence Hindi article was treated as one giant sentence. Combined,
    a simple, well-written Hindi paragraph used to score around -180
    ("Very difficult, specialist level") and take an automatic -10 quality
    penalty for it. It should now report N/A instead of a fabricated number."""
    hindi_text = "यह एक सरल वाक्य है। यह पाचन स्वास्थ्य के बारे में है। " * 15
    r = readability(hindi_text, language="hi")
    assert r["fleschReadingEase"] is None
    assert r["gunningFogIndex"] is None
    # Sentence-length must now correctly split on '।', not treat the whole
    # text as a single sentence.
    assert r["avgSentenceLength"] < 20


def test_readability_devanagari_danda_recognized_as_sentence_boundary():
    text_with_danda = "यह पहला वाक्य है। यह दूसरा वाक्य है। यह तीसरा वाक्य है।"
    r = readability(text_with_danda, language="hi")
    # 12 words / 3 sentences = 4 words per sentence, not 12 (which is what
    # the old '.!?'-only regex would have produced by finding zero sentence
    # boundaries and falling back to "1 sentence").
    assert r["avgSentenceLength"] < 6


def test_readability_english_unaffected_by_language_param():
    text = "This is a simple sentence. It has two sentences total."
    r = readability(text, language="en")
    assert isinstance(r["fleschReadingEase"], float)
    assert r["fleschReadingEase"] != None  # noqa: E711 — explicit contrast with the hi-language None case above
