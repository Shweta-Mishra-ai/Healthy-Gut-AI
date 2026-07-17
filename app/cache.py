import hashlib
import time
import threading
from typing import Optional

from app.config import settings


class TTLCache:
    """In-memory TTL cache. Single-instance only.
    NOTE: for multi-instance/production deployments, replace with Redis
    so cache is shared across worker processes/dynos."""

    def __init__(self, ttl_seconds: int, max_entries: int):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def make_key(*parts: str) -> str:
        raw = "||".join(p.lower().strip() for p in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            if len(self._store) >= self._max:
                # evict oldest entry (simple FIFO eviction, good enough at this scale)
                oldest_key = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest_key]
            self._store[key] = (time.time() + self._ttl, value)

    def stats(self) -> dict:
        with self._lock:
            return {"entries": len(self._store), "max_entries": self._max, "ttl_seconds": self._ttl}


article_cache = TTLCache(settings.CACHE_TTL_SECONDS, settings.CACHE_MAX_ENTRIES)
