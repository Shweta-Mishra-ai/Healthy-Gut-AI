import time
from app.cache import TTLCache


def test_ttl_cache_operations():
    cache = TTLCache(ttl_seconds=1, max_entries=2)

    # Set and get
    cache.set("key1", {"val": 1})
    assert cache.get("key1") == {"val": 1}

    # Max entries eviction
    cache.set("key2", {"val": 2})
    cache.set("key3", {"val": 3})  # should evict key1

    assert cache.get("key1") is None
    assert cache.get("key2") == {"val": 2}
    assert cache.get("key3") == {"val": 3}

    # Expiration
    time.sleep(1.1)
    assert cache.get("key2") is None
    assert cache.get("key3") is None
