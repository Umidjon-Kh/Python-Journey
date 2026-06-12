"""
Tests for INotifyWatcher.

Requires Linux with inotify support.
Tests are split into two categories:
    - Unit tests: test internal state directly, no thread started.
    - Integration tests: start the watcher thread and test real inotify events
      against an actual temporary file system.
"""

from __future__ import annotations

import time
import types
from pathlib import Path
from queue import Empty, Queue
from threading import Event as ShutdownEvent

from vakt.core.domain.event import Event
from vakt.infrastructure.semantic_types import INotifyEventType
from vakt.infrastructure.watchers.inotify_watcher import INotifyWatcher, WatchNode

# ─── Helpers ────────────────────────────────────────────────────────────────


def make_configure(**overrides) -> object:
    """Build a minimal Configure-like namespace for testing."""
    cfg = types.SimpleNamespace(
        thread_safe_buffer=Queue(),
        shutdown_event=ShutdownEvent(),
        occupied_paths={},
        paths_to_observe=set(),
        paths_to_ignore=set(),
        auto_correction=False,
        read_timeout=200,
        pending_count=2,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def make_watcher(
    paths: list[str],
    **overrides,
) -> tuple[INotifyWatcher, Queue[Event], ShutdownEvent]:
    buffer: Queue[Event] = Queue()
    shutdown = ShutdownEvent()
    cfg = make_configure(
        thread_safe_buffer=buffer,
        shutdown_event=shutdown,
        paths_to_observe=set(paths),
        **overrides,
    )
    return INotifyWatcher(cfg), buffer, shutdown  # type: ignore[arg-type]


def drain(buffer: Queue[Event], timeout: float = 1.5) -> list[Event]:
    """Collect all available events from buffer within timeout seconds."""
    events: list[Event] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            events.append(buffer.get_nowait())
        except Empty:
            time.sleep(0.05)
    return events


def find_node(watcher: INotifyWatcher, path: str) -> WatchNode | None:
    """Find a WatchNode by its computed path."""
    for node in watcher._wd_to_node.values():
        if node.path(watcher._hub) == path:
            return node
    return None


# ─── WatchNode.path ──────────────────────────────────────────────────────────


class TestWatchNodePath:
    def test_top_level_node(self) -> None:
        hub = {1: "/etc"}
        node = WatchNode(wd=1, name="ssl", parent=None, recursive=True, origin=True)
        assert node.path(hub) == "/etc/ssl"

    def test_top_level_non_recursive(self) -> None:
        hub = {1: "/var"}
        node = WatchNode(wd=1, name="log", parent=None, recursive=False, origin=False)
        assert node.path(hub) == "/var/log"

    def test_one_level_deep(self) -> None:
        hub = {1: "/etc"}
        root = WatchNode(wd=1, name="ssl", parent=None, recursive=True, origin=True)
        child = WatchNode(wd=2, name="certs", parent=root, recursive=True, origin=None)
        root.children.append(child)
        assert child.path(hub) == "/etc/ssl/certs"

    def test_three_levels_deep(self) -> None:
        hub = {1: "/etc"}
        root = WatchNode(wd=1, name="ssl", parent=None, recursive=True, origin=True)
        child = WatchNode(wd=2, name="certs", parent=root, recursive=True, origin=None)
        grandchild = WatchNode(
            wd=3, name="ca", parent=child, recursive=True, origin=None
        )
        root.children.append(child)
        child.children.append(grandchild)
        assert grandchild.path(hub) == "/etc/ssl/certs/ca"

    def test_subtree_node_with_own_origin(self) -> None:
        """A subtree node that also has origin uses its own wd for path."""
        hub = {1: "/etc", 2: "/etc/ssl"}
        root = WatchNode(wd=1, name="ssl", parent=None, recursive=True, origin=True)
        child = WatchNode(
            wd=2, name="certs", parent=root, recursive=False, origin=False
        )
        root.children.append(child)
        assert child.path(hub) == "/etc/ssl/certs"


# ─── _subscribe_recursive ────────────────────────────────────────────────────


class TestSubscribeRecursive:
    def test_subscribes_root(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))
        assert find_node(watcher, str(tmp_path)) is not None

    def test_subscribes_all_subdirs(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        for sub in [
            str(tmp_path / "a"),
            str(tmp_path / "a" / "b"),
            str(tmp_path / "a" / "b" / "c"),
        ]:
            assert find_node(watcher, sub) is not None, f"Missing node for {sub}"

    def test_top_level_in_hub(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))
        node = find_node(watcher, str(tmp_path))
        assert node is not None
        assert node.wd in watcher._hub

    def test_subtree_node_not_in_hub(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        assert sub_node is not None
        assert sub_node.wd not in watcher._hub

    def test_explicit_subpath_in_hub(self, tmp_path: Path) -> None:
        """A subpath explicitly listed in paths_to_observe gets its own hub entry."""
        sub = tmp_path / "sub"
        sub.mkdir()
        watcher, _, _ = make_watcher(
            [
                str(tmp_path) + "/**",
                str(sub) + "/**",
            ]
        )
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        assert sub_node is not None
        assert sub_node.wd in watcher._hub

    def test_dedup_same_path_no_duplicates(self, tmp_path: Path) -> None:
        """Subscribing same path twice doesn't duplicate nodes."""
        (tmp_path / "a").mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))
        count_first = len(watcher._wd_to_node)

        watcher._subscribe_recursive(str(tmp_path))
        assert len(watcher._wd_to_node) == count_first

    def test_existing_non_recursive_gets_recursive_true(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([])
        watcher._subscribe_non_recursive(str(tmp_path))
        node = find_node(watcher, str(tmp_path))
        assert node is not None
        assert node.recursive is False

        watcher._subscribe_recursive(str(tmp_path))
        assert node.recursive is True

    def test_children_parent_links_correct(self, tmp_path: Path) -> None:
        sub = tmp_path / "a"
        sub.mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        root_node = find_node(watcher, str(tmp_path))
        assert sub_node is not None
        assert sub_node in root_node.children  # type: ignore[arg-type]
        assert sub_node.parent is root_node


# ─── _subscribe_non_recursive ────────────────────────────────────────────────


class TestSubscribeNonRecursive:
    def test_creates_node_with_correct_origin(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([])
        watcher._subscribe_non_recursive(str(tmp_path))

        node = find_node(watcher, str(tmp_path))
        assert node is not None
        assert node.origin is False
        assert node.recursive is False
        assert node.wd in watcher._hub

    def test_hub_entry_correct_base(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([])
        watcher._subscribe_non_recursive(str(tmp_path))

        node = find_node(watcher, str(tmp_path))
        assert watcher._hub[node.wd] == str(tmp_path.parent)  # type: ignore[arg-type]

    def test_priority_over_top_level_recursive(self, tmp_path: Path) -> None:
        """Non-recursive overrides a top-level recursive node: orphans children."""
        (tmp_path / "a").mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        assert root_node.recursive is True  # type: ignore[arg-type]
        assert len(root_node.children) > 0  # type: ignore[arg-type]

        watcher._subscribe_non_recursive(str(tmp_path))

        assert root_node.origin is False  # type: ignore[arg-type]
        assert root_node.recursive is False  # type: ignore[arg-type]
        assert root_node.children == []  # type: ignore[arg-type]

    def test_subtree_node_keeps_children(self, tmp_path: Path) -> None:
        """Subtree node (has parent) keeps its children when non-recursive overrides."""
        sub = tmp_path / "a"
        sub.mkdir()
        (sub / "b").mkdir()

        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        assert sub_node.parent is not None  # type: ignore[arg-type]
        children_count = len(sub_node.children)  # type: ignore[arg-type]

        watcher._subscribe_non_recursive(str(sub))

        assert sub_node.origin is False  # type: ignore[arg-type]
        assert (
            sub_node.recursive is True  # type: ignore[arg-type]
        )  # still in recursive tree
        assert (
            len(sub_node.children) == children_count  # type: ignore[arg-type]
        )  # children untouched

    def test_skips_nonexistent_path(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([])
        watcher._subscribe_non_recursive(str(tmp_path / "ghost"))
        assert len(watcher._wd_to_node) == 0


# ─── _orphan_descendants ────────────────────────────────────────────────────


class TestOrphanDescendants:
    def test_all_children_removed_from_wd_to_node(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        child_wds = {n.wd for n in watcher._wd_to_node.values() if n is not root_node}
        assert len(child_wds) > 0
        assert root_node

        watcher._orphan_descendants(root_node, True)  # type: ignore[arg-type]

        for wd in child_wds:
            assert wd not in watcher._wd_to_node

    def test_children_list_cleared(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        watcher._orphan_descendants(root_node, True)  # type: ignore[arg-type]

        assert root_node.children == []  # type: ignore[arg-type]

    def test_hub_entries_removed_on_delete(self, tmp_path: Path) -> None:
        """When mode=False (deleted), hub entries for origin children are removed."""
        sub = tmp_path / "a"
        sub.mkdir()
        watcher, _, _ = make_watcher(
            [
                str(tmp_path) + "/**",
                str(sub) + "/**",
            ]
        )
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        assert sub_node.wd in watcher._hub  # type: ignore[arg-type]
        assert sub_node.origin is not None  # type: ignore[arg-type]

        root_node = find_node(watcher, str(tmp_path))
        watcher._orphan_descendants(root_node, False)  # type: ignore[arg-type]

        assert sub_node.wd not in watcher._hub  # type: ignore[arg-type]

    def test_origin_nodes_preserved_on_move(self, tmp_path: Path) -> None:
        """When mode=tuple (move), origin nodes are NOT unsubscribed."""
        sub = tmp_path / "a"
        sub.mkdir()
        watcher, _, _ = make_watcher(
            [
                str(tmp_path) + "/**",
                str(sub) + "/**",
            ]
        )
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        sub_wd = sub_node.wd  # type: ignore[arg-type]

        root_node = find_node(watcher, str(tmp_path))
        new = str(tmp_path.parent / "new_tmp")
        watcher._orphan_descendants(root_node, (new, str(tmp_path)))  # type: ignore[arg-type]

        # sub_node was an origin node so its wd should still be in wd_to_node
        assert sub_wd in watcher._wd_to_node

    def test_parent_references_cleared(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        child = root_node.children[0]  # type: ignore[arg-type]

        watcher._orphan_descendants(root_node, True)  # type: ignore[arg-type]

        assert child.parent is None


# ─── _remove_node ────────────────────────────────────────────────────────────


class TestRemoveNode:
    def test_removes_from_wd_to_node(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        wd = root_node.wd  # type: ignore[arg-type]

        watcher._remove_node(root_node, False)  # type: ignore[arg-type]
        assert wd not in watcher._wd_to_node

    def test_removes_from_hub(self, tmp_path: Path) -> None:
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        root_node = find_node(watcher, str(tmp_path))
        wd = root_node.wd  # type: ignore[arg-type]
        assert wd in watcher._hub

        watcher._remove_node(root_node, False)  # type: ignore[arg-type]
        assert wd not in watcher._hub

    def test_removes_from_parent_children(self, tmp_path: Path) -> None:
        sub = tmp_path / "a"
        sub.mkdir()
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        sub_node = find_node(watcher, str(sub))
        parent_node = sub_node.parent  # type: ignore[arg-type]

        watcher._remove_node(sub_node, False)  # type: ignore[arg-type]
        assert sub_node not in parent_node.children  # type: ignore[arg-type]

    def test_all_descendants_removed_out_of_bounds(self, tmp_path: Path) -> None:
        """out_of_bounds=True removes all descendants from wd_to_node."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        watcher, _, _ = make_watcher([str(tmp_path) + "/**"])
        watcher._subscribe_recursive(str(tmp_path))

        all_wds = set(watcher._wd_to_node.keys())
        root_node = find_node(watcher, str(tmp_path))

        watcher._remove_node(root_node, True)  # type: ignore[arg-type]

        for wd in all_wds:
            assert wd not in watcher._wd_to_node


# ─── Integration: real inotify events ───────────────────────────────────────


class TestLiveEvents:
    def test_file_created(self, tmp_path: Path) -> None:
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            (tmp_path / "hello.txt").write_text("hi")
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.FILE_CREATED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_file_deleted(self, tmp_path: Path) -> None:
        target = tmp_path / "bye.txt"
        target.write_text("bye")

        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            target.unlink()
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.FILE_DELETED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_dir_created(self, tmp_path: Path) -> None:
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/**"])
        watcher.start()
        try:
            (tmp_path / "newdir").mkdir()
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.DIR_CREATED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_dir_renamed_same_parent(self, tmp_path: Path) -> None:
        src = tmp_path / "before"
        src.mkdir()

        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/**"])
        watcher.start()
        try:
            src.rename(tmp_path / "after")
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.DIR_RENAMED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_dir_moved_cross_parent(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        (src_dir / "sub").mkdir()

        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/**"])
        watcher.start()
        try:
            (src_dir / "sub").rename(dst_dir / "sub")
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.DIR_MOVED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_file_renamed(self, tmp_path: Path) -> None:
        src = tmp_path / "old.txt"
        src.write_text("data")

        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            src.rename(tmp_path / "new.txt")
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.FILE_RENAMED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_occupied_paths_suppressed(self, tmp_path: Path) -> None:
        target = tmp_path / "busy.txt"
        target.write_text("init")
        occupied = {str(target): 1}

        watcher, buffer, shutdown = make_watcher(
            [str(tmp_path) + "/*"],
            occupied_paths=occupied,
        )
        watcher.start()
        try:
            target.write_text("changed")
            time.sleep(0.6)
            events = drain(buffer, timeout=0.4)
            assert all(e.path != str(target) for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_paths_to_ignore_suppressed(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("hidden")

        watcher, buffer, shutdown = make_watcher(
            [str(tmp_path) + "/*"],
            paths_to_ignore={str(secret)},
        )
        watcher.start()
        try:
            secret.write_text("changed")
            time.sleep(0.6)
            events = drain(buffer, timeout=0.4)
            assert all(e.path != str(secret) for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_expired_pending_emits_deleted(self, tmp_path: Path) -> None:
        """MOVED_FROM with no MOVED_TO after pending_count → emits DELETED."""
        inside = tmp_path / "watched"
        outside = tmp_path.parent / "outside_scope"
        inside.mkdir()

        watcher, buffer, shutdown = make_watcher(
            [str(tmp_path) + "/*"],
            pending_count=2,
        )
        watcher.start()
        try:
            inside.rename(outside)
            events = drain(buffer, timeout=2.5)
            assert any(e.event_type is INotifyEventType.DIR_DELETED for e in events)
        finally:
            outside.rename(inside)  # cleanup
            shutdown.set()
            watcher.stop()

    def test_rescan_restores_state(self, tmp_path: Path) -> None:
        """After _rescan(), watcher still detects new events."""
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            watcher._rescan()
            (tmp_path / "after_rescan.txt").write_text("hi")
            events = drain(buffer)
            assert any(e.event_type is INotifyEventType.FILE_CREATED for e in events)
        finally:
            shutdown.set()
            watcher.stop()

    def test_high_volume_file_creation(self, tmp_path: Path) -> None:
        """Create 300 files rapidly — expect at least 90% to be captured."""
        n = 300
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            for i in range(n):
                (tmp_path / f"f{i}.txt").write_text(str(i))
            events = drain(buffer, timeout=4.0)
            created = [
                e for e in events if e.event_type is INotifyEventType.FILE_CREATED
            ]
            assert len(created) >= int(n * 0.9), (
                f"Expected >= {int(n * 0.9)} FILE_CREATED events, got {len(created)}"
            )
        finally:
            shutdown.set()
            watcher.stop()

    def test_high_volume_mixed_events(self, tmp_path: Path) -> None:
        """Create, rename and delete files rapidly without hanging."""
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            for i in range(100):
                f = tmp_path / f"m{i}.txt"
                f.write_text(str(i))

            for i in range(100):
                src = tmp_path / f"m{i}.txt"
                if src.exists():
                    src.rename(tmp_path / f"r{i}.txt")

            for i in range(100):
                f = tmp_path / f"r{i}.txt"
                if f.exists():
                    f.unlink()

            events = drain(buffer, timeout=4.0)
            # Just verify the watcher didn't crash and delivered something
            assert len(events) > 0
        finally:
            shutdown.set()
            watcher.stop()

    def test_recursive_new_dir_auto_subscribed(self, tmp_path: Path) -> None:
        """Newly created subdirectory is automatically subscribed in recursive mode."""
        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/**"])
        watcher.start()
        try:
            new_dir = tmp_path / "newdir"
            new_dir.mkdir()
            time.sleep(0.3)  # let watcher subscribe to new_dir

            (new_dir / "file.txt").write_text("inside")
            events = drain(buffer)
            paths = {e.path for e in events}
            assert str(new_dir / "file.txt") in paths
        finally:
            shutdown.set()
            watcher.stop()

    def test_non_recursive_ignores_subdirs(self, tmp_path: Path) -> None:
        """Non-recursive watcher does NOT report events inside subdirectories."""
        sub = tmp_path / "sub"
        sub.mkdir()

        watcher, buffer, shutdown = make_watcher([str(tmp_path) + "/*"])
        watcher.start()
        try:
            (sub / "deep.txt").write_text("deep")
            time.sleep(0.5)
            events = drain(buffer, timeout=0.4)
            paths = {e.path for e in events}
            assert str(sub / "deep.txt") not in paths
        finally:
            shutdown.set()
            watcher.stop()
