"""Human-review workflow for generated articles, backed by SQLite.

Every successful generation is registered here as a 'draft'. A human
reviewer can approve or reject it before it's considered publish-ready.
This is the trust layer real health-content teams need — no article should
go live without a person confirming the medical framing is sound.

See app/db.py for the persistence-lifetime caveat on ephemeral-disk hosts.
"""

import json
import time
import uuid
from enum import Enum

from app.db import get_connection, get_lock


class ReviewStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class ReviewNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class ReviewStore:
    def __init__(self, max_entries: int = 1000):
        self._max_entries = max_entries

    def register(self, article_result: dict, topic: str, primary_keyword: str) -> str:
        article_id = uuid.uuid4().hex[:12]
        now = time.time()
        article_json = json.dumps(article_result, ensure_ascii=False)
        quality_score = article_result.get("quality", {}).get("score")
        word_count = article_result.get("metrics", {}).get("wordCount")
        provider_used = article_result.get("provider_used")

        conn = get_connection()
        with get_lock():
            conn.execute(
                """INSERT INTO reviews
                   (id, topic, primary_keyword, status, quality_score, word_count,
                    provider_used, created_at, reviewed_at, reviewer_note, article_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (article_id, topic, primary_keyword, ReviewStatus.draft.value, quality_score,
                 word_count, provider_used, now, None, None, article_json),
            )
            # Keep only the most recent max_entries rows overall.
            conn.execute(
                "DELETE FROM reviews WHERE id NOT IN (SELECT id FROM reviews ORDER BY created_at DESC LIMIT ?)",
                (self._max_entries,),
            )
            conn.commit()
        return article_id

    def get(self, article_id: str) -> dict:
        conn = get_connection()
        with get_lock():
            row = conn.execute("SELECT * FROM reviews WHERE id = ?", (article_id,)).fetchone()
        if not row:
            raise ReviewNotFoundError(f"No article found with id '{article_id}'")
        return self._row_to_full_dict(row)

    def set_status(self, article_id: str, new_status: ReviewStatus, note: str = "",
                    reviewer_name: str = "", reviewer_credential: str = "") -> dict:
        conn = get_connection()
        with get_lock():
            row = conn.execute("SELECT status FROM reviews WHERE id = ?", (article_id,)).fetchone()
            if not row:
                raise ReviewNotFoundError(f"No article found with id '{article_id}'")
            if row["status"] != ReviewStatus.draft.value:
                raise InvalidTransitionError(
                    f"Article '{article_id}' is already '{row['status']}' — only drafts can be reviewed."
                )
            now = time.time()
            conn.execute(
                """UPDATE reviews SET status = ?, reviewed_at = ?, reviewer_note = ?,
                   reviewer_name = ?, reviewer_credential = ? WHERE id = ?""",
                (new_status.value, now, note or None, reviewer_name or None, reviewer_credential or None, article_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM reviews WHERE id = ?", (article_id,)).fetchone()
        return self._row_to_full_dict(updated)

    def list_queue(self, status: str = "draft", limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 200))
        conn = get_connection()
        with get_lock():
            rows = conn.execute(
                "SELECT * FROM reviews WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [self._row_to_summary_dict(r) for r in rows]

    def counts(self) -> dict:
        conn = get_connection()
        with get_lock():
            rows = conn.execute("SELECT status, COUNT(*) AS c FROM reviews GROUP BY status").fetchall()
        counts = {"draft": 0, "approved": 0, "rejected": 0}
        for r in rows:
            counts[r["status"]] = r["c"]
        counts["total"] = sum(counts.values())
        return counts

    @staticmethod
    def _reviewer_badge(d: dict) -> str | None:
        name = d.get("reviewer_name")
        credential = d.get("reviewer_credential")
        if name and credential:
            return f"Reviewed by {name}, {credential}"
        if name:
            return f"Reviewed by {name}"
        return None

    @classmethod
    def _row_to_full_dict(cls, row) -> dict:
        d = dict(row)
        d["article"] = json.loads(d.pop("article_json"))
        d["reviewer_badge"] = cls._reviewer_badge(d)
        return d

    @classmethod
    def _row_to_summary_dict(cls, row) -> dict:
        d = dict(row)
        d.pop("article_json", None)
        d["reviewer_badge"] = cls._reviewer_badge(d)
        return d


review_store = ReviewStore()
