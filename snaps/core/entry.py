import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    """
    Represents a cache entry with metadata required for eviction policies (LRU, LFU) and validation (TTL).

    Attributes:
        value: Cached value of any type.
        created_at: Monotonic timestamp of entry creation (used for absolute TTL).
        last_accessed: Monotonic timestamp of the last access (used for sliding TTL and LRU).
        access_count: Number of times the entry has been accessed (used for LFU).

    Notes:
        - Uses time.monotonic() to avoid jumps due to system clock adjustments.
        - slots=True drastically reduces memory overhead for millions of entries.
    """

    value: Any
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)
    access_count: int = 0

    def touch(self) -> Any:
        """
        Updates metadata on access and returns the cached value.

        Returns:
            The cached value, allowing chaining like `entry.touch()`.
        """
        self.last_accessed = time.monotonic()
        self.access_count += 1
        return self.value
