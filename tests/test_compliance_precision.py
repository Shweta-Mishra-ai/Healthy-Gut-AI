"""Precision of the compliance scanner on sentences a careful writer uses
(must not block) and on sentences that must be caught. Before the
negation/context guards, 9 of the 10 safe sentences were blockers and all 7
risky ones passed as clear."""
import pytest

from app.compliance import scan_article
from app.postprocess import ensure_disclaimer

DISCLAIMER = "\n\n*Medical Disclaimer: educational only, not a substitute for professional advice.*"

SAFE = [
    "No diet can cure IBS, but many people manage symptoms well.",
    "Peppermint oil does not cure IBS; it may ease cramps.",
    "If you have IBS, keep a food diary.",
    "People who have celiac disease need a strict gluten-free diet.",
    "Do not stop your medication without talking to your doctor.",
    "Never stop taking your medication on your own.",
    "Don't skip seeing a doctor if you notice blood in stool.",
    "Most adults should aim for 25-30 g of fibre per day.",
    "Keep a journal of your symptoms for two weeks.",
]


@pytest.mark.parametrize("sentence", SAFE)
def test_safe_sentences_are_not_blocked(sentence):
    report = scan_article(sentence + DISCLAIMER)
    assert report["counts"]["blocker"] == 0, report["findings"]
    assert not any(f["code"] == "unverifiable_citation" for f in report["findings"])


def test_hindi_negated_cure_is_not_blocked():
    report = scan_article("आईबीएस पूरी तरह ठीक नहीं होता, लेकिन इसे संभाला जा सकता है।" + DISCLAIMER, "hi")
    assert report["counts"]["blocker"] == 0


RISKY = [
    ("This tea gets rid of IBS for good.", "absolute_cure_claim"),
    ("Heal your gut in 7 days with this cleanse.", "absolute_cure_claim"),
    ("Say goodbye to bloating forever.", "absolute_cure_claim"),
    ("Take two capsules a day of our probiotic.", "dosage_instruction"),
    ("Have 2 tablespoons of psyllium daily.", "dosage_instruction"),
    ("Ditch your meds and try this natural fix.", "discourages_care"),
    ("You don't need a doctor for bloating.", "discourages_care"),
    ("You probably have SIBO.", "diagnostic_claim"),
    ("This diet cures IBS.", "absolute_cure_claim"),
]


@pytest.mark.parametrize("sentence,code", RISKY)
def test_risky_sentences_are_blocked(sentence, code):
    report = scan_article(sentence + DISCLAIMER)
    assert any(f["code"] == code and f["severity"] == "blocker" for f in report["findings"]), report["findings"]


@pytest.mark.parametrize("sentence,code", [
    ("रोज़ 500 मिलीग्राम दवा लें।", "dosage_instruction_hi"),
    ("दो कैप्सूल रोज़ाना लें।", "dosage_instruction_hi"),
    ("ईसबगोल 2 चम्मच रोज़ रात को लें।", "dosage_instruction_hi"),
    ("दवा छोड़ दें और यह नुस्खा आज़माएँ।", "discourages_care_hi"),
])
def test_hindi_risky_sentences_are_blocked(sentence, code):
    report = scan_article(sentence + DISCLAIMER, "hi")
    assert any(f["code"] == code for f in report["findings"]), report["findings"]


def test_hindi_dietary_quantity_is_not_a_dose():
    report = scan_article("रोज़ 30 ग्राम फाइबर खाने की कोशिश करें।" + DISCLAIMER, "hi")
    assert report["counts"]["blocker"] == 0


def test_cure_attributed_to_medical_treatment_is_a_warning_not_a_blocker():
    report = scan_article("Eradication therapy cures ulcers caused by H. pylori in most people." + DISCLAIMER)
    finding = next(f for f in report["findings"] if f["code"] == "absolute_cure_claim")
    assert finding["severity"] == "warning"
    assert report["counts"]["blocker"] == 0


def test_journal_citation_is_still_flagged():
    report = scan_article("A trial in the Journal of Gastroenterology found benefits." + DISCLAIMER)
    assert any(f["code"] == "unverifiable_citation" for f in report["findings"])


def test_consult_a_doctor_is_not_a_disclaimer():
    """'consult a ...' used to satisfy the disclaimer check, so no disclaimer
    was added to such articles and none was reported missing."""
    body = "# IBS\n\nIBS is common. Consult a gastroenterologist if symptoms persist."
    assert any(f["code"] == "missing_disclaimer" for f in scan_article(body)["findings"])
    assert "Disclaimer" in ensure_disclaimer(body, "en")


def test_hindi_medical_advice_phrase_is_not_a_disclaimer():
    body = "# गैस\n\nलक्षण बने रहें तो चिकित्सा सलाह लें।"
    assert "अस्वीकरण" in ensure_disclaimer(body, "hi")
