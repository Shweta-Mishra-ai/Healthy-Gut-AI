"""Curated gut-health knowledge base for retrieval-augmented generation.

The entries live in knowledge_base.json next to this file — general
medical/nutrition knowledge written for this project, not copied from any
single source. Keeping them as data means adding or correcting an entry is
an edit to one JSON object, reviewable on its own, with no Python involved.

Each entry needs: id (unique), topic, title, content. The file is validated
when it's loaded, so a malformed entry stops the app at startup with the
offending entry named, instead of silently degrading retrieval.
"""
import json
import os

KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.json")
REQUIRED_FIELDS = ("id", "topic", "title", "content")


class KnowledgeBaseError(ValueError):
    pass


def validate_entries(entries) -> list[dict]:
    if not isinstance(entries, list) or not entries:
        raise KnowledgeBaseError("knowledge base must be a non-empty JSON list")
    seen = set()
    for index, entry in enumerate(entries):
        where = f"entry #{index}" + (f" ({entry.get('id')!r})" if isinstance(entry, dict) and entry.get("id") else "")
        if not isinstance(entry, dict):
            raise KnowledgeBaseError(f"{where} is not an object")
        for field in REQUIRED_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise KnowledgeBaseError(f"{where} is missing a non-empty '{field}'")
        if entry["id"] in seen:
            raise KnowledgeBaseError(f"{where} duplicates id {entry['id']!r}")
        seen.add(entry["id"])
    return entries


def load_knowledge_base(path: str = KNOWLEDGE_BASE_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return validate_entries(json.load(f))


KNOWLEDGE_BASE = load_knowledge_base()
