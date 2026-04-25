from collections.abc import Hashable, Mapping, Sequence
from threading import Lock
from typing import Any, Optional

from ..core import (
    NOT_FOUND,
    CacheEntry,
    MetricsCollector,
    Orchestrator,
    Policy,
    Storage,
)


class CompositeOrchestrator(Orchestrator):
    """
    Realization of composite orchestrator that manages with cache storage and several policies
    at the same time, if at least one of them was provided. That feature allows to combine
    multiple count of policies to work them together for example:
        TTL and LRU - TTL evicts only expired entries, LRU evicts - not recently used entries.
    Uses when needed a big responsibilty to wrok with cache.

    Compared to SimpleOrchestrator:
        - responsible for several count of policies, thats it.
    """

    def __init__(
        self,
        policies: Optional[Sequence[Policy]],
        storage: Storage,
        metrics: MetricsCollector,
        max_size: Optional[int],
        eviction_limit: Optional[int],
    ) -> None:
        """Initializes orchestrator all dependency attribute objects."""
        self._policies: Optional[Sequence[Policy]] = policies
        self._storage: Storage = storage
        self._metrics: MetricsCollector = metrics
        self._max_size: Optional[int] = max_size
        self._eviction_limit: Optional[int] = eviction_limit
        self._lock: Lock = Lock()

    def _force_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Removes entry from storage and notifies policies about that if at least was provided
        one policy. Calls only inside locker (thread-safety).
        Needs only for public methods to DRY (Do not Repeat Yourself).
        """
        self._storage.delete(key)

        if self._policies is not None:
            for policy in self._policies:
                policy.on_remove(key, entry)

    def _enforce_size_limit(self) -> None:
        """
        Evicts entries if size of storage raised max_size.
        Works only if at least was provided one policy and max_size.
        If policy or max_size or evictions_limit is not
        provived silently ignores and does nothing. Cause both three objects
        depends each other to work properly.

        Steps:
            While storage size is bigger that max_size:
               - requests all policies for evicting candidates (until raises evictions limit)
               - if policies returns empty sequence - breaks (infinity loop safety)
               - removes received keys from storage
               - increases evictions counter in metrics for al of them
        """
        if (
            self._policies is None
            or self._max_size is None
            or self._eviction_limit is None
        ):
            return

        while self._storage.size() > self._max_size:
            candidates = set()

            for policy in self._policies:
                for candidate in policy.evict_candidates(limit=self._eviction_limit):
                    candidates.add(candidate)
                    if len(candidates) >= self._eviction_limit:
                        break
                if len(candidates) >= self._eviction_limit:
                    break

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
        Returns value of entry under the provided key, if it exists,
        otherwise retruns NOT_FOUND object to avoid confusing NoneType object with not founded.
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                self._metrics.miss(key)
                return NOT_FOUND

            if self._policies is not None:
                for policy in self._policies:
                    if not policy.is_valid(key, entry):
                        self._force_remove(key, entry)
                        self._metrics.evict(key)
                        self._metrics.miss(key)
                        return NOT_FOUND

            entry.touch()

            if self._policies is not None:
                for policy in self._policies:
                    policy.on_access(key, entry)

            self._metrics.hit(key)

        return entry.value

    def put(self, key: Hashable, value: Any) -> None:
        """
        Wraps value into an entry object and adds it to the storage or updates.
        Notifies all polices about that if at least one of them was provided.
        """
        with self._lock:
            old_entry = self._storage.get(key)
            if old_entry is not None:
                self._force_remove(key, old_entry)

            entry = CacheEntry(value=value)

            self._storage.put(key, entry)

            if self._policies is not None:
                for policy in self._policies:
                    policy.on_add(key, entry)

            self._enforce_size_limit()

    def delete(self, key: Hashable) -> None:
        """
        Removes entry from storage and notifies all
        policies (if at leasst one of them was provided).
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is not None:
                self._force_remove(key, entry)

    def clear(self) -> None:
        """
        Completely resets storage and
        restores to default all policies and metrics internal stats.
        """
        with self._lock:
            self._storage.clear()
            if self._policies is not None:
                for policy in self._policies:
                    policy.on_clear()
            self._metrics.reset()

    def stats(self) -> Mapping:
        """
        Returns mapping object of stats.
        Includes statistics of metrics and storage.
        """
        with self._lock:
            stats = {}
            stats["metrics"] = self._metrics.stats()
            stats["storage"] = {"size": self._storage.size()}

        return stats
