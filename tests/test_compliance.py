"""YMYL compliance scanner."""

from app.compliance import scan_article

CLEAN_ARTICLE = """# Managing IBS Symptoms

Irritable bowel syndrome may cause abdominal discomfort and changes in bowel habits.
A low-FODMAP approach is commonly recommended and may help manage symptoms for some people.

## When to see a doctor
If symptoms persist for more than three weeks, consult a doctor for an assessment.

---
*Medical Disclaimer: This article is educational and not a substitute for professional medical advice.*
"""


def test_clean_article_passes():
    report = scan_article(CLEAN_ARTICLE)
    assert report["risk_level"] == "clear"
    assert report["counts"]["blocker"] == 0
    assert report["score_penalty"] == 0


def test_cure_claim_is_a_blocker():
    report = scan_article(CLEAN_ARTICLE + "\nThis diet cures IBS for everyone.")
    assert report["risk_level"] == "blocked"
    assert any(f["code"] == "absolute_cure_claim" for f in report["findings"])


def test_permanent_cure_phrasing_is_a_blocker():
    report = scan_article(CLEAN_ARTICLE + "\nIt permanently eliminates bloating.")
    assert any(f["code"] == "absolute_cure_claim" for f in report["findings"])


def test_dosage_instruction_is_a_blocker():
    report = scan_article(CLEAN_ARTICLE + "\nTake 500 mg of peppermint oil daily for relief.")
    codes = [f["code"] for f in report["findings"]]
    assert "dosage_instruction" in codes


def test_discouraging_care_is_a_blocker():
    report = scan_article(CLEAN_ARTICLE + "\nThere is no need to see a doctor if you follow this.")
    assert any(f["code"] == "discourages_care" for f in report["findings"])


def test_telling_reader_to_stop_medication_is_a_blocker():
    report = scan_article(CLEAN_ARTICLE + "\nYou can stop taking your medication once symptoms ease.")
    assert any(f["code"] == "discourages_care" for f in report["findings"])


def test_statistics_and_citations_are_warnings_not_blockers():
    report = scan_article(CLEAN_ARTICLE + "\nAccording to a 2019 study, 87% of patients improved.")
    assert report["risk_level"] == "review"
    codes = [f["code"] for f in report["findings"]]
    assert "unsourced_statistic" in codes
    assert "unverifiable_citation" in codes
    assert report["counts"]["blocker"] == 0


def test_superlative_claim_is_a_warning():
    report = scan_article(CLEAN_ARTICLE + "\nIt is the best treatment for bloating.")
    assert any(f["code"] == "superlative_claim" for f in report["findings"])


def test_missing_disclaimer_is_a_blocker():
    report = scan_article("# Guide\n\nSome ordinary gut health information without any closing note.")
    assert any(f["code"] == "missing_disclaimer" for f in report["findings"])
    assert report["risk_level"] == "blocked"


def test_missing_care_pathway_is_a_notice():
    body = ("# Guide\n\nSome gut health information.\n\n"
            "*Medical Disclaimer: educational only, not a substitute for professional advice.*")
    report = scan_article(body)
    assert any(f["code"] == "no_care_pathway" for f in report["findings"])


def test_hindi_cure_claim_is_detected():
    hindi = ("# गाइड\n\nयह डाइट पेट की समस्या का पूर्ण इलाज है।\n\n"
             "डॉक्टर से परामर्श लें।\n\n*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक है।*")
    report = scan_article(hindi, language="hi")
    assert any(f["code"] == "absolute_cure_claim_hi" for f in report["findings"])
    assert report["risk_level"] == "blocked"


def test_findings_carry_quoted_evidence():
    report = scan_article(CLEAN_ARTICLE + "\nThis diet cures IBS for everyone who tries it.")
    finding = next(f for f in report["findings"] if f["code"] == "absolute_cure_claim")
    assert "cures ibs" in finding["evidence"].lower()
    assert finding["matched"]


def test_findings_are_capped_per_rule():
    noisy = CLEAN_ARTICLE + "\n" + " ".join(f"About {n}% of people." for n in range(1, 20))
    report = scan_article(noisy)
    assert sum(1 for f in report["findings"] if f["code"] == "unsourced_statistic") <= 3


def test_penalty_is_bounded():
    awful = "\n".join([
        "This cures IBS permanently.",
        "Take 500 mg daily.",
        "No need to see a doctor.",
        "It is the best treatment.",
        "According to a 2018 study, 99% recovered.",
        "You have IBS.",
    ])
    report = scan_article(awful)
    assert report["score_penalty"] <= 40


def test_empty_article_produces_no_findings():
    report = scan_article("")
    assert report["findings"] == []
    assert report["risk_level"] == "clear"


def test_findings_sorted_by_severity():
    report = scan_article(CLEAN_ARTICLE + "\nAbout 40% improve. This diet cures IBS.")
    severities = [f["severity"] for f in report["findings"]]
    assert severities == sorted(severities, key=lambda s: {"blocker": 0, "warning": 1, "notice": 2}[s])
