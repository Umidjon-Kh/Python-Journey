from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator

from ..event import Event


class BaseWatcher(ABC):
    """
    Abstract base class for all file system watchers.

    A watcher is responsible for observing file system changes
    and producing Event objects. It has no knowledge of what
    happens to events after they are provided - that is the
    responsibility of the Dispatcher.

    Impletentations:
        - InotifyWatcher: Linux, uses inotify kernel subsystem.
        - WindowsWatcher: Windows, uses ReadDirectoryChagesW.
        - PollingWatcher: Cross-platform, uses os.stat() polling.

    Notes:
        - Watcher runs in its own thread (Wathcer Thread).
        - It must be respect shutdown_event to stop gracefully.
        - It must never block indefinitely without checking shutdown_event.
        - Watcher has not knowledge where to subscribe it
            only subscribes to provied paths. To provide that paths is
            responsibilty of bootstrap or upper layer.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Starts watching. Called once before the watcher loop begins.
        Uses to subscribe to provided objects in paths. Initializes
        resources file descriptor and watch descriptor.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stops watching and release all resources.
        Called when shutdown_event is set.
        Uses to unsubscribe from subcribed objects.
        """
        ...

    @abstractmethod
    def events(self) -> Generator[Event, None, None]:
        """
        Yields Events as file system changes are detected
        in subscribed objects. This method runs in a loop inside Watcher Thread.
        Must yield control periodically to allow sutdown checks.
        """
        ...
