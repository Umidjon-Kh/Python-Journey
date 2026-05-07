from __future__ import annotations

from collections.abc import Sequence
from os import path as pth
from os import walk
from queue import Queue
from threading import Event as ShutdownEvent
from threading import Thread
from time import monotonic
from typing import Optional

from inotify_simple import INotify, flags

from ...core import (
    BaseWatcher,
    Event,
    EventType,
)

_FLAGS = flags


_MASK = (
    _FLAGS.CREATE
    | _FLAGS.DELETE
    | _FLAGS.MODIFY
    | _FLAGS.MOVED_FROM
    | _FLAGS.MOVED_TO
    | _FLAGS.ATTRIB
)

_MASK_TO_EVENT_TYPE: dict[int, EventType] = {
    _FLAGS.CREATE: EventType.FILE_CREATED,
    _FLAGS.DELETE: EventType.FILE_DELETED,
    _FLAGS.MODIFY: EventType.FILE_MODIFIED,
    _FLAGS.MOVED_FROM: EventType.FILE_MOVED,
    _FLAGS.MOVED_TO: EventType.FILE_MOVED,
    _FLAGS.ATTRIB: EventType.FILE_METADATA_CHANGED,
}

_DIR_MASK_TO_EVENT_TYPE: dict[int, EventType] = {
    _FLAGS.CREATE: EventType.DIR_CREATED,
    _FLAGS.DELETE: EventType.DIR_DELETED,
    _FLAGS.MOVED_FROM: EventType.DIR_MOVED,
    _FLAGS.MOVED_TO: EventType.DIR_MOVED,
    _FLAGS.ATTRIB: EventType.DIR_METADATA_CHANGED,
}


class InotifyWatcher(BaseWatcher):
    """
    Linux implementation of BaseWatcher using notify kernel subsystem
    via inotify_simple library.

    Watches all provided paths recursively by subscribing to each
    directory individually. Automatically subscribe to newly created
    directories to maintain recursive watching

    Compared to other Implementations:
        - InotifyWatcher does not attach directly to the target object.
            Instead, it subscribes to events on the parent directory,
            using those events to infer changes to the child.
            This design significantly reduces resource consumption, avoids
            exhausting the system's watch descriptor limits, and lowers
            memory overhead when operating at scale with large number of objects.
        - InotifyWatcher receives notifications about file system changes only after
            they already occured, not before they take place. As a result, it has no
            capability to preempt, prevent, or intercept an operation prior to
            it's execution.

    Notes:
        - Requires Linux kernel with inotify support.
        - Each watched directory consumes one inotify watch descriptor.
            Linux has a system limit on watch descriptors (default 8192/60K).
            Can be increased via changing value of:
                /proc/sys/fs/inotify/max_user_watches.
        - If you are using this implementation, ensure that target is not a file,
            as individual files will not be tracked correctly. Due to
            optimization constraints, the InotifyWatcher does not attach directly
            to the object itself.If you need to monitor a specific file, you must
            provide it's parent directory.

    """

    def __init__(
        self,
        paths: Sequence[str],
        buffer: Queue[Event],
        shutdown_event: ShutdownEvent,
        read_timeout: int = 1000,
    ) -> None:
        """
        Initializes all attributes of the watcher instance.

        Args:
            paths: Sequence of absolute paths to watch.
                By default watcher subscribes only for children of this paths
                but if you want to subscribe to all objects in this paths recursively
                use "/**" instead of "/*".
            buffer: Thread-safe buffer to put Events into.
            shutdown_event: Flag to stop the watcher gracefully if system asks for it.
            read_timeout: Timeout in milliseconds for inotify.read().
                            Controls how often shutdown_event is checked.
        """
        self._paths: Sequence[str] = paths
        self._buffer: Queue[Event] = buffer
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._read_timeout: int = read_timeout
        self._inotify: INotify = INotify()
        self._subsribed_objects: dict[int, str] = {}
        self._thread: Thread = Thread(target=self.events, daemon=True, name="watcher")

    def start(self) -> None:
        """
        Starts watching. Called once before the watcher loop begins.
        Uses to subsribe to all objects in provided paths. If you
        want to subsribe recursively to all objects in paths ensure
        that you used "/**" instead of "/*". Ensure that the upper layer object
        is validated before receiving paths to InotifyWatcher cause path must end
        with "/**" or "/*". In short: Validating agruments before providing
        them is responsibility of upper layer objects like bootstrap.

        After that runs self.events inside the Watcher Thread that puts
        Events into a buffer. If you want to know why this done like this
        read BaseWatcher class start method docs to understand it.!
        """
        for path in self._paths:
            if path.endswith("/**"):
                self._subscribe_recursive(path.rsplit("/", maxsplit=1)[0])
            else:
                self._subscribe_nonrecursive(path.rsplit("/", maxsplit=1)[0])

        self._thread.start()

    def _subscribe_nonrecursive(self, path: str) -> None:
        """
        Subscribes only for children in provided paths.
        Not subscribes to children's objects in paths.
        Uses only when needed to subsribe non-recursive.
        """
        wd = self._inotify.add_watch(path, _MASK)
        self._subsribed_objects[wd] = path

    def _subscribe_recursive(self, path: str) -> None:
        """
        Recursively subscribes to path and all its subdirectories.
        Ensure that provided path is not a file.
        """
        for root, _, _ in walk(path):
            wd = self._inotify.add_watch(root, _MASK)
            self._subsribed_objects[wd] = root

    def stop(self) -> None:
        """
        Waits for Watcher Thread to finish last iteration in a loop
        after shutdown_event is set and after this unsubscribes from
        all watched paths and closes inotify file descriptor.
        Called once if upper layer object asks for gracefully shutdown.
        """
        self._thread.join()

        for wd in self._subsribed_objects:
            self._inotify.rm_watch(wd)

        self._subsribed_objects.clear()
        self._inotify.close()

    def events(self) -> None:
        """
        Puts Events into a buffer as a file system changes are detected.
        Periodically checks shutdown_event is set or not via read_timeout delay.
        Automatically subsribes to newly created directories to watch them them too
        without stoping the procces.
        """
        while not self._shutdown_event.is_set():
            inotify_events = self._inotify.read(timeout=self._read_timeout)

            for event in inotify_events:
                path = self._subsribed_objects.get(event.wd, None)

                if path is None:
                    continue

                full_path = pth.join(path, event.name)
                is_dir = bool(event.mask & _FLAGS.ISDIR)

                if is_dir and event.mask & _FLAGS.CREATE:
                    self._subscribe_recursive(full_path)

                event_type = self._resolve_event_type(event.mask, is_dir)

                if event_type is None:
                    continue

                domain_event = Event(
                    path=full_path,
                    event_type=event_type,
                    timestamp=monotonic(),
                )

                self._buffer.put(domain_event)

    def _resolve_event_type(self, mask: int, is_dir: bool) -> Optional[EventType]:
        """
        Maps inotify mask to EventType and returns it.
        Why returns annotation is Optional:
            It's done to stub strictly pyright linter.
            If it works correctly, It must never return NoneType object at all.
        """
        mapping = _DIR_MASK_TO_EVENT_TYPE if is_dir else _MASK_TO_EVENT_TYPE

        for flag, event_type in mapping.items():
            if mask & flag:
                return event_type

        return None
