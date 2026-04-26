# ⚡ Snaps

> A snap — and your data is already there.

**Snaps** is a lightweight, extensible Python caching library built on clean hexagonal architecture.
Plug in any policy, any storage, any metrics — or use the smart defaults and forget about it.

---

## ✨ Features

- 🔌 **Fully extensible** — plug in custom policies, storages, and metrics collectors
- 🧠 **Built-in policies** — TTL, LRU, LFU, or combine them
- 🎯 **Template keys** — control your cache key format with `key="user-{user_id}"`
- 📊 **Stats built-in** — hits, misses, evictions, hit rate out of the box
- 🔒 **Thread-safe** — all built-in components use locks
- 🏛️ **Hexagonal architecture** — core ports are fully decoupled from infrastructure
- 🐍 **Pure Python** — zero dependencies, stdlib only

---

## 📦 Installation

```bash
pip install snaps-cacher
```

---

## 🚀 Quick Start

```python
from cacher.presentations import snap

@snap()
def get_user(user_id: int) -> dict:
    return fetch_from_db(user_id)  # called only once per unique user_id

get_user(1)   # fetches from DB
get_user(1)   # returns from cache instantly
```

---

## 📖 Usage

### Basic caching — no policy

Entries live forever until you clear manually.

```python
@snap()
def slow_compute(x: int) -> int:
    time.sleep(1)  # heavy computation
    return x * x

slow_compute(5)   # ~1s
slow_compute(5)   # ~0.000001s — from cache

slow_compute.clear()   # clear when needed
slow_compute.stats()   # {'metrics': {...}, 'storage': {'size': 0}}
```

---

### TTL — Time To Live

Entry expires after N seconds. Supports **absolute** and **sliding** modes.

```python
# Absolute TTL — expires N seconds after creation
@snap(ttl=(60, False))
def get_exchange_rate(currency: str) -> float:
    return fetch_rate(currency)

# Sliding TTL — TTL resets on every access
@snap(ttl=(60, True))
def get_session(session_id: str) -> dict:
    return load_session(session_id)
```

---

### LRU — Least Recently Used

Evicts the entry that hasn't been accessed for the longest time.
Requires `max_size` and `evictions_limit`.

```python
@snap(lru=True, max_size=1000, evictions_limit=10)
def load_product(product_id: int) -> dict:
    return db.fetch_product(product_id)
```

---

### LFU — Least Frequently Used

Evicts the entry that has been accessed the fewest times.
Requires `max_size` and `evictions_limit`.

```python
@snap(lfu=True, max_size=500, evictions_limit=5)
def get_config(key: str) -> str:
    return config_service.get(key)
```

---

### Combining policies

Policies work together — entry is invalid if **any** policy says so.

```python
# TTL expires after 5 minutes AND LRU keeps only 1000 entries
@snap(ttl=(300, False), lru=True, max_size=1000, evictions_limit=10)
def get_post(post_id: int) -> dict:
    return db.fetch_post(post_id)
```

---

### Template key

Control exactly how your cache key is formed.
Inspired by the idea from [EzyGang/py-cachify](https://github.com/EzyGang/py-cachify).

```python
@snap(key="report:{year}-{month}:type-{report_type}")
def generate_report(year: int, month: int, report_type: str) -> dict:
    return heavy_report_generation(year, month, report_type)

generate_report(2025, 1, "sales")    # key: "report:2025-1:type-sales"
generate_report(2025, 1, "finance")  # key: "report:2025-1:type-finance"
```

---

### Stats and clear

Every decorated function gets `.stats()` and `.clear()` attached automatically.

```python
@snap(lru=True, max_size=100, evictions_limit=5)
def fetch(x: int) -> int:
    return x * 2

fetch(1)
fetch(2)
fetch(1)  # hit

print(fetch.stats())
# {
#   'metrics': {
#       'hits': 1,
#       'misses': 2,
#       'evictions': 0,
#       'hit_rate': 0.333
#   },
#   'storage': {'size': 2}
# }

fetch.clear()  # reset everything
```

---

## 🔌 Extensibility

### Custom policy

```python
from cacher.core import Policy, CacheEntry
from collections.abc import Hashable, Sequence

class MaxAccessPolicy(Policy):
    """Invalidates entry after N accesses."""

    requires_max_size: bool = False

    def __init__(self, max_accesses: int) -> None:
        self._max_accesses = max_accesses

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        return entry.access_count <= self._max_accesses

    def on_add(self, key: Hashable, entry: CacheEntry) -> None: pass
    def on_access(self, key: Hashable, entry: CacheEntry) -> None: pass
    def on_remove(self, key: Hashable, entry: CacheEntry) -> None: pass
    def on_clear(self) -> None: pass
    def evict_candidates(self, limit: int) -> Sequence[Hashable]: return []


@snap(policies=[MaxAccessPolicy(max_accesses=3)])
def get_token(user_id: int) -> str:
    return generate_token(user_id)
```

---

### Custom storage

```python
from cacher.core import Storage, CacheEntry
from collections.abc import Hashable, Sequence

class RedisStorage(Storage):
    """Example: Redis-backed storage."""

    def __init__(self, client) -> None:
        self._client = client

    def get(self, key: Hashable) -> CacheEntry | None:
        ...

    def put(self, key: Hashable, entry: CacheEntry) -> None:
        ...

    # implement: delete, contains, size, clear, keys


@snap(storage=RedisStorage(redis_client))
def get_user(user_id: int) -> dict:
    return db.fetch_user(user_id)
```

---

### Custom metrics

```python
from cacher.core import MetricsCollector
from collections.abc import Hashable, Mapping

class PrometheusMetrics(MetricsCollector):
    """Send metrics to Prometheus."""

    def hit(self, key: Hashable) -> None:
        cache_hits_total.inc()

    def miss(self, key: Hashable) -> None:
        cache_misses_total.inc()

    def evict(self, key: Hashable) -> None:
        cache_evictions_total.inc()

    def reset(self) -> None: ...
    def stats(self) -> Mapping: ...


@snap(metrics=PrometheusMetrics())
def get_data(key: str) -> dict:
    return fetch(key)
```

---

## 🏛️ Architecture

Snaps is built on **hexagonal (ports & adapters) architecture**.
The core domain has zero knowledge of infrastructure.

```
snaps/cacher/
│
├── core/                    ← domain — no external dependencies
│   ├── entry.py             ← CacheEntry: value + metadata
│   └── ports/
│       ├── storage.py       ← Storage port (abstract)
│       ├── policy.py        ← Policy port (abstract)
│       ├── metrics.py       ← MetricsCollector port (abstract)
│       └── orchestrator.py  ← Orchestrator port (abstract)
│
├── storages/                ← infrastructure
│   └── memory.py            ← InMemoryStorage
│
├── policies/                ← plugins
│   ├── ttl.py               ← TTLPolicy
│   ├── lru.py               ← LRUPolicy
│   └── lfu.py               ← LFUPolicy
│
├── metrics/
│   └── memory.py            ← InMemoryMetrics
│
├── orchestrators/
│   ├── simple.py            ← SimpleOrchestrator (one policy)
│   └── composite.py         ← CompositeOrchestrator (many policies)
│
├── utils/
│   └── key_gen.py           ← auto key + template key generation
│
└── presentations/
    └── decorator.py         ← @snap — single entry point
```

---

## 🙏 Credits

- Template key generation idea inspired by [EzyGang/py-cachify](https://github.com/EzyGang/py-cachify) —
  a production-ready caching library with distributed locks support worth checking out.

---

## 📄 License

MIT © Umidjon Khodjaev
