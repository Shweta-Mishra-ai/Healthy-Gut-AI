"""Near-duplicate and keyword-cannibalisation detection."""

from app.db import reset_db_for_tests
from app.review import review_store
from app.similarity import NEAR_DUPLICATE_THRESHOLD, check_duplication, duplication_summary

IBS_ARTICLE = """# IBS diet guide

Irritable bowel syndrome causes abdominal pain, bloating and altered bowel habits.
A low-FODMAP diet temporarily restricts fermentable carbohydrates before a structured
reintroduction phase. Fermented foods such as yogurt support the gut microbiome, while
fried food and carbonated drinks commonly worsen symptoms. Consult a gastroenterologist
if symptoms persist beyond three weeks.
"""

GERD_ARTICLE = """# Acid reflux relief

Gastro-oesophageal reflux happens when stomach acid moves back into the oesophagus,
causing heartburn after meals. Raising the head of the bed, avoiding late dinners and
losing excess weight are the usual first steps. Persistent heartburn needs a clinician's
assessment rather than indefinite self-treatment with antacids.
"""


def _store(article_markdown, topic, keyword, status="approved"):
    review_id = review_store.register({"optimized_article_markdown": article_markdown}, topic, keyword)
    if status != "draft":
        from app.review import ReviewStatus
        review_store.set_status(review_id, ReviewStatus[status])
    return review_id


def setup_function():
    reset_db_for_tests()


def test_empty_corpus_is_clear_not_an_error():
    check = check_duplication(IBS_ARTICLE, "IBS diet tips")
    assert check["status"] == "clear"
    assert check["corpus_size"] == 0


def test_identical_article_is_flagged_as_a_duplicate():
    _store(IBS_ARTICLE, "IBS diet guide", "IBS diet tips")
    check = check_duplication(IBS_ARTICLE, "different keyword")
    assert check["status"] == "duplicate"
    assert check["near_duplicates"][0]["similarity"] >= NEAR_DUPLICATE_THRESHOLD
    assert "split their search rankings" in duplication_summary(check)


def test_unrelated_article_is_clear():
    _store(GERD_ARTICLE, "Acid reflux relief", "acid reflux relief")
    check = check_duplication(IBS_ARTICLE, "IBS diet tips")
    assert check["status"] == "clear"
    assert check["near_duplicates"] == []


def test_same_keyword_is_a_cannibalisation_risk_even_when_text_differs():
    _store(GERD_ARTICLE, "Acid reflux relief", "IBS diet tips")
    check = check_duplication(IBS_ARTICLE, "ibs diet tips")
    assert check["status"] == "cannibalisation_risk"
    assert check["keyword_conflicts"][0]["keyword"] == "IBS diet tips"
    assert "already targets the keyword" in duplication_summary(check)


def test_keyword_match_ignores_case_and_punctuation():
    _store(GERD_ARTICLE, "Reflux", "Acid-Reflux, Relief")
    check = check_duplication(IBS_ARTICLE, "acid reflux relief")
    assert check["status"] == "cannibalisation_risk"


def test_excluded_id_is_not_compared_against_itself():
    review_id = _store(IBS_ARTICLE, "IBS diet guide", "IBS diet tips")
    check = check_duplication(IBS_ARTICLE, "IBS diet tips", exclude_id=review_id)
    assert check["status"] == "clear"
    assert check["corpus_size"] == 0


def test_drafts_are_included_in_the_scan():
    """A draft competing for the same keyword is exactly what an editor needs
    to know about before approving a second one."""
    _store(IBS_ARTICLE, "IBS diet guide", "IBS diet tips", status="draft")
    check = check_duplication(IBS_ARTICLE, "IBS diet tips")
    assert check["status"] == "duplicate"
    assert check["near_duplicates"][0]["status"] == "draft"


def test_empty_article_returns_clear():
    _store(IBS_ARTICLE, "IBS diet guide", "IBS diet tips")
    assert check_duplication("   ", "IBS diet tips")["status"] == "clear"
