from __future__ import annotations

from dataclasses import dataclass

from .path_locker import BasePathLocker
from .snapshots_registry_store import BaseSnapshotsRegistryStore


@dataclass(slots=True, frozen=True)
class ToolKit:
    """
    An immutable domain-level container that groups optional infrastructure
    helpers and makes them available to handlers that require them.

    ToolKit is created once during the assembly phase by Bootstrap and
    injected into every BaseHandler implementation via __init__. Handlers
    that do not need any of the tools simply ignore them.

    Why immutable:
        ToolKit is a configuration object assembled once at startup.
        Its references must not change at runtime to guarantee consistency
        across all handlers that share the same instance.

    Why not a domain object:
        ToolKit participates in Bootstrap assembly and is accepted by
        BaseHandler as a typed contract, but the ToolKit object itself does
        not participate in the daemon's pipeline and is used only with the
        handlers themselves.

    Why a typed container and not a plain dict:
        A plain dict would lose type safety,
        IDE autocompletion and semantic clarity.

    Why all handlers receive ToolKit even if they don't need it:
        Bootstrap operates only on abstractions and does not know which
        concrete handler needs which tool. Passing ToolKit to all handlers
        uniformly keeps Bootstrap simple and closed to modification when
        new handlers are added.

    Attributes:
        - ignoring_paths:      Shared dict[str, int] managed by Dispatcher.
                                   Handlers write paths they want suppressed.
                                   Dispatcher reads and decrements counters.
                                   Value of -1 means suppress indefinitely.
        - path_locker:         Helper for locking file system paths to prevent
                                   external modification during handler operations.
        - snapshots_registry_store:  Helper for creating, retrieving and managing
                                   file snapshots used by backup and restore handlers.
    """

    ignoring_paths: dict[str, int]
    path_locker: BasePathLocker
    snapshots_registry_store: BaseSnapshotsRegistryStore
