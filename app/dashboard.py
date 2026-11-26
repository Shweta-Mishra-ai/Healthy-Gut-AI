"""Generation history tracker for the dashboard, backed by SQLite.

See app/db.py for the persistence-lifetime caveat on ephemeral-disk hosts.
"""

import time

from app.db import get_connection, get_lock


class GenerationTracker:
    def __init__(self, max_entries: int = 5000):
        self._max_entries = max_entries

    def record(self, *, topic: str, provider: str, success: bool, out_of_scope: bool = False,
               word_count: int = 0, quality_score: int = 0, cached: bool = False,
               prompt_tokens: int = 0, completion_tokens: int = 0):
        conn = get_connection()
        now = time.time()
        with get_lock():
            conn.execute(
                """INSERT INTO generations
                   (timestamp, topic, provider, success, out_of_scope, word_count, quality_score, cached,
                    prompt_tokens, completion_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, topic, provider, int(success), int(out_of_scope), word_count, quality_score, int(cached),
                 prompt_tokens or 0, completion_tokens or 0),
            )
            conn.execute(
                "DELETE FROM generations WHERE id NOT IN (SELECT id FROM generations ORDER BY timestamp DESC LIMIT ?)",
                (self._max_entries,),
            )
            conn.commit()

    def summary(self, limit_recent: int = 20) -> dict:
        conn = get_connection()
        with get_lock():
            rows = conn.execute("SELECT * FROM generations ORDER BY timestamp DESC").fetchall()

        entries = [dict(r) for r in rows]
        for e in entries:
            e["success"] = bool(e["success"])
            e["out_of_scope"] = bool(e["out_of_scope"])
            e["cached"] = bool(e["cached"])

        total = len(entries)
        succeeded = [e for e in entries if e["success"]]
        out_of_scope = [e for e in entries if e["out_of_scope"]]
        failed = [e for e in entries if not e["success"] and not e["out_of_scope"]]

        provider_counts: dict[str, int] = {}
        for e in succeeded:
            provider_counts[e["provider"]] = provider_counts.get(e["provider"], 0) + 1

        avg_quality = round(sum(e["quality_score"] for e in succeeded) / len(succeeded), 1) if succeeded else 0
        avg_words = round(sum(e["word_count"] for e in succeeded) / len(succeeded), 1) if succeeded else 0
        cache_hit_rate = round(100 * sum(1 for e in succeeded if e["cached"]) / len(succeeded), 1) if succeeded else 0

        recent = entries[:max(1, min(limit_recent, 100))]
        generated = [e for e in succeeded if not e["cached"] and (e.get("prompt_tokens") or e.get("completion_tokens"))]
        total_tokens = sum((e.get("prompt_tokens") or 0) + (e.get("completion_tokens") or 0) for e in generated)

        return {
            # Every figure here covers the retained history only (the newest
            # history_limit generations), not all time — the page says so.
            "history_limit": self._max_entries,
            "total_requests": total,
            "succeeded": len(succeeded),
            "failed": len(failed),
            "out_of_scope": len(out_of_scope),
            "avg_quality_score": avg_quality,
            "avg_word_count": avg_words,
            "cache_hit_rate_percent": cache_hit_rate,
            # Provider tokens for articles a provider actually wrote (cached
            # and template articles cost nothing).
            "total_tokens": total_tokens,
            "avg_tokens_per_article": round(total_tokens / len(generated)) if generated else 0,
            "provider_breakdown": provider_counts,
            "recent": [
                {
                    "topic": e["topic"], "provider": e["provider"], "success": e["success"],
                    "out_of_scope": e["out_of_scope"],
                    "quality_score": e["quality_score"], "word_count": e["word_count"], "cached": e["cached"],
                }
                for e in recent
            ],
        }


tracker = GenerationTracker()
