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


def test_pure_hindi_article_not_flagged_for_language_mixing():
    hindi_article = (
        "# आईबीएस डाइट प्लान: आपकी संपूर्ण गाइड\n\n"
        "**ibs diet** आज गट हेल्थ से जुड़े सबसे ज़्यादा खोजे जाने वाले विषयों में से एक है। " * 40
        + "\n\n*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक उद्देश्यों के लिए है।*"
    )
    result = _base_result(optimized_article_markdown=hindi_article)
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="hi")
    assert not any("mixed-language" in f for f in q["flags"])


def test_mostly_english_article_flagged_when_hindi_requested():
    """Regression test: mock mode used to leak a whole raw-English RAG
    paragraph into Hindi articles. This check catches that class of bug
    even when it comes from a live LLM ignoring the language instruction."""
    mostly_english_article = (
        "# Some English Title\n\n"
        "This entire article is actually in English even though Hindi was requested. " * 30
        + "\n\n*चिकित्सा अस्वीकरण*"
    )
    result = _base_result(optimized_article_markdown=mostly_english_article)
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="hi")
    assert any("mixed-language" in f for f in q["flags"])
    assert q["score"] < 100


def test_language_check_ignores_english_titles_in_sources_section():
    """English proper-noun citation titles in the auto-appended Sources
    Referenced section shouldn't count against language purity."""
    hindi_article = (
        "# आईबीएस गाइड\n\n"
        "यह एक पूरी तरह हिंदी में लिखा गया लेख है जो पाठकों को जानकारी देता है। " * 40
        + "\n\n*चिकित्सा अस्वीकरण*"
        + "\n\n## संदर्भित स्रोत\n\n- Irritable Bowel Syndrome (IBS) — internal medical knowledge base\n- Crohn's Disease — internal medical knowledge base"
    )
    result = _base_result(optimized_article_markdown=hindi_article)
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="hi")
    assert not any("mixed-language" in f for f in q["flags"])


def test_language_check_skipped_for_english_requests():
    result = _base_result()
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="en")
    assert not any("mixed-language" in f for f in q["flags"])


def test_hindi_article_not_penalized_for_english_keyword_transliterated():
    """Regression test: the primary keyword is typically kept in English
    even for Hindi content (that's how people actually search), so the
    article body legitimately writes it in Devanagari transliteration
    (e.g. "आईबीएस डाइट") rather than the literal Latin string "ibs diet".
    The old exact-substring check couldn't see that and docked 25 points
    from every well-formed Hindi article for a non-issue."""
    hindi_article = (
        "# आईबीएस डाइट टिप्स: संपूर्ण गाइड\n\n"
        "यह लेख पाचन तंत्र से जुड़ी एक सामान्य समस्या के बारे में विस्तार से बताता है। " * 40
        + "\n\n*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक उद्देश्यों के लिए है।*"
    )
    result = _base_result(
        optimized_article_markdown=hindi_article,
        meta_description="आईबीएस डाइट के बारे में जानकारी और लक्षण प्रबंधन के तरीके यहां पढ़ें आज ही।",
    )
    q = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="hi")
    assert not any("Primary keyword" in f for f in q["flags"])

    # And the same exact-substring check must still fire for English content,
    # where a literally-missing keyword is a real, actionable SEO problem.
    q_en = assess_quality(result, "IBS diet plan", "ibs diet", "supporting", language="en")
    assert any("Primary keyword" in f for f in q_en["flags"])


# --- Script and compliance integration ---------------------------------

def test_devanagari_slug_is_valid_for_a_hindi_article():
    """An ASCII-only slug pattern flagged every well-formed Hindi URL."""
    result = {
        "optimized_article_markdown": "पाचन तंत्र की देखभाल। " * 300,
        "meta_description": "क" * 130,
        "meta_description_variants": ["क" * 130, "ख" * 130],
        "url_slug": "पाचन-तंत्र-की-देखभाल-guide",
        "faqs": [{"question": "क?", "answer": "ख।"}, {"question": "ग?", "answer": "घ।"}],
    }
    flags = assess_quality(result, "पाचन", "pachan tips", "supporting", "hi")["flags"]
    assert not any("slug" in f for f in flags)


def test_malformed_slug_is_still_flagged_for_hindi():
    result = {"optimized_article_markdown": "पाचन " * 300, "url_slug": "Bad Slug!"}
    flags = assess_quality(result, "पाचन", "pachan", "supporting", "hi")["flags"]
    assert any("slug" in f for f in flags)


def test_foreign_script_characters_are_flagged_and_penalised():
    clean = {"optimized_article_markdown": "Gut health guidance. " * 300}
    dirty = {"optimized_article_markdown": "Gut health guidance. " * 300 + " 消化系统健康"}
    clean_score = assess_quality(clean, "gut", "gut health", "supporting")["score"]
    dirty_report = assess_quality(dirty, "gut", "gut health", "supporting")
    assert dirty_report["score"] < clean_score
    assert any("another writing system" in f for f in dirty_report["flags"])


def test_compliance_blockers_lower_the_quality_score():
    base = {"optimized_article_markdown": "Gut health guidance. " * 300}
    with_blockers = {
        **base,
        "compliance": {"counts": {"blocker": 2, "warning": 0, "notice": 0}, "score_penalty": 30},
    }
    assert (assess_quality(with_blockers, "gut", "gut health", "supporting")["score"]
            < assess_quality(base, "gut", "gut health", "supporting")["score"])
    assert any("compliance blocker" in f for f in
               assess_quality(with_blockers, "gut", "gut health", "supporting")["flags"])
