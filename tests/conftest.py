import os

for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "API_KEY"):
    os.environ.pop(var, None)

import pytest

from app.cache import article_cache
from app.db import reset_db_for_tests
from app.rate_limit import rate_limiter


@pytest.fixture(autouse=True)
def _reset_article_cache():
    """The article cache is a process-wide singleton keyed on the request
    fields, so two tests generating the same topic would silently share one
    result — the second seeing `cached: true` and skipping the code path it
    meant to exercise."""
    article_cache.clear()
    yield
    article_cache.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The rate limiter is a process-wide singleton. Without this, a growing
    test suite eventually exceeds RATE_LIMIT_PER_MINUTE purely from test
    volume, producing 429s that have nothing to do with what's being tested.
    Tests that specifically exercise rate limiting (test_rate_limiting,
    test_rate_limiter_recovers_after_window) already set/restore their own
    limit locally, so this default doesn't interfere with them."""
    rate_limiter._hits.clear()
    rate_limiter._limit = 100000
    yield
    rate_limiter._hits.clear()
    rate_limiter._limit = 10


@pytest.fixture(autouse=True)
def _reset_database():
    """Review/dashboard data now lives in a shared SQLite table (see app/db.py).
    Without a reset, tests asserting exact counts (e.g. test_tracker_summary_math)
    would see rows left over from earlier tests in the same session."""
    reset_db_for_tests()
    yield
    reset_db_for_tests()
