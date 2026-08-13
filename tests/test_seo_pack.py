"""Deterministic SEO pack: structured data, social tags, title candidates."""

import json

from app.seo import (
    MAX_TITLE_TAG_CHARS,
    build_seo_pack,
    build_social_meta,
    build_structured_data,
    build_table_of_contents,
    extract_headings,
    strip_markdown,
    title_tag_variants,
)

ARTICLE = """# IBS Diet: Your Complete Guide

**IBS diet tips** matter for daily comfort.

## What is IBS?
A functional bowel disorder.

### Subsection
Details here.

## Diet and management
| Eat | Avoid |
|---|---|
| Yogurt | Fried food |
"""

RESULT = {
    "optimized_article_markdown": ARTICLE,
    "meta_description": "Learn about IBS diet tips with symptoms, foods to eat and when to see a doctor.",
    "url_slug": "ibs-diet-guide",
    "faqs": [
        {"question": "What is **IBS**?", "answer": "A functional bowel disorder."},
        {"question": "Is it common?", "answer": "Yes, it affects many people."},
    ],
}


def test_extract_headings_returns_levels_in_order():
    headings = extract_headings(ARTICLE)
    assert headings[0] == {"level": 1, "text": "IBS Diet: Your Complete Guide"}
    assert [h["level"] for h in headings] == [1, 2, 3, 2]


def test_strip_markdown_removes_inline_syntax_and_links():
    assert strip_markdown("**bold** and [a link](https://x.test)") == "bold and a link"


def test_title_variants_stay_within_the_truncation_limit():
    variants = title_tag_variants("Irritable bowel syndrome management", "IBS diet tips", "Mumbai, India")
    assert variants
    assert all(len(v) <= MAX_TITLE_TAG_CHARS for v in variants)
    assert len(set(variants)) == len(variants)


def test_title_variants_do_not_stack_two_subtitles():
    variants = title_tag_variants("IBS diet", "IBS diet tips", "USA", h1="IBS Diet: Your Complete Guide")
    assert not any(v.count(":") > 1 for v in variants)


def test_title_variants_trim_on_word_boundaries():
    variants = title_tag_variants("Small intestinal bacterial overgrowth in older adults", "sibo", "Canada")
    for v in variants:
        assert not v.endswith(("-", ":", ","))


def test_structured_data_is_a_valid_linked_graph():
    data = build_structured_data(RESULT, "IBS diet", "IBS diet tips", "Mumbai, India", "en")
    assert data["@context"] == "https://schema.org"
    types = [node["@type"] for node in data["@graph"]]
    assert types == ["MedicalWebPage", "FAQPage", "BreadcrumbList"]
    # Must survive a JSON round-trip: this is pasted into a page verbatim.
    assert json.loads(json.dumps(data))


def test_structured_data_faq_answers_are_plain_text():
    data = build_structured_data(RESULT, "IBS diet", "IBS diet tips")
    faq = next(n for n in data["@graph"] if n["@type"] == "FAQPage")
    assert faq["mainEntity"][0]["name"] == "What is IBS?"


def test_structured_data_omits_faq_node_when_no_faqs():
    data = build_structured_data({**RESULT, "faqs": []}, "IBS diet", "IBS diet tips")
    assert all(n["@type"] != "FAQPage" for n in data["@graph"])


def test_structured_data_uses_absolute_urls_when_site_url_is_set():
    data = build_structured_data(RESULT, "IBS diet", "IBS diet tips", site_url="https://example.test/")
    article = data["@graph"][0]
    assert article["url"] == "https://example.test/ibs-diet-guide"
    assert article["@id"].startswith("https://example.test/")


def test_structured_data_headline_is_capped_at_schema_limit():
    long_title = "# " + "Extremely detailed guidance about digestive wellbeing " * 5
    data = build_structured_data({**RESULT, "optimized_article_markdown": long_title}, "topic", "kw")
    assert len(data["@graph"][0]["headline"]) <= 110


def test_reviewer_badge_becomes_a_reviewed_by_node():
    data = build_structured_data(RESULT, "IBS diet", "IBS diet tips",
                                 reviewer_badge="Reviewed by Dr. Ananya Roy, MD")
    assert data["@graph"][0]["reviewedBy"]["name"] == "Dr. Ananya Roy, MD"


def test_no_reviewer_means_no_fabricated_review_claim():
    data = build_structured_data(RESULT, "IBS diet", "IBS diet tips")
    assert "reviewedBy" not in data["@graph"][0]


def test_social_meta_locale_follows_language():
    hindi = build_social_meta(RESULT, "IBS", "ibs", "Delhi", "hi")
    assert hindi["tags"]["og:locale"] == "hi_IN"
    assert build_social_meta(RESULT, "IBS", "ibs", "USA", "en")["tags"]["og:locale"] == "en_US"


def test_table_of_contents_covers_h2_and_h3_with_anchors():
    toc = build_table_of_contents(ARTICLE)
    assert [t["text"] for t in toc] == ["What is IBS?", "Subsection", "Diet and management"]
    assert toc[0]["anchor"] == "what-is-ibs"


def test_table_of_contents_anchors_support_devanagari():
    toc = build_table_of_contents("## पाचन तंत्र\n\ntext")
    assert toc[0]["anchor"] == "पाचन-तंत्र"


def test_seo_pack_bundles_every_section():
    pack = build_seo_pack(RESULT, "IBS diet", "IBS diet tips", "Mumbai, India", "en")
    assert set(pack) == {"structured_data", "social", "table_of_contents", "headings"}


def test_seo_pack_handles_an_empty_article_without_raising():
    pack = build_seo_pack({"optimized_article_markdown": ""}, "", "")
    assert pack["structured_data"]["@graph"]
    assert pack["table_of_contents"] == []


def test_slug_fallback_keeps_devanagari():
    """An ASCII-only filter erased every character of a Hindi topic, giving
    every Hindi article the same '/article' URL."""
    from app.seo import build_structured_data

    data = build_structured_data(
        {"optimized_article_markdown": "# पाचन गाइड", "url_slug": ""},
        "पाचन तंत्र की देखभाल", "pachan", language="hi",
    )
    assert data["@graph"][0]["url"] == "/पाचन-तंत्र-की-देखभाल"
