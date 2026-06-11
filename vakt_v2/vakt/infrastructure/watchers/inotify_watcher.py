from __future__ import annotations

from dataclasses import dataclass, field
from os import scandir
from os.path import exists, isdir
from queue import Queue
from threading import Event as ShutdownEvent
from threading import Thread
from time import monotonic
from weakref import WeakValueDictionary

from inotify_simple import Event as IEvent
from inotify_simple import INotify
from inotify_simple import flags as _FLAGS

from ...core import BaseWatcher, Configure, Event
from ..semantic_types import INotifyEventType

_MASK: int = (
    _FLAGS.CREATE
    | _FLAGS.DELETE
    | _FLAGS.ACCESS
    | _FLAGS.ATTRIB
    | _FLAGS.OPEN
    | _FLAGS.CLOSE_WRITE
    | _FLAGS.CLOSE_NOWRITE
    | _FLAGS.MOVED_FROM
    | _FLAGS.MOVED_TO
    | _FLAGS.EXCL_UNLINK
    | _FLAGS.DONT_FOLLOW
)
"""
Combined INotify event mask applied to every watch descriptor.
Three system events are delivered by the kernel regardless of this mask
and are handled internally by INotifyWatcher:
    - IN_IGNORED:    Delivered when a watch descriptor is automatically
                     invalidated - either because the watched directory was
                     deleted or because the file system was unmounted.
                     INotifyWatcher removes the corresponding WatchNode,
                     since the path no longer exists and cannot produce
                     meaningful events.

    - IN_UNMOUNT:    Delivered when the file system containing a watched path
                     is unmounted. The kernel invalidates all watch descriptors
                     on that file system immediately after, so IN_IGNORED
                     follows for each of them. INotifyWatcher treats this
                     identically to IN_IGNORED.

    - IN_Q_OVERFLOW: Delivered when the kernel event queue overflowed and
                     events were lost. Since the exact set of missed changes
                     is unknown, INotifyWatcher discards all current state
                     and performs a full rescan via _rescan() to restore a
                     consistent view of the file system.

Two special flags are included for defensive reasons:
    - IN_EXCL_UNLINK: Supresses events for directories that have been unlinked
                      but are still held open by another process - reduces
                      unnecessary buffer noise.

    - IN_DONT_FOLLOW: Prevents following symbolic links when adding watches,
                      keeping observation within the expected directory tree.

For the reasoning behind all other flag choices - including why IN_MODIFY
is ommited - see INotifyEventType class documentation.
"""

_FILE_MASK_TO_EVENT: dict[int, INotifyEventType] = {
    _FLAGS.ACCESS: INotifyEventType.FILE_ACCESSED,
    _FLAGS.CREATE: INotifyEventType.FILE_CREATED,
    _FLAGS.DELETE: INotifyEventType.FILE_DELETED,
    _FLAGS.OPEN: INotifyEventType.FILE_OPENED,
    _FLAGS.CLOSE_NOWRITE: INotifyEventType.FILE_CLOSED_NO_WRITE,
    _FLAGS.CLOSE_WRITE: INotifyEventType.FILE_CLOSED_WRITE,
    _FLAGS.ATTRIB: INotifyEventType.FILE_METADATA_CHANGED,
}  # type: ignore[assignment]

_DIR_MASK_TO_EVENT: dict[int, INotifyEventType] = {
    _FLAGS.ACCESS: INotifyEventType.DIR_ACCESSED,
    _FLAGS.CREATE: INotifyEventType.DIR_CREATED,
    _FLAGS.DELETE: INotifyEventType.DIR_DELETED,
    _FLAGS.ATTRIB: INotifyEventType.DIR_METADATA_CHANGED,
    _FLAGS.OPEN: INotifyEventType.DIR_OPENED,
}  # type: ignore[assignment]


@dataclass(slots=True)
class WatchNode:
    """..."""

    wd: int = -1
    name: str = ""
    parent: WatchNode | None = None
    recursive: bool = False
    origin: tuple[str, bool] | None = None
    children: list[WatchNode] = field(default_factory=list)

    @property
    def path(self) -> str:
        if self.origin is not None:
            return self.origin[0] + "/" + self.name

        full_name = self.name
        parent = self.parent

        while parent is not None:
            full_name = parent.name + "/" + full_name
            if parent.origin is not None:
                return parent.origin[0] + "/" + full_name
            parent = parent.parent

        return "/" + full_name


class INotifyWatcher(BaseWatcher):
    """..."""

    def __init__(self, configure: Configure) -> None:
        """..."""
        self._buffer: Queue[Event] = getattr(configure, "thread_safe_buffer")
        self._shutdown_event: ShutdownEvent = getattr(configure, "shutdown_event")
        self._occupied_paths: dict[str, int] = getattr(configure, "occupied_paths")
        self._paths_to_observe: list[str] = getattr(configure, "paths_to_observe")
        self._paths_to_ignore: set[str] = getattr(configure, "paths_to_ignore")
        self._auto_correction: bool = getattr(configure, "auto_correction")
        self._read_timeout: int = getattr(configure, "read_timeout")
        self._pending_count: int = getattr(configure, "pending_count")
        self._inotify: INotify = INotify()
        self._pendings: dict[int, tuple[WatchNode, Event, int]] = {}
        self._root: WatchNode = WatchNode()
        self._wd_to_node: WeakValueDictionary[int, WatchNode] = WeakValueDictionary()
        self._thread: Thread = Thread(target=self.events, daemon=True, name="Watcher")

    def start(self) -> None:
        """..."""
        self._scan()
        self._thread.start()

    def stop(self) -> None:
        """..."""
        self._thread.join()
        self._unsubscribe_all()
        self._inotify.close()

    def events(self) -> None:
        """..."""
        while not self._shutdown_event.is_set():
            inotify_events = self._inotify.read(timeout=self._read_timeout)

            for ie in inotify_events:
                if ie.mask & _FLAGS.IGNORED or ie.mask & _FLAGS.UNMOUNT:
                    node = self._wd_to_node.pop(ie.wd, None)
                    if node is not None:
                        self._remove_node(node)
                    continue

                if ie.mask & _FLAGS.Q_OVERFLOW:
                    self._rescan()
                    continue

                self._handle(ie)
            self._flush_expired_pendings()

    @classmethod
    def describe(cls) -> str:
        return "..."

    @classmethod
    def requirements(cls) -> Configure:
        return Configure(
            internal_reqs=(
                "shutdown_event",
                "occupied_paths",
                "thread_safe_buffer",
            ),
            client_reqs={
                "paths_to_observe": (
                    "...",
                    lambda x: [p.strip() for p in x.split(",") if p.strip()],
                ),
                "paths_to_ignore": (
                    "...",
                    lambda x: set(p.strip() for p in x.split(",") if p.strip()),
                ),
                "auto_correction": (
                    "...",
                    lambda x: (
                        x
                        if isinstance(x, bool)
                        else x.lower() in {"true", "1", "yes"}
                        if isinstance(x, str)
                        else (_ for _ in ()).throw(ValueError("..."))
                    ),
                ),
                "read_timeout": (
                    "...",
                    lambda x: (
                        v
                        if (v := int(x)) >= 200
                        else (_ for _ in ()).throw(ValueError("..."))
                    ),
                ),
                "pending_count": (
                    "...",
                    lambda x: (
                        v
                        if (v := int(x)) >= 1
                        else (_ for _ in ()).throw(ValueError("..."))
                    ),
                ),
            },
        )

    def _scan(self) -> None:
        """..."""
        non_recursive: list[str] = []

        for path in self._paths_to_observe:
            if path.endswith("/**"):
                self._subscribe_recursive(path.removesuffix("/**").removesuffix("/"))
            else:
                non_recursive.append(path)

        for path in non_recursive:
            if path.endswith("/*"):
                self._subscribe_non_recursive(path.removesuffix("/*").removesuffix("/"))
            elif path.endswith("/"):
                self._subscribe_non_recursive(path.removesuffix("/").removesuffix("/"))
            else:
                if not exists(path):
                    continue
                if not isdir(path):
                    path = path.rsplit("/", 1)[0]
                self._subscribe_non_recursive(path)

    def _rescan(self) -> None:
        """..."""
        self._unsubscribe_all()
        self._scan()

    def _unsubscribe_all(self) -> None:
        """..."""
        for wd in self._wd_to_node:
            try:
                self._inotify.rm_watch(wd)
            except OSError:
                pass

        self._root = WatchNode()
        self._wd_to_node.clear()
        self._pendings.clear()

    def _subscribe_recursive(self, path: str, parent: WatchNode | None = None) -> None:
        """..."""
        stack: list[tuple[str, WatchNode]] = [
            (path, parent if parent is not None else self._root)
        ]

        while stack:
            current_path, current_parent = stack.pop()
            try:
                wd = self._inotify.add_watch(current_path, _MASK)
            except OSError:
                continue

            if wd == current_parent.wd:
                node = current_parent

            else:
                node = WatchNode(
                    wd=wd,
                    name=current_path.rsplit("/", 1)[-1],
                    parent=current_parent if current_parent is not self._root else None,
                    recursive=True,
                    origin=(current_path.rsplit("/", 1)[0], True)
                    if current_parent is self._root
                    else None,
                )
                current_parent.children.append(node)
                self._wd_to_node[wd] = node

            try:
                for entry in scandir(current_path):
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((entry.path, node))
            except OSError:
                pass

    def _subscribe_non_recursive(self, path: str) -> None:
        """..."""
        if not exists(path):
            return
        try:
            wd = self._inotify.add_watch(path, _MASK)
        except OSError:
            return

        base, name = path.rsplit("/", 1)
        node = self._wd_to_node.get(wd)
        if node is not None:
            if node not in self._root.children:
                node.origin = (base, False)
        else:
            node = WatchNode(
                wd=wd,
                name=name,
                parent=None,
                recursive=False,
                origin=(base, False),
            )
            self._wd_to_node[wd] = node
            self._root.children.append(node)

    def _orphan_descendants(self, node: WatchNode) -> None:
        """..."""
        stack: list[WatchNode] = list(node.children)

        while stack:
            current = stack.pop()
            try:
                self._inotify.rm_watch(current.wd)
            except OSError:
                pass

            stack.extend(current.children)
            current.children = []
            current.parent = None
        node.children = []

    def _remove_node(self, node: WatchNode) -> None:
        """..."""
        if node.parent is not None:
            try:
                node.parent.children.remove(node)
            except ValueError:
                pass
        if node.origin is not None:
            try:
                self._root.children.remove(node)
            except ValueError:
                pass
        node.parent = None
        self._orphan_descendants(node)

        try:
            self._inotify.rm_watch(node.wd)
        except OSError:
            return

    @staticmethod
    def _resolve(mask: int, is_dir: bool) -> INotifyEventType | None:
        """..."""
        mapping = _DIR_MASK_TO_EVENT if is_dir else _FILE_MASK_TO_EVENT
        for flag, event_type in mapping.items():
            if mask & flag:
                return event_type
        return None

    def _flush_expired_pendings(self) -> None:
        """..."""
        expired: list[int] = []
        for cookie, (old_parent, event, count) in self._pendings.items():
            if count >= self._pending_count:
                if event.event_type is INotifyEventType.DIR_MOVED:
                    if old_parent.recursive:
                        for node in old_parent.children:
                            if node.name == event.path.rsplit("/", 1)[-1]:
                                self._remove_node(node)
                                break
                    event_type = INotifyEventType.DIR_DELETED
                else:
                    event_type = INotifyEventType.FILE_DELETED

                self._buffer.put(
                    Event(
                        path=event.path,
                        event_type=event_type,  # type: ignore[assignment]
                        timestamp=event.timestamp,
                    )
                )
                expired.append(cookie)
            else:
                self._pendings[cookie] = (old_parent, event, count + 1)

        for cookie in expired:
            del self._pendings[cookie]

    def _handle_moved_to(
        self, new_parent: WatchNode, full_path: str, cookie: int, is_dir: bool
    ) -> None:
        """..."""
        new_path = full_path
        name = full_path.rsplit("/", 1)[-1]
        pending = self._pendings.pop(cookie, None)

        def adopt(parent: WatchNode, orphan: WatchNode, name: str) -> None:
            orphan.name = name
            orphan.parent = parent
            parent.children.append(orphan)

        def autocorrect(
            new_path: str, old_path: str, node: WatchNode | None = None
        ) -> None:
            if self._auto_correction:
                for index, raw in enumerate(self._paths_to_observe):
                    if raw.endswith(("/**", "/*", "/")):
                        path, suffix = raw.rsplit("/", 1)
                    else:
                        path, suffix = raw, ""
                    if old_path == path.removesuffix("/"):
                        if node is not None:
                            if node.origin is not None:
                                mode = node.origin[1]
                            else:
                                mode = True if suffix == "/**" else False
                            node.origin = (new_path, mode)
                            self._root.children.append(node)
                        self._paths_to_observe[index] = new_path + "/" + suffix
                        break

        def get_child(parent: WatchNode, name: str, orphan: bool) -> WatchNode | None:
            if parent.recursive:
                for index, child in enumerate(parent.children):
                    if child.name == name:
                        node = parent.children[index]
                        if orphan:
                            parent.children.pop(index)
                            node.parent = None
                        return node
            return None

        if pending is None:
            if is_dir:
                if new_parent.recursive:
                    self._subscribe_recursive(new_path, new_parent)
                    autocorrect(new_path, new_path, get_child(new_parent, name, False))
            self._buffer.put(
                Event(
                    path=new_path,
                    event_type=INotifyEventType.DIR_CREATED
                    if is_dir
                    else INotifyEventType.FILE_CREATED,  # type: ignore[assigment]
                    timestamp=monotonic(),
                )
            )
            return

        old_parent, event, _ = pending
        node: WatchNode | None = None

        if old_parent.recursive and is_dir:
            node = get_child(old_parent, event.path.rsplit("/", 1)[-1], True)

        if old_parent is new_parent:
            if node is not None:
                adopt(new_parent, node, name)
                if node.origin is not None:
                    autocorrect(new_path, event.path, node)

            self._buffer.put(
                Event(
                    path=new_path,
                    event_type=INotifyEventType.DIR_RENAMED
                    if is_dir
                    else INotifyEventType.FILE_RENAMED,  # type: ignore[assignment]
                    timestamp=monotonic(),
                    previous_path=event.path,
                )
            )
        else:
            if node is not None:
                if node.origin is not None:
                    if node.origin[1] is True or new_parent.recursive:
                        if node.origin[1] is False and node.recursive is False:
                            self._subscribe_recursive(new_path, node)
                        adopt(new_parent, node, name)
                        autocorrect(new_path, event.path, node)

                    else:
                        self._orphan_descendants(node)
                else:
                    if new_parent.recursive:
                        adopt(new_parent, node, name)
                        if node.recursive is False:
                            self._subscribe_recursive(new_path, node)
                    else:
                        self._remove_node(node)
            else:
                if new_parent.recursive:
                    self._subscribe_recursive(new_path, new_parent)
                    autocorrect(
                        new_path, event.path, get_child(new_parent, name, False)
                    )

            self._buffer.put(
                Event(
                    path=new_path,
                    event_type=event.event_type,
                    timestamp=monotonic(),
                    previous_path=event.path,
                )
            )

    def _handle(self, inotify_event: IEvent) -> None:
        """..."""
        node = self._wd_to_node.get(inotify_event.wd, None)

        if node is None:
            return

        full_path = node.path + "/" + inotify_event.name

        if (
            self._occupied_paths.get(full_path, 0) > 0
            or full_path in self._paths_to_ignore
        ):
            return

        is_dir = bool(inotify_event.mask & _FLAGS.ISDIR)

        if inotify_event.mask & _FLAGS.MOVED_FROM:
            event_type = (
                INotifyEventType.DIR_MOVED if is_dir else INotifyEventType.FILE_MOVED
            )
            event = Event(
                path=full_path,
                event_type=event_type,  # type: ignore[assigment]
                timestamp=monotonic(),
            )
            self._pendings[inotify_event.cookie] = (node, event, 0)
            return

        if inotify_event.mask & _FLAGS.MOVED_TO:
            self._handle_moved_to(node, full_path, inotify_event.cookie, is_dir)
            return

        if is_dir and inotify_event.mask & _FLAGS.CREATE and node.recursive:
            self._subscribe_recursive(full_path, node)

        event_type = self._resolve(inotify_event.mask, is_dir)
        if event_type is None:
            return

        self._buffer.put(
            Event(
                path=full_path,
                event_type=event_type,
                timestamp=monotonic(),
            )
        )
