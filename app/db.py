"""SQLite persistence layer for review history and generation dashboard data.

IMPORTANT DEPLOYMENT NOTE: on hosts with ephemeral filesystems (e.g. Render's
free tier), this database file is wiped on every restart/redeploy/spin-down —
same lifetime as the in-memory stores it replaces. It gives real persistence
within a running instance (multiple requests, multiple hours of uptime) and
is ready to work unchanged the moment DATABASE_PATH points at a real
persistent disk or volume. It is not, by itself, a guarantee of permanent
storage on every host.

Uses Python's stdlib sqlite3 — no extra dependency. A single shared
connection protected by a lock keeps this simple and correct at this scale;
if concurrent write volume ever becomes a bottleneck, that's the signal to
move to Postgres, not to fix within this file.
"""

import sqlite3
import threading

from app.config import settings

_lock = threading.Lock()
_conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.row_factory = sqlite3.Row


def init_db():
    with _lock:
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                primary_keyword TEXT NOT NULL,
                status TEXT NOT NULL,
                quality_score INTEGER,
                word_count INTEGER,
                provider_used TEXT,
                created_at REAL NOT NULL,
                reviewed_at REAL,
                reviewer_note TEXT,
                article_json TEXT NOT NULL
            )
        """)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status)")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_created ON reviews(created_at)")

        _conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                topic TEXT NOT NULL,
                provider TEXT,
                success INTEGER NOT NULL,
                out_of_scope INTEGER NOT NULL DEFAULT 0,
                word_count INTEGER DEFAULT 0,
                quality_score INTEGER DEFAULT 0,
                cached INTEGER NOT NULL DEFAULT 0
            )
        """)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_generations_timestamp ON generations(timestamp)")
        _conn.commit()


def get_connection() -> sqlite3.Connection:
    return _conn


def get_lock() -> threading.Lock:
    return _lock


def reset_db_for_tests():
    """Test-only helper: wipes all rows. Never call outside the test suite."""
    with _lock:
        _conn.execute("DELETE FROM reviews")
        _conn.execute("DELETE FROM generations")
        _conn.commit()


init_db()
