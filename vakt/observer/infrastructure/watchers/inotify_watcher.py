from __future__ import annotations

from collections.abc import Sequence
from os import path as pth
from os import walk
from queue import Queue
from threading import Event as ShutdownEvent
from threading import Thread
from time import monotonic

from inotify_simple import INotify
from inotify_simple import flags as _FLAGS

from ...core import BaseWatcher, Event
from ..semantic_types import InotifyEventType

_PENDING__MAX_ITERATIONS: int = 2
"""
Number of read() iterations a MOVED_FROM event is kept in pending
before being emitted as DELETED. Iterations count is used instead of
one iteration to reduce false deletions in case MOVED_TO arrives in the
next batch due to timing between kernel delivery and read() batching.
"""

_READ_TIMEOUT: int = 500
"""
Maximum milliseconds inotif.read() blocks waiting for events.
Controls how oftern the main loop checks the shutdown event and
flushes expired pending moves.
"""

_MASK: int = (
    _FLAGS.CREATE
    | _FLAGS.DELETE
    | _FLAGS.ATTRIB
    | _FLAGS.ACCESS
    | _FLAGS.OPEN
    | _FLAGS.CLOSE_WRITE
    | _FLAGS.CLOSE_NOWRITE
    | _FLAGS.MOVED_FROM
    | _FLAGS.MOVED_TO
    | _FLAGS.EXCL_UNLINK
    | _FLAGS.DONT_FOLLOW
)
"""
Combined inotify mask applied to every watch descriptor.
System events IN_IGNORED, IN_UNMOUNT and IN_Q_OVERFLOW are delivered
by the kernel regardless of the mask and are handled internally
Two specific flags IN_EXCL_UNLINK and IN_DONT_FOLLOW serves for:
    - IN_EXCL_UNLINK:
        supresses events for files deleted from the directory,
        but still open by another process, reducing noise.
    - IN_DONT_FOLLOW:
        prevents following symlinks when adding watches,
        keeping observation within the expected directory tree.
"""

_FILE_MASK_TO_EVENT: dict[int, InotifyEventType] = {
    _FLAGS.ACCESS: InotifyEventType.FILE_ACCESSED,
    _FLAGS.CREATE: InotifyEventType.FILE_CREATED,
    _FLAGS.DELETE: InotifyEventType.FILE_DELETED,
    _FLAGS.OPEN: InotifyEventType.FILE_OPENED,
    _FLAGS.CLOSE_NOWRITE: InotifyEventType.FILE_CLOSED_NO_WRITE,
    _FLAGS.CLOSE_WRITE: InotifyEventType.FILE_CLOSED_WRITE,
    _FLAGS.ATTRIB: InotifyEventType.FILE_METADATA_CHANGED,
}  # type: ignore[assignment]

_DIR_MASK_TO_EVENT: dict[int, InotifyEventType] = {
    _FLAGS.ACCESS: InotifyEventType.DIR_ACCESSED,
    _FLAGS.CREATE: InotifyEventType.DIR_CREATED,
    _FLAGS.DELETE: InotifyEventType.DIR_DELETED,
    _FLAGS.ATTRIB: InotifyEventType.DIR_METADATA_CHANGED,
    _FLAGS.OPEN: InotifyEventType.DIR_OPENED,
}  # type: ignore[assignment]


class InotifyWatcher(BaseWatcher):
    """
    Linux inotify-based implementation of BaseWatcher.

    Runs a dedicated daemon thrad that reads inotify events and
    translates them into domain Event object placed into the shared
    buffer for the DIspatcher to consume.

    Compared to other Implementations:
        - InotifyWatcher does not attach directly to the target object.
            Instead, it sbuscribes to events on the parent directory,
            using those events to infer changes to the child.
            This design significantly reduces resource consumption,
            avoids exhausting the system's watcher descriptor limits, and
            lowers memory overhead when operating at scale with a large number
            of objects in a file system.
        - InotifyWatcher receives notifications about file system changes only
            after they already occured, not before they take place. As a result,
            it has no capability to preempt, prevent, or intercept an operation
            prior to it is execution.

    MOVED_FROM / MOVED_TO Pairing:
        Inotify delivers moves as two seperated events sharing a cookie.
        MOVED_FROM is stored in pending until MOVED_TO arrives.
        If MOVED_TO does not arrive within _PENDING_MAX_ITERATIONS
        iterations it means the object is moved to outside of watchnig paths
        and MOVED_FROM is emitted as DELETED preserving the original timestamp.

    RENAMED vs MOVED:
        Both are delivered via MOVED_FROM / MOVED_TO pairs.
        If the parent directory is the same -> RENAMED.
        If the parent directory differs     -> MOVED.

    MOVED_TO without pending:
        The object arrived from outside the watching paths.
        Emitted as CREATED. If it is a directory it is also
        subsribed according to the subscription mode of its parent.

    System Events:
        IN_MOVED, IN_UNMOUNT -> watched descriptor removed from registry.
                                rm watch is not called: kernel already
                                invalidated the descriptor.
        IN_Q_OVERFLOW:       -> events were lost, full rescan performed.

    Notes:
        - Requires Linux kernel with inotify support.
        - The thread is daemon so it does not block process exit.
            It means InotifyWatcher respects shutdown_event and gracefully
            stops after sending all last received events.
        - Each watched directory consumer one inotify watch descriptor.
            Linux has a system limit on watch descriptors (default 8192/60K).
            Can be increased via changing value of:
                /proc/sys/fs/inotify/max_user_watches.
        - If a path in paths_to_observe points directly to a file,
            InotifyWatcher automatically subscribes to its parent directory
            instead. Events for that file will be observed via the parent watch.
        - Automatically subscribes to newly created diectories to provide
            information about changes on it, even if the parent directory
            has not been designed for recursive tracking.
    """

    def __init__(
        self,
        shutdown_event: ShutdownEvent,
        buffer: Queue[Event],
        paths_to_observe: Sequence[str],
    ) -> None:
        """
        Initializes all atributes of the watcher instance,

        Args:
            paths_to_observe: Sequence of absolute paths to watch,
                                By default watcher subscribes only for children of this paths
                                but if you want to subscribe to all objects recursively, ensure
                                that the provided path is ends with "/**" suffix, instead of "/*".
            buffer:           Thread-safe buffer to put Events into.
            shutdown_event:   Flag to stop watcher gracefully if system asks for it.
        """
        self._paths_to_observe: Sequence[str] = paths_to_observe
        self._buffer: Queue[Event] = buffer
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._inotify: INotify = INotify()
        self._subscribed_objects: dict[int, str] = {}
        self._pending: dict[int, tuple[Event, int]] = {}
        self._thread: Thread = Thread(target=self.events, daemon=True, name="watcher")

    def start(self) -> None:
        """
        Subscribes to all provided paths and starts the Watcher Thread
        that keeps watching to all provided paths while shutdown_event is not
        set. Called once to start the daemon.

        If you want to know about why watching events is splitted from start method
        read BaseWatcher class docs to understand it.!
        """
        self._scan()
        self._thread.start()

    def stop(self) -> None:
        """
        Waits for Watcher Thread to finish last iterations in a loop
        after shutdon_event is set, then starts unsubsribing from all
        subscribed paths and releases all resources closing
        inotify file descriptor. Called once if upper layer object asks for
        gracefully shutdown.
        """
        self._thread.join()
        self._unsubscribe_all()
        self._inotify.close()

    def events(self) -> None:
        """
        Continuously reads inotify events and puts domain Event objects
        into the buffer. Runs in a loop inside the Watcher Thread and
        periodiclaly checks shutdown_event is set or not via _READ_TIMEOUT delay.
        Automatically subsribes to newly created directories to watch them too
        without stopping the process.
        Flushes expired pending moves at the end of every iteration to ensure
        MOVED_TO events within the same batch are paired before expiry is evaluated.
        """
        while not self._shutdown_event.is_set():
            inotify_events = self._inotify.read(timeout=_READ_TIMEOUT)

            for ie in inotify_events:
                # 1.Case: watching paths is deleted or unmounted
                if ie.mask & _FLAGS.IGNORED or ie.mask & _FLAGS.UNMOUNT:
                    self._subscribed_objects.pop(ie.wd, None)
                    continue

                # 2.Case: Events were lost due to buffer overflow
                if ie.mask & _FLAGS.Q_OVERFLOW:
                    self._rescan()
                    continue

                # 3.Case: Received file system event
                path = self._subscribed_objects.get(ie.wd)

                # 1.Scenario: Invalid watch descrptor
                if path is None:
                    # watch descriptor was removed during rescan but
                    # kernel had already queued this event.
                    continue

                full_path = pth.join(path, ie.name)
                is_dir = bool(ie.mask & _FLAGS.ISDIR)

                # 2.Scenario: Received MOVED_FROM event
                if ie.mask & _FLAGS.MOVED_FROM:
                    event_type = (
                        InotifyEventType.DIR_MOVED
                        if is_dir
                        else InotifyEventType.FILE_MOVED
                    )
                    event = Event(
                        path=full_path,
                        event_type=event_type,  # type: ignore[assignment]
                        timestamp=monotonic(),
                    )
                    self._pending[ie.cookie] = (event, 0)
                    continue

                # 3.Scenario: Received MOVED_TO event
                if ie.mask & _FLAGS.MOVED_TO:
                    self._handle_moved_to(full_path, ie.cookie, is_dir)
                    continue

                # 4.Scenario: Received CREATE event
                if is_dir and ie.mask & _FLAGS.CREATE:
                    self._subscribe_new_dir(full_path)

                # 5.Scenario: Received regular non specific event
                event_type = self._resolve_event_type(ie.mask, is_dir)
                if event_type is None:
                    continue

                self._buffer.put(
                    Event(
                        path=full_path,
                        event_type=event_type,
                        timestamp=monotonic(),
                    )
                )

            self._flush_expired_pending()

    def _scan(self) -> None:
        """
        Subscribe to all paths and normalizes them in place.

        Paths without a recognized suffix are silently normalized
        to non-recursive so upper layer are not burdened with strict
        sytax requirements. After the first call self._paths contains
        only normalized entries making all subsequent checks against
        paths unambiguous.
        """
        normalized: list[str] = []

        for path in self._paths_to_observe:
            if path.endswith("/**"):
                normalized.append(path)
                self._subscribe_recursive(path.rsplit("/", maxsplit=1)[0])
            elif path.endswith(("/*", "/")):
                normalized.append(path if path.endswith("/*") else path + "*")
                self._subscribe_nonrecursive(path.rsplit("/", maxsplit=1)[0])
            else:
                if not pth.exists(path):
                    continue
                if not pth.isdir(path):
                    path = path.rsplit("/", maxsplit=1)[0]
                normalized.append(path + "/*")
                self._subscribe_nonrecursive(path)

    def _subscribe_recursive(self, path: str) -> None:
        """
        Subscribes to path and all of its subdirectories recursively.

        Uses try/except around add_watch rather than exists() because
        a directory can be deleted between os.walk yielding it and
        ad_watch being called (TOCTOU). os.walk itself does not raise
        on missing directories so only add_watch needs protection.
        """
        for root, _, _ in walk(path):
            try:
                wd = self._inotify.add_watch(root, _MASK)
                self._subscribed_objects[wd] = root
            except OSError:
                pass

    def _subscribe_nonrecursive(self, path: str) -> None:
        """
        Subscribes to a single directory without entering subdirectories.

        Skips silently if the path does not exist. This can happend during
        rescan if the directory was deleted while events were being lost.
        """
        if not pth.exists(path):
            return
        try:
            wd = self._inotify.add_watch(path, _MASK)
            self._subscribed_objects[wd] = path
        except OSError:
            pass

    def _subscribe_new_dir(self, path: str) -> None:
        """
        Subscribes to a newly created or moved-in directory.

        Determines subscription mode by looking up the parent in
        self._paths_to_observe. If the parent was subscribed non-recursively
        the new directory is also subscribes non-recursively.
        In all other cases recurisve is used - this covers both
        explicit recursive paths and directories added transitively
        via a recursive subscription whose base is not the immediate parent.
        """
        parent = path.rsplit("/", maxsplit=1)[0]

        for watched_path in self._paths_to_observe:
            base = watched_path.rsplit("/", maxsplit=1)[0]
            if base == parent and not watched_path.endswith("/**"):
                self._subscribe_nonrecursive(path)
                return

        self._subscribe_recursive(path)

    def _unsubscribe_all(self) -> None:
        """Removes all active watch descriptor and clears the registry."""
        for wd in self._subscribed_objects:
            try:
                self._inotify.rm_watch(wd)
            except OSError:
                pass

        self._subscribed_objects.clear()

    def _rescan(self) -> None:
        """
        Unsubscribes all watches and rescans from scratch.

        Called on IN_Q_OVERFLOW when events have been lost. Does not
        call stop() to avoid joining the current thread from within
        itself which would cause a deadlock.
        """
        self._unsubscribe_all()
        self._scan()

    def _handle_moved_to(
        self,
        full_path: str,
        cookie: int,
        is_dir: bool,
    ) -> None:
        """
        Resolves a MOVED_TO event against pending MOVED_FROM entries.

        If a correspong MOVED_FROM entry exists, the pair is converted to
        RENAMED OR MOVED depending on whether the parent directory has changed.
        If there is no corresponding entry, the object came from outside of
        the tracked paths. Then it is emitted as CREATED.
        """
        pending_entry = self._pending.pop(cookie, None)

        # 1.Case: Pending entry is exists
        if pending_entry is not None:
            from_event, _ = pending_entry
            from_parent = from_event.path.rsplit("/", maxsplit=1)[0]
            to_parent = full_path.rsplit("/", maxsplit=1)[0]

            event_type: InotifyEventType = (
                (
                    InotifyEventType.DIR_RENAMED
                    if is_dir
                    else InotifyEventType.FILE_RENAMED
                )
                if from_parent == to_parent
                else from_event.event_type  # DIR_MOVED or FILE_MOVED
            )  # type: ignore[assignment]

            self._buffer.put(
                Event(
                    path=full_path,
                    event_type=event_type,
                    timestamp=monotonic(),  # Time when moving is finished
                    previous_path=from_event.path,
                )
            )
            return

        # 2.Case: Pending entry is not exist
        if is_dir:
            self._subscribe_new_dir(full_path)

        event_type = (
            InotifyEventType.DIR_CREATED if is_dir else InotifyEventType.FILE_CREATED
        )  # type: ignore[assignment]
        self._buffer.put(
            Event(path=full_path, event_type=event_type, timestamp=monotonic())
        )

    def _flush_expired_pending(self) -> None:
        """
        Emits expired pending MOVED_FROM events as DELETED.
        A pending entry is expired when its iteration count reaches
        _PENDING_MAX_ITERATIONS meaning no matching MOVED_TO arrived
        within the allowed limit of delay. This means the object is moved
        to outside of the watching paths. The DELETED event preserves the
        original timestamp.
        """
        expired = []
        for cookie, (event, count) in self._pending.items():
            if count >= _PENDING__MAX_ITERATIONS:
                event_type = (
                    InotifyEventType.DIR_DELETED
                    if event.event_type is InotifyEventType.DIR_MOVED
                    else InotifyEventType.FILE_DELETED
                )
                self._buffer.put(
                    Event(
                        path=event.path,
                        event_type=event_type,  # type: ignore[assignment]
                        timestamp=event.timestamp,
                    )
                )
                expired.append(cookie)
            else:
                self._pending[cookie] = (event, count + 1)

        for cookie in expired:
            del self._pending[cookie]

    @staticmethod
    def _resolve_event_type(
        mask: int,
        is_dir: bool,
    ) -> InotifyEventType | None:
        """
        Maps an inotify mask to an InotifyEventType.

        Returns None if the mask does not match any known event.
        This can occur when inotify delivers internal or unsupported
        flags not included in _MASK.
        """
        mapping = _DIR_MASK_TO_EVENT if is_dir else _FILE_MASK_TO_EVENT
        for flag, event_type in mapping.items():
            if mask & flag:
                return event_type
        return None
