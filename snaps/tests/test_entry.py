"""Tests for CacheEntry dataclass."""

import time

import pytest
from cacher.core import CacheEntry


def test_initial_values():
    """Entry initializes with correct default values."""
    entry = CacheEntry(value=42)
    assert entry.value == 42
    assert entry.access_count == 1
    assert entry.created_at > 0
    assert entry.last_accessed > 0
    assert round(entry.created_at, 1) == round(entry.last_accessed, 1)


def test_touch_returns_value():
    """touch() returns the cached value."""
    entry = CacheEntry(value="hello")
    assert entry.touch() == "hello"


def test_touch_increments_access_count():
    """touch() increments access_count on every call."""
    entry = CacheEntry(value=0)
    assert entry.access_count == 1
    entry.touch()
    assert entry.access_count == 2
    entry.touch()
    assert entry.access_count == 3


def test_touch_updates_last_accessed():
    """touch() updates last_accessed timestamp."""
    entry = CacheEntry(value=0)
    before = entry.last_accessed
    time.sleep(0.01)
    entry.touch()
    assert entry.last_accessed > before


def test_touch_does_not_change_created_at():
    """touch() never modifies created_at."""
    entry = CacheEntry(value=0)
    created = entry.created_at
    entry.touch()
    entry.touch()
    assert entry.created_at == created


def test_value_can_be_none():
    """None is a valid cached value."""
    entry = CacheEntry(value=None)
    assert entry.value is None
    assert entry.touch() is None


def test_value_can_be_any_type():
    """Entry accepts any type as value."""
    for val in [0, "", [], {}, False, 3.14, (1, 2)]:
        entry = CacheEntry(value=val)
        assert entry.value == val
