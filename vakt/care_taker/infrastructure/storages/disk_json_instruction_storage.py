from __future__ import annotations

from collections.abc import Sequence
from json import dump, load
from pathlib import Path
from typing import Any, Optional

from ...core import (
    BaseInstructionStorage,
    Event,
    EventType,
    Instruction,
    LevelType,
)


class DiskJsonInstructionStorage(BaseInstructionStorage):
    """
    Implementation of BaseInstrucitonStorage that persists the registry
    to disk as a JSON file and matches Instruction using glob patterns.

    Matching Strategy:
        - Finds all Instructions whose paths match event.path via fnmatch.
        - If path=None, the Instruciton matches any path.(It means None="root/**")
        - Among matched Instrucitons have equal specificity, prefers the one
            with a matching event_type over event_types=None.
        - Returns None if no Instruction matches the incoming Event.

    Maintains two parallel registries:
        - _registry: list of Instruction domain objects used by the code.
        - _raw_registry: list of raw dicst used for fast JSON serialization.

    Notes:
        - Registry is loaded from disk on initialization if file exists.
        - Persists changes automatically on every registry modification.
        - JSON registry file and its parent directories are created
            automatically if they not exists.
    """

    def __init__(self, registry_path: str) -> None:
        """
        Initializes all attributes of instance and loads all
        Instructions raw metadata in dict format. Ensure that
        the path file is exists and its a JSON file in correct format.
        """
        self._registry_path: Path = Path(registry_path)
        self._registry: list[Instruction] = []
        self._raw_registry: list[dict] = []
        self._load()

    def add(self, instruction: Instruction) -> None:
        """
        Adds an Instruction to both registries and persists
        raw_registry immediately to avoid metadata loss on crash.
        """
        self._registry.append(instruction)
        self._raw_registry.append(self._instruction_to_dict(instruction))
        self._save()

    def get(self, event: Event) -> Optional[Instruction]:
        """
        Returns the most appropriate Instruction for the given Event
        that best matches the specifications. Returns None if no match is found.
        """
        best: Optional[Instruction] = None
        best_specifity: int = -1
        best_has_event_type: bool = False

        for instruction in self._registry:
            matched_pattern = self._match_path(event.path, instruction)
            if matched_pattern is None:
                continue

            has_event_type = (
                instruction.event_types is not None
                and event.event_type in instruction.event_types
            )

            if instruction.event_types is not None and not has_event_type:
                continue

            specificity = len(matched_pattern)

            is_better = specificity > best_specifity or (
                specificity == best_specifity
                and has_event_type
                and not best_has_event_type
            )

            if is_better:
                best = instruction
                best_specifity = specificity
                best_has_event_type = has_event_type

        return best

    def _match_path(self, path: str, instruction: Instruction) -> Optional[str]:
        """
        Returns the most matching glob pattern if event path matches
        any of the instruction paths. Returns None if no match.
        If instruction.paths is None matches any path and returns
        empty string as pattern with specificity 0.
        """
        most = ""
        matched = False

        if instruction.paths is None:
            return most

        for pattern in instruction.paths:
            if pattern == path:
                most = pattern
                matched = True
                break
            elif pattern.endswith("/**"):
                base = pattern.rsplit("/", maxsplit=1)[0]
                if path.startswith(base) and len(base) > len(most):
                    most = pattern
                    matched = True
            elif pattern.endswith(("/*", "/")):
                base = pattern.rsplit("/", maxsplit=1)[0]
                full_path = base + "/" + path.rsplit("/", maxsplit=1)[1]
                if full_path == path:
                    most = pattern
                    matched = True

        if matched:
            return most

        return None

    def show(self) -> Sequence[Instruction]:
        """Returns all Instruction from the registry."""
        return self._registry

    def delete(self, target: Any) -> None:
        """
        Removes an Instruction from both registries at the given index.
        silently ignores if index does not exist,
        """
        try:
            self._registry.pop(target)
            self._raw_registry.pop(target)
            self._save()
        except IndexError:
            return

    def clear(self) -> None:
        """
        Removes all Instructions from both registries and persists immediately.
        """
        self._registry.clear()
        self._raw_registry.clear()
        self._save()

    @staticmethod
    def _instruction_to_dict(instruction: Instruction) -> dict:
        """Converts an Instruction domain object to a raw dict for JSON serialization."""
        return {
            "paths": list(instruction.paths) if instruction.paths else None,
            "event_types": (
                [et.value for et in instruction.event_types]
                if instruction.event_types
                else None
            ),
            "level": instruction.level.value if instruction.level else None,
            "should_log": instruction.should_log,
            "should_backup": instruction.should_backup,
            "should_notify": instruction.should_notify,
        }

    def _save(self) -> None:
        """Persists raw registry metadata to JSON file on a disk."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._registry_path, "w") as file:
            dump(self._raw_registry, file, indent=4)

    def _load(self) -> None:
        """
        Loads registry metadata from JSON file on disk if it exists.
        Ensure that the file is in right format.
        """
        if not self._registry_path.exists():
            return

        with open(self._registry_path, "r") as file:
            self._raw_registry = load(file)

        for instruction in self._raw_registry:
            paths = instruction.get("paths")
            event_types = instruction.get("event_types")
            level = instruction.get("level")
            should_log = instruction.get("should_log", True)
            should_backup = instruction.get("should_backup", False)
            should_notify = instruction.get("should_notify", False)

            self._registry.append(
                Instruction(
                    paths=paths,
                    event_types=[EventType(et) for et in event_types]
                    if event_types is not None
                    else None,
                    level=LevelType(level) if level is not None else None,
                    should_log=should_log,
                    should_backup=should_backup,
                    should_notify=should_notify,
                )
            )
