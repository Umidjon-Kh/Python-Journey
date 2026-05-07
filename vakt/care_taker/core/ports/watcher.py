from __future__ import annotations

from abc import ABC, abstractmethod


class BaseWatcher(ABC):
    """
    Abstract base class for all file system watchers.

    A watcher is responsible for observing file system changes
    and producing Event objects, It has no knowledge of what happens to event
    after they are provided - that is the responsibility of the Dispatcher-layer.

    Implementations Example:
        - InotifyWatcher: Linux, uses inotify kernel subsystem.
        - WindowsWatcher: Windows, uses ReadDirectoryChangesW.
        - PollingWatcher: Cross-platform, uses os.stat() polling.

    Notes:
        - Watcher runs in its own thread (Watcher Thread).
        - It must be respect shutdown_event to stop gracefully.
        - It must never block indefinitely without checking shutdown_event.
        - Watcher has not knowledge where to subscribe, it
            only subscribes to provided paths, Providing those paths is
            responsibility of the bootstrap or any upper layer object.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Starts watching. Called once before the watcher loop begins.
        Uses to subscribe to all objects in provided paths. Initializes
        resources file descriptor and watch descriptor.
        After this runs Watcher Thread with self.events method.
        Why events method is splitted from start:
            This is done intentionally to avoid mixing
            two logics in one place, creating unnecessary noise that
            can interfere with the correct reading of the code, even if they are
            called in the same place.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stops watching and release all resources.
        Called when shutdown event is set.
        Uses to unsubscribe from all subcribed objects.
        """
        ...

    @abstractmethod
    def events(self) -> None:
        """
        Puts Events into a buffer as a file system changes are detected
        in subscribed objects. This method runs in a loop inside Watcher Thread.
        Must yield control periodically to allow shutdown checks.
        """
        ...
