from abc import ABC, abstractmethod
from collections.abc import Hashable, Mapping


class MetricsCollector(ABC):
    """
    Interface collector of metrics for cache.

    Designed to collect cache statistics: hits, misses, evictions and etc...
    Implementations can send metrics to the client, console, a file, Prometheus, StatD and etc..

    All methods receives key, it needed to give opportunity to create new features in future,
    for example: track smot used (hot!) entry keys, or miss_rate). But in realization it can be ignored.

    Thread-safety is not required at the interface level.
    Only required if the implementation uses in multi-threading enviroment.
    """

    @abstractmethod
    def hit(self, key: Hashable) -> None:
        """
        Records hits count (cache hit), increses hits count in every call.
        Calls by orchestrator, when entry is exists and its valid.
        """
        ...

    @abstractmethod
    def miss(self, key: Hashable) -> None:
        """
        Record misses count (cache miss), increases misses count in every call.
        Calls by orchestrator, when key is not exist or exists but its not valid.
        """
        ...

    @abstractmethod
    def evict(self, key: Hashable) -> None:
        """
        Records evictions count of entries from cache.
        Also calls by orchestrator when removing entry from cache.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Resets all metrics, calls by orchestrator when client needs to clear cache.
        """
        ...

    @abstractmethod
    def stats(self) -> Mapping:
        """
        Returns mapping object that includes to it metrics like:
            - hits: count of hits
            - misses: count of misses
            - evictions: count of evicted entries
            - hit_rate: hits / (hits + misses)
        """
        ...
