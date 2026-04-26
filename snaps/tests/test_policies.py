"""Tests for TTLPolicy, LRUPolicy, LFUPolicy."""

import time

import pytest
from cacher.core import CacheEntry
from cacher.policies import LFUPolicy, LRUPolicy, TTLPolicy

# ─────────────────────────────────────────────
# TTLPolicy
# ─────────────────────────────────────────────


class TestTTLPolicy:
    def test_is_valid_before_expiry(self):
        """Entry is valid before TTL expires."""
        policy = TTLPolicy(ttl=10)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        assert policy.is_valid("k", entry) is True

    def test_is_valid_after_expiry(self):
        """Entry is invalid after TTL expires."""
        policy = TTLPolicy(ttl=0.05)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        time.sleep(0.1)
        assert policy.is_valid("k", entry) is False

    def test_on_remove_cleans_expiry(self):
        """on_remove() removes key from internal expiry dict."""
        policy = TTLPolicy(ttl=10)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        policy.on_remove("k", entry)
        # After removal, key not in expiry → treated as valid (safe guard)
        assert policy.is_valid("k", entry) is True

    def test_evict_candidates_returns_expired(self):
        """evict_candidates() returns expired keys."""
        policy = TTLPolicy(ttl=0.05)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        time.sleep(0.1)
        candidates = policy.evict_candidates(limit=10)
        assert "k" in candidates

    def test_evict_candidates_respects_limit(self):
        """evict_candidates() returns at most limit keys."""
        policy = TTLPolicy(ttl=0.05)
        for i in range(10):
            e = CacheEntry(value=i)
            policy.on_add(f"k{i}", e)
        time.sleep(0.1)
        candidates = policy.evict_candidates(limit=3)
        assert len(candidates) <= 3

    def test_sliding_ttl_extends_on_access(self):
        """Sliding TTL resets on access — entry stays valid."""
        policy = TTLPolicy(ttl=0.15, sliding=True)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)

        # Access before expiry to extend lifetime
        time.sleep(0.1)
        entry.touch()
        policy.on_access("k", entry)

        # Without sliding this would expire — with sliding it should still be valid
        time.sleep(0.1)
        assert policy.is_valid("k", entry) is True

    def test_on_clear_resets_state(self):
        """on_clear() empties internal expiry dict."""
        policy = TTLPolicy(ttl=0.05)
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        policy.on_clear()
        time.sleep(0.1)
        # After clear, key is gone — is_valid returns True (safe guard for missing key)
        assert policy.is_valid("k", entry) is True


# ─────────────────────────────────────────────
# LRUPolicy
# ─────────────────────────────────────────────


class TestLRUPolicy:
    def test_is_valid_always_true(self):
        """LRU does not invalidate entries — always returns True."""
        policy = LRUPolicy()
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        assert policy.is_valid("k", entry) is True

    def test_evict_candidates_returns_oldest(self):
        """evict_candidates() returns least recently used key first."""
        policy = LRUPolicy()
        for key in ["a", "b", "c"]:
            policy.on_add(key, CacheEntry(value=1))

        # Access b and c — a becomes LRU
        policy.on_access("b", CacheEntry(value=1))
        policy.on_access("c", CacheEntry(value=1))

        candidates = policy.evict_candidates(limit=1)
        assert candidates[0] == "a"

    def test_on_access_moves_to_end(self):
        """on_access() makes key most recently used."""
        policy = LRUPolicy()
        for key in ["a", "b", "c"]:
            policy.on_add(key, CacheEntry(value=1))

        # Access a — now b is LRU
        policy.on_access("a", CacheEntry(value=1))
        candidates = policy.evict_candidates(limit=1)
        assert candidates[0] == "b"

    def test_on_remove_removes_key(self):
        """on_remove() removes key from internal order."""
        policy = LRUPolicy()
        entry = CacheEntry(value=1)
        policy.on_add("a", entry)
        policy.on_add("b", entry)
        policy.on_remove("a", entry)
        candidates = policy.evict_candidates(limit=10)
        assert "a" not in candidates

    def test_on_clear_resets_state(self):
        """on_clear() empties internal order dict."""
        policy = LRUPolicy()
        policy.on_add("a", CacheEntry(value=1))
        policy.on_clear()
        assert policy.evict_candidates(limit=10) == []


# ─────────────────────────────────────────────
# LFUPolicy
# ─────────────────────────────────────────────


class TestLFUPolicy:
    def test_is_valid_always_true(self):
        """LFU does not invalidate entries — always returns True."""
        policy = LFUPolicy()
        entry = CacheEntry(value=1)
        policy.on_add("k", entry)
        assert policy.is_valid("k", entry) is True

    def test_evict_candidates_returns_least_frequent(self):
        """evict_candidates() returns least frequently used key."""
        policy = LFUPolicy()
        for key in ["a", "b", "c"]:
            policy.on_add(key, CacheEntry(value=1))

        # Access a many times — b and c remain freq=1
        for _ in range(5):
            entry = CacheEntry(value=1)
            for _ in range(_):
                entry.touch()
            policy.on_access("a", entry)

        candidates = policy.evict_candidates(limit=1)
        assert candidates[0] in ("b", "c")

    def test_on_remove_removes_key(self):
        """on_remove() removes key from internal buckets."""
        policy = LFUPolicy()
        entry = CacheEntry(value=1)
        policy.on_add("a", entry)
        policy.on_remove("a", entry)
        candidates = policy.evict_candidates(limit=10)
        assert "a" not in candidates

    def test_on_clear_resets_state(self):
        """on_clear() empties all internal state."""
        policy = LFUPolicy()
        policy.on_add("a", CacheEntry(value=1))
        policy.on_clear()
        assert policy.evict_candidates(limit=10) == []
