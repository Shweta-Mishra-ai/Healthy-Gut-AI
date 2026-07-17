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
