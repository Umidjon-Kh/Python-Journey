from __future__ import annotations

from dataclasses import dataclass, field
from os import scandir
from os.path import exists, isdir
from queue import Queue
from threading import Event as ShutdownEvent
from threading import Thread
from time import monotonic

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

    wd: int
    name: str
    parent: WatchNode | None
    recursive: bool
    origin: bool | None = None
    children: list[WatchNode] = field(default_factory=list)

    def path(self, origins: dict[int, str]) -> str:
        """..."""
        if self.origin is not None:
            return origins[self.wd] + "/" + self.name

        full_name = self.name
        parent = self.parent

        while parent is not None:
            full_name = parent.name + "/" + full_name
            if parent.origin is not None:
                return origins[parent.wd] + "/" + full_name
            parent = parent.parent

        return "/" + full_name


class INotifyWatcher(BaseWatcher):
    """..."""

    def __init__(self, configure: Configure) -> None:
        """..."""
        self._buffer: Queue[Event] = getattr(configure, "thread_safe_buffer")
        self._shutdown_event: ShutdownEvent = getattr(configure, "shutdown_event")
        self._occupied_paths: dict[str, int] = getattr(configure, "occupied_paths")
        self._paths_to_observe: set[str] = getattr(configure, "paths_to_observe")
        self._paths_to_ignore: set[str] = getattr(configure, "paths_to_ignore")
        self._auto_correction: bool = getattr(configure, "auto_correction")
        self._read_timeout: int = getattr(configure, "read_timeout")
        self._pending_count: int = getattr(configure, "pending_count")
        self._inotify: INotify = INotify()
        self._pendings: dict[int, tuple[WatchNode, Event, int]] = {}
        self._hub: dict[int, str] = {}
        self._wd_to_node: dict[int, WatchNode] = {}
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
                        self._remove_node(node, False)
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
                    lambda x: {p.strip() for p in x.split(",") if p.strip()},
                ),
                "paths_to_ignore": (
                    "...",
                    lambda x: {p.strip() for p in x.split(",") if p.strip()},
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

        self._hub.clear()
        self._wd_to_node.clear()
        self._pendings.clear()

    def _subscribe_recursive(self, path: str, parent: WatchNode | None = None) -> None:
        """..."""
        stack: list[tuple[str, WatchNode | None]] = [(path, parent)]

        while stack:
            current_path, current_parent = stack.pop()
            try:
                wd = self._inotify.add_watch(current_path, _MASK)
            except OSError:
                continue

            if (
                wd in self._hub
                or current_parent is not None
                and wd == current_parent.wd
            ):
                node = self._wd_to_node[wd]
                if node.recursive:
                    continue
                node.recursive = True

            else:
                base, name = current_path.rsplit("/", 1)

                node = WatchNode(
                    wd=wd,
                    name=name,
                    parent=current_parent,
                    recursive=True,
                )
                self._wd_to_node[wd] = node
                if current_parent is not None:
                    current_parent.children.append(node)
                if (
                    current_parent is None
                    or current_path + "/**" in self._paths_to_observe
                    or current_path + "//**" in self._paths_to_observe
                ):
                    self._hub[wd] = base
                    node.origin = True
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
            node.origin = False
            if node.recursive is True and node.parent is None:
                self._orphan_descendants(node, True)
                node.recursive = False
        else:
            node = WatchNode(
                wd=wd,
                name=name,
                parent=None,
                recursive=False,
                origin=False,
            )
            self._wd_to_node[wd] = node
        self._hub[wd] = base

    def _autocorrect(self, after: str, before: str) -> None:
        """..."""

        for wd, base in self._hub.items():
            if base.startswith(before):
                new_base = after + base.removeprefix(before)
                self._hub[wd] = new_base
                node = self._wd_to_node[wd]
                if self._auto_correction:
                    old_path = base + "/" + node.name
                    new_path = new_base + "/" + node.name
                    if node.origin is True:
                        self._paths_to_observe.discard(old_path + "/**")
                        self._paths_to_observe.discard(old_path + "//**")
                        self._paths_to_observe.add(new_path + "/**")
                    else:
                        self._paths_to_observe.discard(old_path + "/*")
                        self._paths_to_observe.discard(old_path + "//*")
                        self._paths_to_observe.add(new_path + "/*")

    def _orphan_descendants(
        self, node: WatchNode, mode: tuple[str, str] | bool
    ) -> None:
        """..."""
        stack: list[WatchNode] = list(node.children)

        while stack:
            current = stack.pop()

            if current.origin is not None:
                if isinstance(mode, tuple):
                    if current.origin is False:
                        stack.extend(current.children)
                    continue
                else:
                    self._hub.pop(current.wd, None)

            if mode is True:
                try:
                    self._inotify.rm_watch(current.wd)
                except OSError:
                    pass

            stack.extend(current.children)
            current.children = []
            current.parent = None
            self._wd_to_node.pop(current.wd, None)
        node.children = []

        if isinstance(mode, tuple):
            self._autocorrect(mode[0], mode[1])

    def _remove_node(self, node: WatchNode, out_of_bounds: bool) -> None:
        """..."""
        self._wd_to_node.pop(node.wd, None)
        self._hub.pop(node.wd, None)
        if node.parent is not None:
            try:
                node.parent.children.remove(node)
            except ValueError:
                pass
        node.parent = None
        self._orphan_descendants(node, out_of_bounds)
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
                                self._remove_node(node, True)
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
        self, new_parent: WatchNode, new_path: str, cookie: int, is_dir: bool
    ) -> None:
        """..."""
        name = new_path.rsplit("/", 1)[-1]
        pending = self._pendings.pop(cookie, None)

        def adopt(parent: WatchNode, child: WatchNode, name: str) -> None:
            child.name = name
            child.parent = parent
            parent.children.append(child)

        def get_child(parent: WatchNode, name: str, orphan: bool) -> WatchNode | None:
            for index, child in enumerate(parent.children):
                if child.name == name:
                    if orphan:
                        node = parent.children.pop(index)
                        node.parent = None
                    else:
                        node = parent.children[index]
                    return node
            return None

        if pending is None:
            if is_dir and new_parent.recursive:
                self._subscribe_recursive(new_path, new_parent)

            self._buffer.put(
                Event(
                    path=new_path,
                    event_type=INotifyEventType.DIR_CREATED
                    if is_dir
                    else INotifyEventType.FILE_CREATED,  # type: ignore[assignment]
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
                self._autocorrect(new_path, event.path)

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
            if is_dir:
                if node is not None:
                    if node.origin is not None:
                        if node.origin is True or new_parent.recursive:
                            if node.origin is False and node.recursive is False:
                                self._subscribe_recursive(new_path, node)
                            self._hub[node.wd] = new_path.rsplit("/", 1)[0]
                            adopt(new_parent, node, name)
                            self._autocorrect(new_path, event.path)
                        else:
                            self._orphan_descendants(node, (new_path, event.path))
                    else:
                        if new_parent.recursive:
                            adopt(new_parent, node, name)
                            if node.recursive is False:
                                self._subscribe_recursive(new_path, node)
                            self._autocorrect(new_path, event.path)
                        else:
                            self._remove_node(node, True)
                else:
                    if new_parent.recursive:
                        self._subscribe_recursive(new_path, new_parent)

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

        full_path = node.path(self._hub) + "/" + inotify_event.name

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
