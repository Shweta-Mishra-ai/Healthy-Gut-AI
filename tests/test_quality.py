from app.quality import assess_quality


def _base_result(**overrides):
    result = {
        "optimized_article_markdown": "# IBS Diet Plan\n\n" + ("word " * 1200) + "\n\n*Medical Disclaimer: consult a doctor.*",
        "meta_description": "A" * 140,
        "url_slug": "ibs-diet-plan-guide",
        "faqs": [{"question": "q1", "answer": "a1"}, {"question": "q2", "answer": "a2"}],
        "metrics": {"readability": {"fleschReadingEase": 60.0}},
    }
    result.update(overrides)
    return result


def test_good_article_scores_high():
    result = _base_result()
    result["optimized_article_markdown"] = "# IBS Diet Plan\n\nibs diet " + ("word " * 1200) + "\n\n*Medical Disclaimer: consult a doctor.*"
    result["meta_description"] = "Learn about ibs diet with our complete guide covering symptoms diet and management options today." 
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert q["score"] >= 70
    assert q["word_count"] > 1000


def test_short_article_flagged_and_penalized():
    result = _base_result(optimized_article_markdown="# Short\n\nToo short. *Medical Disclaimer: consult a doctor.*")
    q = assess_quality(result, "IBS diet plan", "ibs diet", "pillar")
    assert q["score"] < 80
    assert any("Word count" in f for f in q["flags"])


def test_missing_disclaimer_flagged():
    result = _base_result(optimized_article_markdown="# IBS\n\n" + ("word " * 1200))
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("disclaimer" in f.lower() for f in q["flags"])


def test_bad_meta_description_length_flagged():
    result = _base_result(meta_description="Too short")
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("Meta description" in f for f in q["flags"])


def test_missing_keyword_in_opening_flagged():
    result = _base_result(optimized_article_markdown="# Unrelated Title\n\n" + ("word " * 1200) + "*Medical Disclaimer: consult a doctor.*")
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("opening" in f.lower() for f in q["flags"])


def test_bad_slug_flagged():
    result = _base_result(url_slug="Not A Slug!!")
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("slug" in f.lower() for f in q["flags"])


def test_too_few_faqs_flagged():
    result = _base_result(faqs=[{"question": "q1", "answer": "a1"}])
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("FAQ" in f for f in q["flags"])


def test_very_low_readability_flagged():
    result = _base_result(metrics={"readability": {"fleschReadingEase": 10.0}})
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting")
    assert any("Readability" in f for f in q["flags"])


def test_score_never_negative():
    result = _base_result(
        optimized_article_markdown="short",
        meta_description="x",
        url_slug="Bad Slug",
        faqs=[],
        metrics={"readability": {"fleschReadingEase": 5.0}},
    )
    q = assess_quality(result, "IBS diet plan", "ibs diet", "pillar")
    assert q["score"] >= 0
