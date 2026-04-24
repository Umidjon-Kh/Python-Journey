from collections.abc import Hashable, Sequence
from threading import Lock
from time import monotonic

from ..core import CacheEntry, Policy


class TTLPolicy(Policy):
    """
    Realization of policy Time-To-Live (TTL) for cache.
    This policy decides entry is valid right now or not by checking entry's last acces.
    Supports absolute (from creating) and sliding (from last acces) modes.

    Particular qualities:
        - On absolute TTL (sliding=False) time of life is determines using created time of entry
        - On sliding TTl (sliding=True) time of life is determines using last acces to entry
        - Expired entries returns to evict_candidates for forcely removing tham from storage.
        - For aviding race condition in multi-threading enviroment uses lock
    """

    def __init__(self, ttl: float, sliding: bool = False) -> None:
        """
        Initializes params when creating an instance.
        Args:
            ttl: Life time of entries
            sliding: if True turns on sliding mode, otherwise does nothing.
        """
        self._ttl = ttl
        self._sliding = sliding
        self._expiry: dict[Hashable, float] = {}
        self._lock: Lock = Lock()

    def _get_expiry_time(self, entry: CacheEntry) -> float:
        """
        Determines time of expiriation and returns it to called internal method.
        Depending on the mode determines using created_at or last_acces.
        """
        base = entry.last_accessed if self._sliding else entry.created_at
        return base + self._ttl

    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when adding entry to storage via orchestrator to
        save expiriation time of life.
        """
        with self._lock:
            self._expiry[key] = self._get_expiry_time(entry)

    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when upper layer objects (ordinary orchestrator)
        gained acces to entry in storage.
        Updates time only if sliding mode is on.
        """
        if not self._sliding:
            return
        with self._lock:
            self._expiry[key] = self._get_expiry_time(entry)

    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """Calls when removing entry from storage to forget expiry date about entry."""
        with self._lock:
            self._expiry.pop(key, None)

    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        """
        Returns sequence that contains of entry's keys that
        expiriation date is raised.
        If expired entries more than limit returns only first entries count that
        not bigger that size of limit.
        """
        # I could make this whole code shorter using syntactic sugar,
        # but then the execution of the method depends on the number of records,
        # it depends only on the limit
        now = monotonic()
        with self._lock:
            expired = []
            count = 0
            for key, deadline in self._expiry.items():
                if count >= limit:
                    break
                if deadline <= now:
                    expired.append(key)
                    count += 1

        return expired

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        """
        Checks if entry's life time has expired.
        If key is not exist in dictionary, count as valid.
        But this not gonna happen ever cause we always store entry deadline if
        that was added to storage, in this block of code i use get method only to
        accord safe guard code style.
        """
        with self._lock:
            exp = self._expiry.get(key, None)

        if exp is None:
            # Thats not should happen.
            return True
        return monotonic() <= exp

    def on_clear(self) -> None:
        """
        Restores internal stats to default(currently only to empty dict),
        calls when clearing storage data.
        """
        with self._lock:
            self._expiry.clear()
