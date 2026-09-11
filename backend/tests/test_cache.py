"""Cache layer: Redis path, in-memory fallback, and blast radius.

The last group matters most — cache.py's Redis client is shared with
token_store, so a cache operation that reaches beyond cache keys can undo
authentication state.
"""

from __future__ import annotations

import time

import pytest

from app.core import token_store
from app.core.cache import TTL, Cache, _MemStore, cache


# ── In-memory store ───────────────────────────────────────────────────────────

def test_mem_store_round_trips():
    m = _MemStore()
    m.set("k", {"a": 1}, 60)
    assert m.get("k") == {"a": 1}


def test_mem_store_expires_entries():
    m = _MemStore()
    m.set("k", "v", 0)
    time.sleep(0.01)
    assert m.get("k") is None


def test_mem_store_miss_returns_none():
    assert _MemStore().get("nope") is None


def test_mem_store_prefix_flush_is_scoped():
    m = _MemStore()
    m.set("quote:A", 1, 60)
    m.set("quote:B", 2, 60)
    m.set("news:A", 3, 60)
    m.flush("quote:")
    assert m.get("quote:A") is None and m.get("quote:B") is None
    assert m.get("news:A") == 3


def test_mem_store_full_flush_clears_everything():
    m = _MemStore()
    m.set("a", 1, 60)
    m.flush()
    assert m.size() == 0


# ── Redis-backed cache ────────────────────────────────────────────────────────

def test_cache_uses_redis_when_connected():
    assert cache.backend == "redis", "tests are not exercising the Redis path"


def test_cache_round_trips_through_redis():
    cache.set("test:key", {"x": [1, 2, 3]}, "market")
    assert cache.get("test:key") == {"x": [1, 2, 3]}


def test_cache_miss_returns_none():
    assert cache.get("test:definitely-absent") is None


def test_cache_delete_removes_the_key():
    cache.set("test:del", 1, "market")
    cache.delete("test:del")
    assert cache.get("test:del") is None


def test_cache_applies_the_category_ttl():
    cache.set("test:ttl", 1, "search")
    ttl = cache._redis.ttl("test:ttl")
    assert 0 < ttl <= TTL["search"]


def test_unknown_category_falls_back_to_a_default_ttl():
    cache.set("test:unknown", 1, "not-a-real-category")
    assert 0 < cache._redis.ttl("test:unknown") <= 600


def test_non_json_serialisable_values_are_coerced_not_crashed():
    from datetime import datetime
    cache.set("test:dt", {"when": datetime(2025, 1, 1)}, "market")
    assert isinstance(cache.get("test:dt")["when"], str)


def test_malformed_cached_json_is_treated_as_a_miss():
    """A value written by something else (or a partial write) must not take
    down the reader."""
    cache._redis.set("test:corrupt", "{not valid json")
    assert cache.get("test:corrupt") is None


# ── Degradation ───────────────────────────────────────────────────────────────

def test_reads_fall_back_to_memory_when_redis_errors():
    c = Cache()

    class _Broken:
        def get(self, *a, **k):
            raise ConnectionError("redis down")

        def setex(self, *a, **k):
            raise ConnectionError("redis down")

    c._redis = _Broken()
    c._mem.set("k", "memvalue", 60)
    assert c.get("k") == "memvalue"


def test_writes_fall_back_to_memory_when_redis_errors():
    c = Cache()

    class _Broken:
        def setex(self, *a, **k):
            raise ConnectionError("redis down")

        def get(self, *a, **k):
            raise ConnectionError("redis down")

    c._redis = _Broken()
    c.set("k", "v", "market")
    assert c._mem.get("k") == "v", "a Redis write failure lost the value entirely"


def test_connect_to_an_unreachable_redis_degrades_silently():
    c = Cache()
    c.connect("redis://127.0.0.1:1/0")
    assert c.backend == "memory"
    c.set("k", "v", "market")
    assert c.get("k") == "v"


def test_stats_never_raise():
    assert "backend" in cache.stats()


def test_stats_expose_no_key_contents():
    cache.set("quote:SECRET", {"password": "hunter2"}, "market")
    blob = str(cache.stats())
    assert "hunter2" not in blob and "SECRET" not in blob


# ── Blast radius ──────────────────────────────────────────────────────────────

def test_prefix_flush_does_not_touch_unrelated_keys():
    cache.set("quote:A", 1, "market")
    cache.set("news:A", 2, "market")
    cache.flush("quote:")
    assert cache.get("quote:A") is None
    assert cache.get("news:A") == 2


def test_full_flush_does_not_destroy_session_revocation_state():
    """cache.py and token_store share one Redis client and one keyspace. A
    full `cache.flush()` issues KEYS * / DEL *, so it also deletes
    auth:session:*:revoked — silently un-revoking every killed session and
    reviving every blocklisted access token."""
    token_store.revoke_session("sid-under-test")
    token_store.revoke_access_jti("jti-under-test", 3600)
    assert token_store.is_access_revoked("jti-under-test", "sid-under-test") is True

    cache.flush()

    assert token_store.is_access_revoked("jti-under-test", "sid-under-test") is True, (
        "flushing the cache cleared the auth blocklist and session-revocation keys — "
        "a cache flush silently reinstates logged-out and revoked sessions"
    )


def test_full_flush_does_not_destroy_refresh_rotation_pointers():
    """Same keyspace problem seen from the refresh side: losing
    auth:session:{sid}:current_jti resets the rotation chain, so a
    previously-rotated-away refresh token is accepted again."""
    token_store.start_session("sid-rotate", "jti-1")
    cache.flush()
    assert cache._redis.get("auth:session:sid-rotate:current_jti") == "jti-1", (
        "a cache flush wiped the refresh-token rotation chain — replayed "
        "refresh tokens stop being detected"
    )
