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

SEVERITY_ORDER = {"blocker": 0, "warning": 1, "notice": 2}

# Each rule: (code, severity, message, compiled pattern)
# Patterns are lowercase-matched against the article body. Hindi patterns
# are matched against the original text (Devanagari has no case).
_RULES: list[tuple[str, str, str, re.Pattern]] = [
    (
        "absolute_cure_claim", "blocker",
        "States or implies a guaranteed cure. Health content must not promise cures — "
        "rewrite as 'may help manage' or 'is commonly recommended for'.",
        re.compile(
            r"\b(cures?|curing|cured)\s+(your\s+|the\s+|all\s+)?"
            r"(ibs|ibd|gerd|celiac|coeliac|sibo|crohn'?s?|colitis|gastritis|ulcers?|"
            r"bloating|constipation|diarrh(?:o)?ea|reflux|the\s+condition|it)\b"
            r"|\b(permanent(ly)?|complete(ly)?|fully|100%|guaranteed?)\s+(cure|cured|cures|eliminates?|"
            r"eliminated|heals?|healed|reverses?|reversed)\b"
            r"|\bmiracle\s+(cure|remedy|food|treatment)\b"
            r"|\bcure[sd]?\s+(it\s+)?(permanently|completely|forever|for\s+good)\b"
        ),
    ),
    (
        "absolute_cure_claim_hi", "blocker",
        "Hindi text promises a complete/permanent cure. Use balanced wording such as "
        "'प्रबंधन में मदद कर सकता है' instead.",
        re.compile(r"(पूर्ण\s*इलाज|पूरी\s*तरह\s*ठीक|हमेशा\s*के\s*लिए\s*ठीक|१००%\s*इलाज|100%\s*इलाज|चमत्कारी\s*इलाज|गारंटीशुदा)"),
    ),
    (
        "dosage_instruction", "blocker",
        "Contains a specific dose or regimen. Dosing is individual medical advice and "
        "must come from a clinician, not an article.",
        re.compile(
            r"\b\d+\s?(mg|mcg|µg|g|ml|iu|billion\s+cfu|cfu)\b[^.\n]{0,60}?"
            r"\b(daily|per\s+day|twice|thrice|every\s+day|a\s+day|before\s+bed|with\s+meals?)\b"
            r"|\btake\s+\d+\s?(mg|mcg|g|ml|iu|tablets?|capsules?|pills?)\b"
        ),
    ),
    (
        "discourages_care", "blocker",
        "Discourages professional medical care. Never tell a reader to skip, delay or "
        "stop treatment — always point them to a clinician.",
        re.compile(
            r"\b(no\s+need\s+to\s+(see|consult|visit)\s+a?\s*(doctor|gp|physician|specialist))\b"
            r"|\b(avoid|skip|don'?t\s+bother\s+with)\s+(seeing\s+)?(a\s+)?(doctor|doctors|physicians?)\b"
            r"|\b(stop|discontinue|quit)\s+(taking\s+)?(your\s+)?(medication|medicines?|prescription|treatment)\b"
            r"|\binstead\s+of\s+(seeing\s+a\s+doctor|medical\s+treatment|prescribed\s+medication)\b"
        ),
    ),
    (
        "discourages_care_hi", "blocker",
        "Hindi text discourages seeing a doctor or continuing treatment. Always direct "
        "readers to a qualified clinician.",
        re.compile(r"(डॉक्टर\s*(के\s*पास\s*जाने)?\s*की\s*(कोई\s*)?ज़?रूरत\s*नहीं|दवा\s*बंद\s*कर\s*दें|इलाज\s*बंद\s*कर)"),
    ),
    (
        "diagnostic_claim", "blocker",
        "Diagnoses the reader directly. An article can describe symptoms; it cannot "
        "tell someone what they have.",
        re.compile(
            r"\byou\s+(definitely\s+|certainly\s+)?have\s+(ibs|ibd|gerd|celiac|coeliac|sibo|crohn'?s|colitis|cancer)\b"
            r"|\bthis\s+means\s+you\s+have\b"
            r"|\bdiagnose\s+yourself\b"
        ),
    ),
    (
        "unsourced_statistic", "warning",
        "Cites a specific statistic. Confirm the figure appears in the grounding "
        "sources, or replace it with a qualitative description.",
        re.compile(r"\b\d{1,3}(\.\d+)?\s?%|\b(\d+)\s+(in|out\s+of)\s+(\d+)\s+(people|patients|adults|women|men)\b"),
    ),
    (
        "unverifiable_citation", "warning",
        "References a study, journal or organisation that this app cannot verify. "
        "Either attach a real citation or remove the attribution.",
        re.compile(
            r"\b(a|the)\s+(19|20)\d{2}\s+(study|trial|paper|review|meta-analysis)\b"
            r"|\baccording\s+to\s+(a\s+)?(study|research|researchers|scientists|the\s+(who|nih|cdc|nhs|icmr|aiims))\b"
            r"|\b(published\s+in|journal\s+of)\s+[a-z]"
        ),
    ),
    (
        "superlative_claim", "warning",
        "Uses an unqualified superlative. Search raters treat 'the best/most effective' "
        "health claims as unsupported unless attributed.",
        re.compile(
            r"\b(the\s+)?(best|most\s+effective|safest|strongest|number\s+one|#1)\s+"
            r"(treatment|remedy|cure|supplement|probiotic|diet|food|medicine)\b"
        ),
    ),
    (
        "risky_self_treatment", "warning",
        "Suggests self-treating without clinical oversight. Add an explicit "
        "'talk to your doctor first' qualifier next to this advice.",
        re.compile(
            r"\b(self[-\s]?medicat\w*|treat\s+it\s+at\s+home\s+without|no\s+prescription\s+(needed|required))\b"
        ),
    ),
    (
        "fear_marketing", "notice",
        "Uses fear-based framing. Health content converts better and rates better on "
        "trust when it stays calm and factual.",
        re.compile(r"\b(dangerous(ly)?\s+(toxic|deadly)|silent\s+killer|destroy(ing)?\s+your\s+(gut|body)|shocking\s+truth)\b"),
    ),
]

# Recognised in either language; mirrors app/quality.py::DISCLAIMER_MARKERS.
_DISCLAIMER_MARKERS = (
    "disclaimer", "not a substitute for professional", "consult a", "consult your doctor",
    "अस्वीकरण", "चिकित्सा सलाह",
)

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

    for code, severity, message, pattern in _RULES:
        target = text if code.endswith("_hi") else lower
        for match in pattern.finditer(target):
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

    if text.strip() and not any(marker in lower for marker in _DISCLAIMER_MARKERS):
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
        "checked_rules": len(_RULES) + 2,
    }
