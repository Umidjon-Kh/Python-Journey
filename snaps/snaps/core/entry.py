from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    """
    Smart Dataclass that determines expired auto and
    stores all needed attributes to work properly and support any type of policies.
    """

    # main attr
    value: Any

    # sub attributes for determining time of leaving
    created_at: float = field(default_factory=monotonic, init=False)
    last_accessed: float = field(default_factory=monotonic, init=False)

    # sub attribute for counting how many times called
    hits: int = 0

    def is_expired(self, ttl: float, sliding: bool) -> bool:
        """
        Determine whether this cache entry has expired.

        Returns:
            bool:
                True if the entry has exceeded its TTL.
                False if still valid or if no TTL is configured.

        Expiration rules:
            sliding=False:
                created_at + ttl

            sliding=True:
                last_accessed + ttl
        """
        base_time = self.last_accessed if sliding else self.created_at
        return monotonic() >= (base_time + ttl)

    def touch(self) -> Any:
        """
        Mark the entry as accessed and return the stored value.

        Side effects:
            - Increments hit counter
            - Updates last_accessed timestamp
            - Extends lifetime when sliding=True

        Returns:
            Any:
                The cached value.

        Typical usage:
            return entry.touch()
        """
        self.hits += 1
        self.last_accessed = monotonic()
        return self.value
