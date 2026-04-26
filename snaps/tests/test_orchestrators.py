"""Tests for SimpleOrchestrator and CompositeOrchestrator."""

import time

import pytest
from cacher.core import NOT_FOUND
from cacher.metrics import InMemoryMetrics
from cacher.orchestrators import CompositeOrchestrator, SimpleOrchestrator
from cacher.policies import LRUPolicy, TTLPolicy
from cacher.storages import InMemoryStorage


def make_simple(policy=None, max_size=None, evictions_limit=None):
    return SimpleOrchestrator(
        policy=policy,
        storage=InMemoryStorage(),
        metrics=InMemoryMetrics(),
        max_size=max_size,
        eviction_limit=evictions_limit,
    )


def make_composite(policies=None, max_size=None, evictions_limit=None):
    return CompositeOrchestrator(
        policies=policies,
        storage=InMemoryStorage(),
        metrics=InMemoryMetrics(),
        max_size=max_size,
        eviction_limit=evictions_limit,
    )


# ─────────────────────────────────────────────
# SimpleOrchestrator
# ─────────────────────────────────────────────


class TestSimpleOrchestrator:
    def test_get_missing_returns_not_found(self):
        """get() returns NOT_FOUND for missing key."""
        orc = make_simple()
        assert orc.get("missing") is NOT_FOUND

    def test_put_and_get(self):
        """put() stores value and get() retrieves it."""
        orc = make_simple()
        orc.put("k", 42)
        assert orc.get("k") == 42

    def test_none_is_valid_cached_value(self):
        """None can be cached and retrieved correctly."""
        orc = make_simple()
        orc.put("k", None)
        result = orc.get("k")
        assert result is None
        assert result is not NOT_FOUND

    def test_get_increments_hits(self):
        """Successful get() increments hits counter."""
        orc = make_simple()
        orc.put("k", 1)
        orc.get("k")
        stats = orc.stats()
        assert stats["metrics"]["hits"] == 1

    def test_get_missing_increments_misses(self):
        """Missing get() increments misses counter."""
        orc = make_simple()
        orc.get("missing")
        stats = orc.stats()
        assert stats["metrics"]["misses"] == 1

    def test_delete_removes_entry(self):
        """delete() removes stored entry."""
        orc = make_simple()
        orc.put("k", 1)
        orc.delete("k")
        assert orc.get("k") is NOT_FOUND

    def test_delete_missing_does_not_raise(self):
        """delete() silently ignores missing keys."""
        orc = make_simple()
        orc.delete("nonexistent")

    def test_clear_resets_everything(self):
        """clear() removes all entries and resets metrics."""
        orc = make_simple()
        orc.put("a", 1)
        orc.put("b", 2)
        orc.get("a")
        orc.clear()

        assert orc.get("a") is NOT_FOUND
        assert orc.stats()["metrics"]["hits"] == 0
        assert orc.stats()["storage"]["size"] == 0

    def test_ttl_invalidates_entry(self):
        """TTLPolicy causes get() to return NOT_FOUND after expiry."""
        orc = make_simple(policy=TTLPolicy(ttl=0.05))
        orc.put("k", 99)
        time.sleep(0.1)
        assert orc.get("k") is NOT_FOUND

    def test_lru_evicts_oldest(self):
        """LRUPolicy evicts least recently used entry when max_size reached."""
        orc = make_simple(
            policy=LRUPolicy(),
            max_size=2,
            evictions_limit=1,
        )
        orc.put("a", 1)
        orc.put("b", 2)
        orc.get("a")  # a is now most recently used
        orc.put("c", 3)  # b should be evicted

        assert orc.get("b") is NOT_FOUND
        assert orc.get("a") == 1
        assert orc.get("c") == 3

    def test_stats_returns_correct_structure(self):
        """stats() returns mapping with metrics and storage keys."""
        orc = make_simple()
        stats = orc.stats()
        assert "metrics" in stats
        assert "storage" in stats
        assert "size" in stats["storage"]


# ─────────────────────────────────────────────
# CompositeOrchestrator
# ─────────────────────────────────────────────


class TestCompositeOrchestrator:
    def test_get_missing_returns_not_found(self):
        """get() returns NOT_FOUND for missing key."""
        orc = make_composite()
        assert orc.get("missing") is NOT_FOUND

    def test_put_and_get(self):
        """put() stores value and get() retrieves it."""
        orc = make_composite()
        orc.put("k", "value")
        assert orc.get("k") == "value"

    def test_none_is_valid_cached_value(self):
        """None can be cached and retrieved correctly."""
        orc = make_composite()
        orc.put("k", None)
        result = orc.get("k")
        assert result is None
        assert result is not NOT_FOUND

    def test_ttl_and_lru_combined(self):
        """TTL + LRU together — both policies apply."""
        orc = make_composite(
            policies=[TTLPolicy(ttl=0.05), LRUPolicy()],
            max_size=2,
            evictions_limit=1,
        )
        orc.put("a", 1)
        orc.put("b", 2)

        # b is LRU — gets evicted on next put
        orc.get("a")
        orc.put("c", 3)
        assert orc.get("b") is NOT_FOUND

        # TTL expires a and c
        time.sleep(0.1)
        assert orc.get("a") is NOT_FOUND
        assert orc.get("c") is NOT_FOUND

    def test_clear_resets_all_policies(self):
        """clear() resets storage, all policies, and metrics."""
        orc = make_composite(
            policies=[TTLPolicy(ttl=10), LRUPolicy()],
            max_size=10,
            evictions_limit=2,
        )
        orc.put("k", 1)
        orc.get("k")
        orc.clear()

        assert orc.get("k") is NOT_FOUND
        assert orc.stats()["metrics"]["hits"] == 0
