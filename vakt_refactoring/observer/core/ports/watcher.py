from __future__ import annotations

from abc import ABC, abstractmethod


class BaseWatcher(ABC):
    """
    Abstract base class for all file system watchers.

    A Watcher is responsible for observing file system changes
    and producing Event objects. It has not knowledge of what happens
    to event after they are placed into the buffer - that is the
    responsibility of the Dispatcher layer objects.

    Watcher runs in its own thread (Watcher Thread) and continuously
    monitors subscribed paths for changes. When a change is detected,
    it creates a domain Event object and puts it into a thread-safe buffer
    that is shared with Dispatcher Thread.

    Implementations Example:
        - InotifyWatcher: Linux, uses inotify kernel subsystem.
        - FanotifyWatcher: Linux, uses fanotify kernel subsystem.
        - WindowsWatcher: Windows, uses ReadDirectoryChangesW.
        - PollingWatcher: Cross-platform, uses os.stat() polling.

    Rule of Path Syntax for all Implementations:
        /some/path/**   -> recursive: watches path and all subpaths in this path.
        /some/path/*    -> non-recursive: watches only direct contents of path.
        /some/path      -> no suffix: silently normalized to /some/path/* by
                            implementation.

    Why events() method is split from start():
        start() handles initialization and subscription - a one-time setup.
        events() handles the continuous monitoring loop - an ongoing process.
        Mixing both into start() would create unnecessary noise and make
        it harder to understand the lifecycle of the watcher.

    Notes:
        - Watcher runs in its own thread (Watcher Thread).
        - It must respect shutdown_event to stop gracefully.
        - It must never block indefinitely without checking shutdown_event.
        - Watcher has no knowledge of what to subscribe to - it only
            subscribes to provided paths. Providing those path is the
            responsibility of the bootstrap or any upper layer object.
        - Buffer and shutdown_event are provided via __init__ of the
            implementation. BaseWatcher does not enforce this contract
            because each implementation may require different parameters.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Subscribes to all provided paths and starts the Watcher Thread.
        Called once during bootstrap before the main loop begins.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Waits for the Watcher Thread  to finish after shutdown_event is set,
        then unsubscribes from all subscribed paths and releases all resources
        such as file descriptors and watch descriptors.
        Called once during graceful shutdown.
        """
        ...

    @abstractmethod
    def events(self) -> None:
        """
        Continuously reads file system events and puts them into the buffer.
        Runs in a loop inside the Watcher Thread until shutdown_event is set.
        Must check shutdown_event periodically to allow graceful shutdown.
        This method is the target of the Watcher Thread started in start()
        """
        ...
