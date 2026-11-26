"""Registered medical reviewers.

The "Reviewed by Dr. X, MD" line printed on published articles is a medical
trust claim. It used to come from whatever name and credential the person
approving typed into a prompt, with nothing checked, so anyone who could
approve could put any doctor's name on a public health article.

Reviewers are now configured by the operator — REVIEWERS_JSON (inline JSON)
or REVIEWERS_FILE (path to a JSON file) — as a list of
  {"id": "rao", "name": "Dr. Anita Rao", "credential": "MD (Gastroenterology)",
   "registration": "NMC/State council registration no."}
The operator is responsible for verifying each entry (for India, against the
NMC Indian Medical Register or the state medical council). When a registry is
configured, approving requires one of these reviewers and only their badge is
printed. Without a registry, a typed name is kept as a self-attested internal
record and is never printed on the article.
"""
import json
import os
import re

_UNSAFE = re.compile(r"[<>{}$`]")
_FIELDS = ("id", "name", "credential", "registration")


class ReviewerRegistryError(ValueError):
    pass


def parse_registry(raw: str) -> dict[str, dict]:
    if not raw.strip():
        return {}
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ReviewerRegistryError(f"reviewer registry is not valid JSON: {e}") from e
    if not isinstance(entries, list):
        raise ReviewerRegistryError("reviewer registry must be a JSON list")
    registry: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ReviewerRegistryError(f"reviewer #{index} is not an object")
        cleaned = {f: str(entry.get(f, "") or "").strip() for f in _FIELDS}
        if not cleaned["id"] or not cleaned["name"]:
            raise ReviewerRegistryError(f"reviewer #{index} needs an 'id' and a 'name'")
        if any(_UNSAFE.search(v) for v in cleaned.values()):
            raise ReviewerRegistryError(f"reviewer {cleaned['id']!r} contains disallowed characters")
        if cleaned["id"] in registry:
            raise ReviewerRegistryError(f"duplicate reviewer id {cleaned['id']!r}")
        registry[cleaned["id"]] = cleaned
    return registry


def load_registry() -> dict[str, dict]:
    path = os.getenv("REVIEWERS_FILE", "").strip()
    if path:
        with open(path, encoding="utf-8") as f:
            return parse_registry(f.read())
    return parse_registry(os.getenv("REVIEWERS_JSON", ""))


REVIEWERS = load_registry()


def registry_enabled() -> bool:
    return bool(REVIEWERS)


def get_reviewer(reviewer_id: str) -> dict | None:
    return REVIEWERS.get((reviewer_id or "").strip())


def public_list() -> list[dict]:
    return [dict(r) for r in REVIEWERS.values()]
