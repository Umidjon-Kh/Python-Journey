from __future__ import annotations

from collections.abc import Mapping, Sequence
from json import dump, load
from logging import DEBUG, FileHandler, Formatter, Logger, getLogger
from os import makedirs, replace
from os.path import exists, isfile
from shutil import copy2, copytree, rmtree
from time import monotonic
from typing import Any, Optional

from ...core import (
    BasePathLocker,
    BaseSnapshotsRegistryStore,
    Event,
    EventType,
    Snapshot,
)
from ..utils import checksum, hash_path


class SAJSnapshotsRegistryStore(BaseSnapshotsRegistryStore):
    _LOG_FILENAME = "saj_operations.log"

    def __init__(self, config: dict[str, Any]) -> None:
        self._backup_dir: str = config["backup_dir"]
        self._registry_path: str = config["registry_path"]
        self._path_locker: BasePathLocker = config["path_locker"]
        self._ignoring_paths: dict[str, int] = config["ignoring_paths"]
        self._registry: dict[str, list[Snapshot]] = {}
        self._raw_registry: dict[str, dict] = {}

        self._log: Logger = self._setup_logger()
        self._log.info(
            "| __init__ | -> start: backup_dir=%s, registry_path=%s",
            self._backup_dir,
            self._registry_path,
        )

        self._load()
        self._recover_tumblers()

        self._log.info(
            "| __init__ | -> done: loaded %d paths, lock=%s",
            len(self._registry),
            type(self._path_locker).__name__,
        )

    def _save(self) -> None:
        self._log.debug(
            "| _save | -> start: persisting %d paths to %s",
            len(self._raw_registry),
            self._registry_path,
        )

        makedirs(self._registry_path.rsplit("/", 1)[0], exist_ok=True)
        tmp_path = self._registry_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._raw_registry, file, indent=4)

        self._ignoring_paths[tmp_path] = self._ignoring_paths.get(tmp_path, 0) + 1
        self._ignoring_paths[self._registry_path] = (
            self._ignoring_paths.get(self._registry_path, 0) + 1
        )

    def _load(self) -> None:
        if not exists(self._registry_path):
            return

        self._log.debug(
            "| _load | -> start: reading registry from %s", self._registry_path
        )

        with open(self._registry_path, encoding="utf-8") as file:
            self._raw_registry = load(file)

        self._ignoring_paths[self._registry_path] = (
            self._ignoring_paths.get(self._registry_path, 0) + 1
        )

        for path, data in self._raw_registry.items():
            self._registry[path] = [
                Snapshot(
                    original_path=raw["original_path"],
                    backup_path=raw["backup_path"],
                    checksum=raw["checksum"],
                    created_at=raw["created_at"],
                    event_type=EventType(raw["event_type"]),
                    description=raw["description"],
                )
                for raw in data["snapshots"]
            ]

        self._log.debug(
            "| _load | -> done: loaded %d paths, %d total snapshots",
            len(self._registry),
            sum(len(v) for v in self._registry.values()),
        )

    def _setup_logger(self) -> Logger:
        vault = self._registry_path.rsplit("/", 1)[0]
        makedirs(vault, exist_ok=True)
        logger = getLogger(__name__)
        logger.setLevel(DEBUG)

        if not logger.handlers:
            handler = FileHandler(vault + "/" + self._LOG_FILENAME, encoding="utf-8")
            handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        return logger

    @staticmethod
    def _to_dict(snapshot: Snapshot) -> dict:
        """Converts a Snapshot domain object to a raw dict for JSON serialization."""
        return {
            "original_path": snapshot.original_path,
            "backup_path": snapshot.backup_path,
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at,
            "event_type": snapshot.event_type,
            "description": snapshot.description,
        }
