from __future__ import annotations

from collections.abc import Mapping, Sequence
from json import dump, load
from pathlib import Path
from typing import Optional

from ...core import BaseSnapshotsStorage, Snapshot


class DiskJsonSnapshotsStorage(BaseSnapshotsStorage):
    """
    Implementation of BaseSnapshotsStorage that persists the registry
    to disk as a JSON file.

    Stores Snapshot metadata objects in memory grouped by original_path
    and automatically persists the registry to disk on every add()
    to prevent metadata loss on crash.

    Maintains two parallel registries:
        - _registry: dictionary of Snapshot domain objects used by the code.
        - _raw_registry: dictionary of raw dicts used for fast JSON serialization
            without converting all Snapshot objects no every save.

    Notes:
        - Registry is loaded from disk on initialization if file exists.
        - Actual backup files are not managed here, only metadata.
        - JSON registry file and its parent directories are created
            automatically if they do not exist.
    """

    def __init__(self, registry_path: str) -> None:
        """
        Initializes all attributes of instance and loads all registry metadata
        from provided registry_path is it exist. Ensure that provided path from upper layer
        is correct and file in path is contains only metadata of Snapshots and nothing at all
        to avoid any exceptions like: KeyError.
        """
        self._registry_path: Path = Path(registry_path)
        self._registry: dict[str, list[Snapshot]] = {}
        self._raw_registry: dict[str, list[dict]] = {}
        self._load()

    def add(self, path: str, snapshot: Snapshot) -> None:
        """
        Adds a Snapshot to both registries under the given path
        and persists the updated raw registry to disk immediately.
        """
        if path not in self._registry:
            self._registry[path] = []
            self._raw_registry[path] = []

        self._registry[path].append(snapshot)
        self._raw_registry[path].append(self._snapshot_to_dict(snapshot))
        self._save()

    def get(self, path: str, index: int) -> Optional[Snapshot]:
        """
        Returns a single Snapshot for given path at the given index.
        Returns latest snapshot if index is out of range or -1.
        Returns None if no snapshots exists for the given path.
        """
        snapshots = self._registry.get(path, None)

        if snapshots is None:
            return None
        try:
            return snapshots[index]
        except IndexError:
            return snapshots[-1]

    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all Snapshots for the given path ordered by created_date ascending.
        Returns empty list if no snapshots exists for the given path.
        """
        return self._registry.get(path, [])

    def show(self) -> Mapping[str, Sequence[Snapshot]]:
        """
        Returns the whole registry mapping for external management utilities.
        """
        return self._registry

    def delete(self, path: str, index: int) -> None:
        """
        Removes Snapshot from both registries at the given index.
        Silently ignores if path or index does not exists.
        If Snapshot was succesfully deleted, persists the updated
        raw_registry to disk immediately.
        """
        snapshots = self._registry.get(path, None)

        if snapshots is None:
            return
        try:
            snapshots.pop(index)
            self._raw_registry[path].pop(index)
            if len(snapshots) == 0:
                del self._registry[path]
                del self._raw_registry[path]
            self._save()
        except IndexError:
            return

    def clear(self, path: str) -> None:
        """
        Removes all Snapshots for the given path from both registries.
        Silently ignores if path does not exist.
        """
        if path not in self._registry:
            return

        del self._registry[path]
        del self._raw_registry[path]
        self._save()

    def clear_all(self) -> None:
        """
        Removes all Snapshots from both registries.
        Silently ignores if registries is already empty.
        """
        self._registry.clear()
        self._raw_registry.clear()
        self._save()

    @staticmethod
    def _snapshot_to_dict(snapshot: Snapshot) -> dict:
        """Converts a Snapshot domain object to a raw dict for JSON serialization."""
        return {
            "original_path": snapshot.original_path,
            "backup_path": snapshot.backup_path,
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at,
            "event_type": snapshot.event_type,
            "description": snapshot.description,
        }

    def _save(self) -> None:
        """Persists raw registry to JSON file on a disk in registry_path."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._registry_path, "w") as file:
            dump(self._raw_registry, file, indent=4)

    def _load(self) -> None:
        """
        Loads registry metadata from registry_path that was provided in initialization
        of instance, Ensure that path file is exists and it's JSON file.
        Also file must contain only metadata of Snapshots in a dict.
        If file is not exists it silently ignores and does nothing.
        """
        if not self._registry_path.exists():
            return
        with open(self._registry_path, "r") as file:
            self._raw_registry = load(file)

        for path, snapshots in self._raw_registry.items():
            self._registry[path] = [
                Snapshot(
                    original_path=snapshot["original_path"],
                    backup_path=snapshot["backup_path"],
                    checksum=snapshot["checksum"],
                    created_at=snapshot["created_at"],
                    event_type=snapshot["event_type"],
                    description=snapshot.get("description"),
                )
                for snapshot in snapshots
            ]
