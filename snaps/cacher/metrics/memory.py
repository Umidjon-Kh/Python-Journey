from collections.abc import Hashable, Mapping
from threading import Lock

from ..core import MetricsCollector


class InMemoryMetrics(MetricsCollector):
    """
    Realization of metrics collector that stores all stats in memory.
    Stores counter of hits, misses, evicts.
    Supports thread-safety and provides statistics.

    Stats Counters:
        - hits: general counter of hits (cache hit)
        - misses: general couner of missses (cache misses)
        - evictions: general counter of evictions (cache entries)

    All operations on counter is guarded for thread-safety.
    Also in this realization all arguments ignored
    cause it's default metrics collector that only collects basic needed metrics.
    """

    def __init__(self) -> None:
        """Initializes all counter with default values (zero)."""
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0
        self._lock: Lock = Lock()

    def hit(self, key: Hashable) -> None:
        """Increases value of hits counter."""
        with self._lock:
            self._hits += 1

    def miss(self, key: Hashable) -> None:
        """Increases value of misses counter."""
        with self._lock:
            self._misses += 1

    def evict(self, key: Hashable) -> None:
        """Increases value of evictions counter."""
        with self._lock:
            self._evictions += 1

    def reset(self) -> None:
        """Resets all metrics, calls by orchestrator when client needs to clear cashe."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> Mapping:
        """
        Returns mapping object that includes all internal stats (metrics).
        Also returns hits rate that needed to show user needs to cachify
        this callable or not cause it can be dont needed in some situtations.

        Metrics to return:
            - hits
            - misses
            - evictions
            - hit_rate: hits / (hits + misses)
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": hit_rate,
            }
