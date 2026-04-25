from collections.abc import Hashable, Mapping
from threading import Lock
from typing import Any, Optional

from ..core import (
    CacheEntry,
    MetricsCollector,
    Orchestrator,
    Policy,
    Storage,
)

# Created to avoid confusing a not found object with
# a NoneType object value of entries
NOT_FOUND = object()


class SimpleOrchestrator(Orchestrator):
    """
    Realization of simple orchestrator that manages with a cache storage and
    only with a sinlge policy, uses when needed simlpied and lighetr version of cacher.

    SimpleOrchestrator is responsible for:
        - storage of data (Storage)
        - application of policy (Policy)
        - collecting metrics (MetricsCollector)
        - thread0safety (Lock)
        - cache size control (max_size)
        - limit of evictions when cache is raised max size (eviction limit)

    Logic of work procces:
        - get: checks for contains -> validity -> updates metadata -> notifies policy
        - put: adds/updates entry -> calls eviction when raised max size
        - delete/clear: removing and notifying policy
        - stats: returns stats of metrics and storage
    """

    def __init__(
        self,
        policy: Policy,
        storage: Storage,
        metrics: MetricsCollector,
        max_size: int,
        eviction_limit: int,
    ) -> None:
        """Initializes orchestrator all dependency attribute objects."""
        self._policy: Policy = policy
        self._storage: Storage = storage
        self._metrics: MetricsCollector = metrics
        self._max_size: int = max_size
        self._eviction_limit: int = eviction_limit
        self._lock: Lock = Lock()

    def _force_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Removes entry from storage and notifies policy about that.
        Calls only inside locker (thread-safety).
        Needs only for public methods to DRY (Do no Repeat Yourself)
        """
        self._storage.delete(key)
        self._policy.on_remove(key, entry)

    def _enforce_size_limit(self) -> None:
        """
        Evicts entries if size of storage raised max_size.

        Steps:
            1. If max_size is not provided, does nothing
                    (if not provided by default it would be
                       infinity number that was received from upper layer objects).
            2. While size is bigger that max_size:
                - requests policy for evicting candidates (until raises evictions limit)
                - if policy returns empty sequence - breaks (safety)
                - removes received key froms storage
                - increases evictions counter in metrics
        """
        while self._storage.size() > self._max_size:
            candidates = self._policy.evict_candidates(limit=self._eviction_limit)
            if not candidates:
                break

            for candidate in candidates:
                entry = self._storage.get(candidate)
                if entry is None:
                    continue

                self._force_remove(candidate, entry)
                self._metrics.evict(candidate)

    def get(self, key: Hashable) -> Optional[Any]:
        """
        Returns value of entry under the provided key, if it exists, otherwise
        returns _NOT_FOUND object to avoid confusing NoneType object with not founded.

        How it works:
            1. Locker blocks acces to other threads (thread-safety).
            2. Getts entry from storage.
            3. If entry is not found in storage, increases misses count and return NOT_FOUND.
            4. If entry is founded but policy decides this entry is not valid removes it and
                                    increases misses count after returns NOT_FOUND.
            5. If entry is exists and it's valid:
                - updates metadata of entry (entry.touch())
                - notifies policy (policy.on_acces())
                - increases hits count in metrics
                - returns value of entry
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                self._metrics.miss(key)
                return NOT_FOUND

            if not self._policy.is_valid(key, entry):
                self._force_remove(key, entry)
                self._metrics.miss(key)
                self._metrics.evict(key)
                return NOT_FOUND

            entry.touch()
            self._policy.on_access(key, entry)
            self._metrics.hit(key)

        return entry.value

    def put(self, key: Hashable, value: Any) -> None:
        """
        Wraps value into an entry object and adds it to the storage or updates.

        How it works:
            1. Locker blocks acces to other threads (thread-safety).
            2. If key is exists in storage, removes it and notifies policy.
            3. Wraps value into an entry object.
            4. Stores it to the storage.
            5. Notifies policy (on_add)
            6. Checks storage raised max size or not.
        """
        with self._lock:
            old_entry = self._storage.get(key)
            if old_entry is not None:
                self._force_remove(key, old_entry)

            entry = CacheEntry(value=value)

            self._storage.put(key, entry)
            self._policy.on_add(key, entry)
            self._enforce_size_limit()

    def delete(self, key: Hashable) -> None:
        """Removes entry from storage and notifies policy."""
        with self._lock:
            entry = self._storage.get(key)
            if entry is not None:
                self._force_remove(key, entry)

    def clear(self) -> None:
        """
        Completely resets storage and
        restores to default all policy and metrics internal stats.
        """
        with self._lock:
            self._storage.clear()
            self._policy.on_clear()
            self._metrics.reset()

    def stats(self) -> Mapping:
        """
        Returns mapping object of stats.
        Includes statistics of metric and storage.
        """
        with self._lock:
            stats = {}
            stats["metrics"] = self._metrics.stats()
            stats["storage"] = {"size": self._storage.size()}

        return stats
