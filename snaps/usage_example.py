"""
Snaps — Usage Examples
======================
Demonstrates all features of the @snap decorator:
    1. Basic caching (no policy) — with timing
    2. TTL policy
    3. LRU policy
    4. LFU policy
    5. TTL + LRU combined
    6. Template key
    7. Custom policy
    8. Custom storage
"""

import time
from collections.abc import Hashable, Sequence

from cacher.core import CacheEntry, Policy, Storage
from cacher.presentations import snap

# ─────────────────────────────────────────────────────────────────────────────
# 1. Basic caching — no policy, no limits
#    Entries live forever until manually cleared via .clear()
# ─────────────────────────────────────────────────────────────────────────────


@snap()
def slow_add(a: int, b: int) -> int:
    """Simulates a slow computation (e.g. DB query or API call)."""
    time.sleep(0.5)
    return a + b


print("=" * 60)
print("1. Basic caching — no policy")
print("=" * 60)

start = time.perf_counter()
result = slow_add(10, 20)
print(
    f"  First call  → result={result}, time={time.perf_counter() - start:.4f}s"
)  # ~0.5s

start = time.perf_counter()
result = slow_add(10, 20)
print(
    f"  Second call → result={result}, time={time.perf_counter() - start:.6f}s"
)  # ~0.000001s

start = time.perf_counter()
result = slow_add(10, 20)
print(
    f"  Third call  → result={result}, time={time.perf_counter() - start:.6f}s"
)  # ~0.000001s

print()
print("  NOTE: Without a policy, entries live forever.")
print("  You must clear manually when needed:")
slow_add.clear()  # type: ignore[stub]
print("  Cache cleared.")

start = time.perf_counter()
result = slow_add(10, 20)
print(
    f"  After clear → result={result}, time={time.perf_counter() - start:.4f}s"
)  # ~0.5s again
print("  Stats:", slow_add.stats())  # type: ignore[stub]
print()


# ─────────────────────────────────────────────────────────────────────────────
# 2. TTL policy — entries expire after N seconds
# ─────────────────────────────────────────────────────────────────────────────


@snap(ttl=(2, False))
def get_rate(currency: str) -> float:
    """Simulates fetching exchange rate from an API."""
    time.sleep(0.3)
    return 1.25


print("=" * 60)
print("2. TTL policy (2 seconds, absolute)")
print("=" * 60)

start = time.perf_counter()
get_rate("USD")
print(f"  First call  → time={time.perf_counter() - start:.4f}s")

start = time.perf_counter()
get_rate("USD")
print(f"  Second call → time={time.perf_counter() - start:.6f}s  (from cache)")

print("  Sleeping 2.1 seconds...")
time.sleep(2.1)

start = time.perf_counter()
get_rate("USD")
print(f"  After TTL   → time={time.perf_counter() - start:.4f}s  (recomputed)")
print()


# ─────────────────────────────────────────────────────────────────────────────
# 3. LRU policy — evicts least recently used entries
# ─────────────────────────────────────────────────────────────────────────────


@snap(lru=True, max_size=3, evictions_limit=1)
def load_user(user_id: int) -> dict:
    """Simulates loading a user from DB."""
    time.sleep(0.2)
    return {"id": user_id, "name": f"User {user_id}"}


print("=" * 60)
print("3. LRU policy (max_size=3)")
print("=" * 60)

for uid in [1, 2, 3]:
    start = time.perf_counter()
    load_user(uid)
    print(f"  load_user({uid}) → time={time.perf_counter() - start:.4f}s  (computed)")

start = time.perf_counter()
load_user(1)
print(
    f"  load_user(1) → time={time.perf_counter() - start:.6f}s  (from cache, moves to end)"
)

start = time.perf_counter()
load_user(4)
print(
    f"  load_user(4) → time={time.perf_counter() - start:.4f}s  (computed, user 2 evicted)"
)

start = time.perf_counter()
load_user(2)
print(
    f"  load_user(2) → time={time.perf_counter() - start:.4f}s  (recomputed, was evicted)"
)
print()


# ─────────────────────────────────────────────────────────────────────────────
# 4. LFU policy — evicts least frequently used entries
# ─────────────────────────────────────────────────────────────────────────────


@snap(lfu=True, max_size=3, evictions_limit=1)
def fetch_config(key: str) -> str:
    """Simulates fetching config value."""
    time.sleep(0.2)
    return f"value-{key}"


print("=" * 60)
print("4. LFU policy (max_size=3)")
print("=" * 60)

fetch_config("host")
fetch_config("port")
fetch_config("timeout")

for _ in range(4):
    fetch_config("host")

fetch_config("port")

start = time.perf_counter()
fetch_config("debug")
print(
    f"  fetch_config('debug')   → time={time.perf_counter() - start:.4f}s  (timeout evicted, freq=1)"
)

start = time.perf_counter()
fetch_config("timeout")
print(
    f"  fetch_config('timeout') → time={time.perf_counter() - start:.4f}s  (recomputed)"
)
print()


# ─────────────────────────────────────────────────────────────────────────────
# 5. TTL + LRU combined
# ─────────────────────────────────────────────────────────────────────────────


@snap(ttl=(5, False), lru=True, max_size=2, evictions_limit=1)
def get_post(post_id: int) -> dict:
    """Cached with both TTL (5s) and LRU (max 2 entries)."""
    time.sleep(0.2)
    return {"id": post_id, "title": f"Post {post_id}"}


print("=" * 60)
print("5. TTL + LRU combined (max_size=2, ttl=5s)")
print("=" * 60)

get_post(1)
get_post(2)

start = time.perf_counter()
get_post(1)
print(f"  get_post(1) → time={time.perf_counter() - start:.6f}s  (from cache)")

get_post(3)

start = time.perf_counter()
get_post(2)
print(
    f"  get_post(2) → time={time.perf_counter() - start:.4f}s  (recomputed, evicted by LRU)"
)
print()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Template key
# ─────────────────────────────────────────────────────────────────────────────


@snap(key="report:{year}-{month}:type-{report_type}")
def generate_report(year: int, month: int, report_type: str) -> dict:
    """Simulates heavy report generation."""
    time.sleep(0.4)
    return {"year": year, "month": month, "type": report_type, "rows": 1500}


print("=" * 60)
print("6. Template key")
print("=" * 60)

start = time.perf_counter()
generate_report(2025, 1, "sales")
print(f"  First call  → time={time.perf_counter() - start:.4f}s  (computed)")

start = time.perf_counter()
generate_report(2025, 1, "sales")
print(f"  Second call → time={time.perf_counter() - start:.6f}s  (from cache)")

start = time.perf_counter()
generate_report(2025, 1, "finance")
print(
    f"  Other type  → time={time.perf_counter() - start:.4f}s  (different key, computed)"
)
print()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Custom policy — MaxAccessPolicy
#    Entry is invalidated after N accesses
# ─────────────────────────────────────────────────────────────────────────────


class MaxAccessPolicy(Policy):
    """
    Invalidates entry after it has been accessed N times.
    Demonstrates how to plug any custom eviction logic into snaps.
    """

    requires_max_size: bool = False

    def __init__(self, max_accesses: int) -> None:
        self._max_accesses = max_accesses

    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        pass

    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        pass

    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        pass

    def on_clear(self) -> None:
        pass

    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        return []

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        return entry.access_count <= self._max_accesses


@snap(policies=[MaxAccessPolicy(max_accesses=3)])
def get_token(user_id: int) -> str:
    """Token is cached but invalidated after 3 accesses."""
    time.sleep(0.3)
    return f"token-{user_id}-{time.time():.0f}"


print("=" * 60)
print("7. Custom policy — MaxAccessPolicy (max 3 accesses)")
print("=" * 60)

for i in range(1, 6):
    start = time.perf_counter()
    get_token(42)
    elapsed = time.perf_counter() - start
    source = "computed" if elapsed > 0.1 else "from cache"
    print(f"  Access #{i} → time={elapsed:.4f}s  ({source})")

print()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Custom storage — VerboseStorage
#    Logs every operation — shows extensibility of storage layer
# ─────────────────────────────────────────────────────────────────────────────


class VerboseStorage(Storage):
    """
    Logs every storage operation to stdout.
    Demonstrates how to plug any storage backend into snaps.
    """

    def __init__(self) -> None:
        self._data: dict[Hashable, CacheEntry] = {}

    def get(self, key: Hashable):
        entry = self._data.get(key)
        print(f"    [storage.get]    → {'HIT' if entry else 'MISS'}")
        return entry

    def put(self, key: Hashable, entry: CacheEntry) -> None:
        print("    [storage.put]    → stored")
        self._data[key] = entry

    def delete(self, key: Hashable) -> None:
        print("    [storage.delete] → removed")
        self._data.pop(key, None)

    def contains(self, key: Hashable) -> bool:
        return key in self._data

    def size(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        print("    [storage.clear]  → all removed")
        self._data.clear()

    def keys(self) -> Sequence[Hashable]:
        return list(self._data.keys())


@snap(storage=VerboseStorage())
def compute_square(n: int) -> int:
    """Compute square with verbose storage logging."""
    time.sleep(0.1)
    return n * n


print("=" * 60)
print("8. Custom storage — VerboseStorage")
print("=" * 60)

print("  compute_square(5):")
compute_square(5)
print()
print("  compute_square(5) again:")
compute_square(5)
print()
print("  compute_square(7):")
compute_square(7)
