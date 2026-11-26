"""YMYL compliance scanner for health content.

Gut-health articles are "Your Money or Your Life" content: search engines
hold them to a higher evidentiary bar, ad networks and pharmacy affiliates
have hard rules about what may be claimed, and a wrong claim can hurt a
reader. A quality score built on word count and keyword density says
nothing about any of that.

This scans the finished article for the specific claim patterns that get
health pages demoted, rejected by an ad network, or pulled by a medical
reviewer, and returns concrete findings with the offending text quoted, so
an editor can fix the sentence rather than guess. Every check is a literal
pattern match on the output — no model call, no probabilistic judgement.

Findings carry a severity:
  blocker  — must not publish (absolute cure claims, dosing instructions,
             telling a reader to skip or stop medical care)
  warning  — publish only after an editor confirms it (unsourced statistics,
             fabricated-sounding citations, superlatives)
  notice   — stylistic/trust improvements (hedging, missing disclaimer link)
"""

import re

from app.quality import DISCLAIMER_MARKERS

SEVERITY_ORDER = {"blocker": 0, "warning": 1, "notice": 2}

# Conditions and complaints a cure/elimination claim can target.
_COND = (
    r"(ibs|ibd|gerd|celiac|coeliac|sibo|crohn'?s?|colitis|gastritis|ulcers?|bloating|constipation|"
    r"diarrh(?:o)?ea|reflux|acidity|indigestion|piles|ha?emorrhoids|h\.?\s?pylori|leaky\s+gut|candida|"
    r"the\s+condition|it)"
)
_NUM_WORD = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|half\s+a)"
_NUM = rf"(?:\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?|{_NUM_WORD})"
_DRUG_UNIT = r"(?:mg|mcg|µg|iu|billion\s+cfu|cfu|capsules?|tablets?|pills?|drops?|sachets?|softgels?)"
_KITCHEN_UNIT = r"(?:g|grams?|ml|tablespoons?|tbsp|teaspoons?|tsp|scoops?)"
_FREQUENCY = (
    r"(?:daily|per\s+day|a\s+day|twice|thrice|three\s+times|times\s+a\s+day|every\s+(?:day|morning|night)|"
    r"each\s+(?:day|morning|night)|before\s+bed|at\s+bedtime|at\s+night|with\s+(?:each\s+)?meals?|"
    r"(?:after|before)\s+meals?|on\s+an\s+empty\s+stomach)"
)
# A quantity in grams or spoons is dietary guidance ("25-30 g of fibre per
# day") unless the sentence is about a supplement or medicine.
_SUPPLEMENT_CONTEXT = re.compile(
    r"\b(supplements?|capsules?|tablets?|pills?|probiotics?|psyllium|isabgol|powder|doses?|dosage|"
    r"medications?|medicines?|drugs?|peppermint\s+oil|laxatives?|enzymes?|extracts?|ashwagandha|"
    r"triphala|churna|syrup)\b"
)
_HI_SUPPLEMENT_CONTEXT = re.compile(r"(सप्लीमेंट|कैप्सूल|दवा|दवाई|ईसबगोल|इसबगोल|चूर्ण|प्रोबायोटिक|सिरप|गोली)")
_HI_FREQUENCY = r"(रोज़|रोज|रोज़ाना|रोजाना|प्रतिदिन|हर\s*दिन|दिन\s*में|सुबह|रात\s*को|खाने\s*(के)?\s*(बाद|पहले))"

# Words in the few words before a claim that turn it into its opposite
# ("no diet can cure IBS", "do not stop your medication"). Before these
# guards, the most careful sentences a model writes were the ones flagged.
_NEGATION = re.compile(
    r"\b(no|not|never|cannot|can'?t|doesn'?t|does\s+not|don'?t|do\s+not|won'?t|will\s+not|isn'?t|"
    r"is\s+not|aren'?t|nothing|neither|nor|unlikely|there\s+is\s+no|there'?s\s+no)\b"
)
_CONDITIONAL = re.compile(
    r"\b(if|when|whether|unless|in\s+case|(?:people|those|anyone|someone|patients|readers)\s+who)\b"
)
# Medically accurate cure statements exist (H. pylori eradication, surgery
# for ulcerative colitis); attributed to a treatment they need a clinician's
# confirmation, not an automatic block.
_MEDICAL_TREATMENT = re.compile(
    r"\b(antibiotics?|eradication|surgery|surgical|colectomy|therapy|treatment\s+with|prescribed)\b"
)
_SENTENCE_BREAK = re.compile(r"[.!?।\n]")
_HI_NEGATION_AFTER = re.compile(r"^\s*(नहीं|न\s)")


def _sentence(text: str, start: int, end: int) -> str:
    left = max((m.end() for m in _SENTENCE_BREAK.finditer(text, 0, start)), default=0)
    right_match = _SENTENCE_BREAK.search(text, end)
    right = right_match.start() if right_match else len(text)
    return text[left:right]


def _words_before(text: str, start: int, count: int = 6) -> str:
    left = max((m.end() for m in _SENTENCE_BREAK.finditer(text, 0, start)), default=0)
    words = text[left:start].split()
    return " ".join(words[-count:]).replace("not only", "")


def _negated(text: str, match: re.Match) -> bool:
    return bool(_NEGATION.search(_words_before(text, match.start())))


def _conditional_or_negated(text: str, match: re.Match) -> bool:
    before = _words_before(text, match.start())
    return bool(_CONDITIONAL.search(before) or _NEGATION.search(before))


def _hi_negated(text: str, match: re.Match) -> bool:
    return bool(_HI_NEGATION_AFTER.search(text[match.end():match.end() + 12]))


def _needs_supplement_context(text: str, match: re.Match) -> bool:
    """Guard returning True (= suppress) when no supplement/medicine is in the sentence."""
    return not _SUPPLEMENT_CONTEXT.search(_sentence(text, match.start(), match.end()))


def _hi_needs_supplement_context(text: str, match: re.Match) -> bool:
    return not _HI_SUPPLEMENT_CONTEXT.search(_sentence(text, match.start(), match.end()))


def _rule(code, severity, message, pattern, *, original_case=False, suppress=None, downgrade=None):
    return {
        "code": code, "severity": severity, "message": message, "pattern": re.compile(pattern),
        # Hindi patterns and case-sensitive ones run on the original text;
        # everything else on the lowercased text.
        "original_case": original_case or code.endswith("_hi"),
        "suppress": suppress, "downgrade": downgrade,
    }


_RULES: list[dict] = [
    _rule(
        "absolute_cure_claim", "blocker",
        "States or implies a guaranteed cure. Health content must not promise cures — "
        "rewrite as 'may help manage' or 'is commonly recommended for'.",
        rf"\b(cures?|curing|cured)\s+(your\s+|the\s+|all\s+)?{_COND}\b"
        r"|\b(permanent(ly)?|complete(ly)?|fully|100%|guaranteed?)\s+(cure|cured|cures|eliminates?|"
        r"eliminated|heals?|healed|reverses?|reversed)\b"
        r"|\bmiracle\s+(cure|remedy|food|treatment)\b"
        r"|\bcure[sd]?\s+(it\s+)?(permanently|completely|forever|for\s+good)\b"
        rf"|\b(gets?|getting)\s+rid\s+of\s+{_COND}\s+(for\s+good|forever|permanently|completely|once\s+and\s+for\s+all)\b"
        rf"|\b(eliminates?|eradicates?|wipes?\s+out)\s+{_COND}\s+(for\s+good|forever|permanently|completely)\b"
        rf"|\b(heal|cure|fix|reset|repair)\s+(your\s+)?(gut|{_COND})\s+in\s+(\d+|{_NUM_WORD}|a)\s+(days?|weeks?|hours?)\b"
        rf"|\bsay\s+goodbye\s+to\s+{_COND}\s+(forever|for\s+good)\b"
        rf"|\bnever\s+(suffer|deal)\s+(from|with)\s+{_COND}\s+again\b",
        suppress=_negated,
        downgrade=_MEDICAL_TREATMENT,
    ),
    _rule(
        "absolute_cure_claim_hi", "blocker",
        "Hindi text promises a complete/permanent cure. Use balanced wording such as "
        "'प्रबंधन में मदद कर सकता है' instead.",
        r"(पूर्ण\s*इलाज|पूरी\s*तरह\s*ठीक|हमेशा\s*के\s*लिए\s*ठीक|१००%\s*इलाज|100%\s*इलाज|चमत्कारी\s*इलाज|गारंटीशुदा|जड़\s*से\s*खत्म)",
        suppress=_hi_negated,
    ),
    _rule(
        "dosage_instruction", "blocker",
        "Contains a specific dose or regimen. Dosing is individual medical advice and "
        "must come from a clinician, not an article.",
        rf"\b{_NUM}\s?{_DRUG_UNIT}\b[^.\n]{{0,60}}?\b{_FREQUENCY}"
        rf"|\b{_FREQUENCY}[^.\n]{{0,30}}?\b{_NUM}\s?{_DRUG_UNIT}\b"
        rf"|\btake\s+({_NUM}|a|an)\s?{_DRUG_UNIT}\b",
        suppress=_negated,
    ),
    _rule(
        "dosage_instruction", "blocker",
        "Contains a specific supplement or medicine quantity with a schedule. Dosing must come from a clinician.",
        rf"\b{_NUM}\s?{_KITCHEN_UNIT}\b[^.\n]{{0,60}}?\b{_FREQUENCY}",
        suppress=lambda text, m: _negated(text, m) or _needs_supplement_context(text, m),
    ),
    _rule(
        "dosage_instruction_hi", "blocker",
        "Hindi text gives a dose or regimen. Dosing must come from a clinician.",
        rf"(\d+|एक|दो|तीन|चार|पाँच|पांच)\s*(मिलीग्राम|मि\.?\s?ग्रा\.?|एमजी|mg|कैप्सूल|गोली|गोलियां|गोलियाँ|टैबलेट|बूंद|बूँद)"
        rf"[^।\n]{{0,40}}{_HI_FREQUENCY}|{_HI_FREQUENCY}[^।\n]{{0,40}}(\d+|एक|दो|तीन|चार|पाँच|पांच)\s*"
        r"(मिलीग्राम|मि\.?\s?ग्रा\.?|एमजी|mg|कैप्सूल|गोली|गोलियां|गोलियाँ|टैबलेट|बूंद|बूँद)",
    ),
    _rule(
        "dosage_instruction_hi", "blocker",
        "Hindi text gives a supplement quantity with a schedule. Dosing must come from a clinician.",
        rf"(\d+|एक|दो|तीन|चार|पाँच|पांच)\s*(ग्राम|चम्मच)[^।\n]{{0,40}}{_HI_FREQUENCY}",
        suppress=_hi_needs_supplement_context,
    ),
    _rule(
        "discourages_care", "blocker",
        "Discourages professional medical care. Never tell a reader to skip, delay or "
        "stop treatment — always point them to a clinician.",
        r"\b(no\s+need\s+to\s+(see|consult|visit)\s+a?\s*(doctor|gp|physician|specialist))\b"
        r"|\bno\s+need\s+for\s+(a\s+)?(doctor|medications?|medicines?|prescriptions?)\b"
        r"|\b(avoid|skip|don'?t\s+bother\s+with)\s+(seeing\s+)?(a\s+)?(doctor|doctors|physicians?)\b"
        r"|\b(stop|discontinue|quit)\s+(taking\s+)?(your\s+)?(medication|medicines?|prescription|treatment)\b"
        r"|\b(ditch|dump|throw\s+(out|away)|get\s+off|come\s+off)\s+(all\s+)?(your\s+)?(meds|medications?|medicines?|pills|prescriptions?)\b"
        r"|\binstead\s+of\s+(seeing\s+a\s+doctor|medical\s+treatment|prescribed\s+medication)\b"
        r"|\byou\s+(don'?t|do\s+not)\s+need\s+(a\s+|to\s+see\s+a\s+|to\s+visit\s+a\s+)?"
        r"(doctor|gp|physician|specialist|gastroenterologist)\b"
        r"|\b(doctors?|medicines?|medications?)\s+(can'?t|cannot|won'?t)\s+help\b",
        suppress=_negated,
    ),
    _rule(
        "discourages_care_hi", "blocker",
        "Hindi text discourages seeing a doctor or continuing treatment. Always direct "
        "readers to a qualified clinician.",
        r"(डॉक्टर\s*(के\s*पास\s*जाने)?\s*की\s*(कोई\s*)?ज़?रूरत\s*नहीं|दवा(ई|इयाँ|इयां|एं|एँ)?\s*(बंद|छोड़)\s*(कर\s*)?(दें|दो|दीजिए)|इलाज\s*बंद\s*कर)",
    ),
    _rule(
        "diagnostic_claim", "blocker",
        "Diagnoses the reader directly. An article can describe symptoms; it cannot "
        "tell someone what they have.",
        r"\byou\s+(definitely\s+|certainly\s+|probably\s+|likely\s+|clearly\s+)?(have|are\s+suffering\s+from)\s+"
        r"(ibs|ibd|gerd|celiac|coeliac|sibo|crohn'?s|colitis|cancer)\b"
        r"|\bthis\s+means\s+you\s+have\b"
        r"|\bdiagnose\s+yourself\b",
        suppress=_conditional_or_negated,
    ),
    _rule(
        "unsourced_statistic", "warning",
        "Cites a specific statistic. Confirm the figure appears in the grounding "
        "sources, or replace it with a qualitative description.",
        r"\b\d{1,3}(\.\d+)?\s?%|\b(\d+)\s+(in|out\s+of)\s+(\d+)\s+(people|patients|adults|women|men)\b",
    ),
    _rule(
        "unverifiable_citation", "warning",
        "References a study, journal or organisation that this app cannot verify. "
        "Either attach a real citation or remove the attribution.",
        r"\b(a|the)\s+(19|20)\d{2}\s+(study|trial|paper|review|meta-analysis)\b"
        r"|\baccording\s+to\s+(a\s+)?(study|research|researchers|scientists|the\s+(who|nih|cdc|nhs|icmr|aiims))\b"
        r"|\bpublished\s+in\s+(the\s+)?[a-z]",
    ),
    _rule(
        # Case-sensitive on purpose: "the Journal of Gastroenterology" is a
        # citation, "keep a journal of your symptoms" is advice.
        "unverifiable_citation", "warning",
        "References a journal this app cannot verify. Either attach a real citation or remove the attribution.",
        r"\bJournal\s+of\s+[A-Z][a-z]+",
        original_case=True,
    ),
    _rule(
        "superlative_claim", "warning",
        "Uses an unqualified superlative. Search raters treat 'the best/most effective' "
        "health claims as unsupported unless attributed.",
        r"\b(the\s+)?(best|most\s+effective|safest|strongest|number\s+one|#1)\s+"
        r"(treatment|remedy|cure|supplement|probiotic|diet|food|medicine)\b",
    ),
    _rule(
        "risky_self_treatment", "warning",
        "Suggests self-treating without clinical oversight. Add an explicit "
        "'talk to your doctor first' qualifier next to this advice.",
        r"\b(self[-\s]?medicat\w*|treat\s+it\s+at\s+home\s+without|no\s+prescription\s+(needed|required))\b",
        suppress=_negated,
    ),
    _rule(
        "fear_marketing", "notice",
        "Uses fear-based framing. Health content converts better and rates better on "
        "trust when it stays calm and factual.",
        r"\b(dangerous(ly)?\s+(toxic|deadly)|silent\s+killer|destroy(ing)?\s+your\s+(gut|body)|shocking\s+truth)\b",
    ),
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")


def _evidence_for(text: str, match: re.Match) -> str:
    """The sentence containing the match, trimmed — an editor needs to see
    the claim in context to rewrite it, not just the matched fragment."""
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    if end == -1:
        end = min(len(text), match.end() + 120)
    snippet = text[start:end + 1].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    if len(snippet) > 220:
        snippet = snippet[:217].rstrip() + "..."
    return snippet


def scan_article(article_markdown: str, language: str = "en") -> dict:
    """Runs every compliance rule over the article.

    Returns {risk_level, findings, counts, score_penalty}. `risk_level` is
    'blocked' when anything must be fixed before publishing, 'review' when a
    human should confirm, 'clear' otherwise.
    """
    text = article_markdown or ""
    lower = text.lower()
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for rule in _RULES:
        code, pattern = rule["code"], rule["pattern"]
        target = text if rule["original_case"] else lower
        for match in pattern.finditer(target):
            if rule["suppress"] and rule["suppress"](target, match):
                continue
            severity, message = rule["severity"], rule["message"]
            if rule["downgrade"] and rule["downgrade"].search(_sentence(target, match.start(), match.end())):
                severity = "warning"
                message += " Here it is attributed to a medical treatment — confirm the wording with a clinician."
            evidence = _evidence_for(target, match)
            key = (code, evidence)
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "code": code,
                "severity": severity,
                "message": message,
                "evidence": evidence,
                "matched": match.group(0).strip(),
            })
            # Three examples of the same problem is enough for an editor to
            # see the pattern; more just buries the other findings.
            if sum(1 for f in findings if f["code"] == code) >= 3:
                break

    if text.strip() and not any(marker in lower for marker in DISCLAIMER_MARKERS):
        findings.append({
            "code": "missing_disclaimer",
            "severity": "blocker",
            "message": "No medical disclaimer found. Health content must state that it is "
                       "educational and not a substitute for professional advice.",
            "evidence": "",
            "matched": "",
        })

    if text.strip() and not re.search(r"(consult|speak\s+to|see)\s+(a|your)\s+(doctor|gp|clinician|gastroenterologist|"
                                      r"healthcare\s+provider)|डॉक्टर\s*से\s*(सलाह|परामर्श|मिलें)", lower):
        findings.append({
            "code": "no_care_pathway",
            "severity": "notice",
            "message": "The article never tells the reader when to seek professional care. "
                       "A 'when to see a doctor' pathway is expected in health content.",
            "evidence": "",
            "matched": "",
        })

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 3))
    counts = {
        "blocker": sum(1 for f in findings if f["severity"] == "blocker"),
        "warning": sum(1 for f in findings if f["severity"] == "warning"),
        "notice": sum(1 for f in findings if f["severity"] == "notice"),
    }

    if counts["blocker"]:
        risk_level = "blocked"
    elif counts["warning"]:
        risk_level = "review"
    else:
        risk_level = "clear"

    # Bounded so a long article with many minor notices can't zero out an
    # otherwise-good quality score on its own.
    penalty = min(40, counts["blocker"] * 15 + counts["warning"] * 5 + counts["notice"] * 2)

    return {
        "risk_level": risk_level,
        "findings": findings,
        "counts": counts,
        "score_penalty": penalty,
        "checked_rules": len({r['code'] for r in _RULES}) + 2,
    }
