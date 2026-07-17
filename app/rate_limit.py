import time
import threading
from collections import defaultdict

from app.config import settings


class RateLimiter:
    """Sliding-window rate limiter, per client key (IP).
    NOTE: in-memory only -> resets on restart, not shared across instances.
    For real multi-instance production, swap for Redis-backed limiter
    (e.g. redis + fixed window counter, or a library like slowapi+redis)."""

    def __init__(self, limit_per_minute: int):
        self._limit = limit_per_minute
        self._window = 60.0
        self._hits: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self._window
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self._limit:
                retry_after = int(self._window - (now - hits[0])) + 1
                return False, retry_after
            hits.append(now)
            return True, 0


rate_limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE)
