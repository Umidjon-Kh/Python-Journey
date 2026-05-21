from __future__ import annotations

from collections.abc import Sequence
from json import dump, load
from os import replace
from pathlib import Path
from typing import Any, Optional

from ...core import (
    BaseInstructionRegistry,
    Event,
    EventType,
    Instruction,
    InstructionType,
    LevelType,
)
from ..utils import match_path


class GlobInstructionRegistry(BaseInstructionRegistry):
    """
    Implementation of BaseInstructionRegistry that persists the registry
    to disk as a JSON file and matches Instructions using custom glob-style
    paths patterns.

    Matching Strategy:
        Evaluates each Instruction against the incoming Event using a
        specificity score composed of two components: paths score and
        event_type score. The Instruction with the highest combined score
        is returned. If no Instruction matches, the default Instruction
        provided via __init__ is returned.

        Path scoring:
            Delegated to match_path() in ../utils/path_matcher.
            See its documentation for full pattern syntax and priority rules.

        EventType scoring:
            1 - event.event_type is found in instruction.event_types
            0 - instruction.event_type is None

        Full priority table (descending):
            1. exact path    | event_type is found
            2. exact path    | event_type is None
            3. segment wildcard | event_type is found
            4. segment wildcard | event_type is None
            5. deep glob with anchors | event_type is found
            6. deep glob with anchors | event_type is None
            7. non-recursive          | event_type is found
            8. non-recursive          | event_type is None
            9. recursive              | event_type is found
            10. recursive             | event_type is None
            11. global name/wildcard  | event_type is found
            12. global_name/wildcard  | event_type is None

    Atomic Persistence:
        All registry modifications are persisted atomically using a
        write-to-temp-then-replace strategy. The registry is written to
        a temporary file first, then renamed over the target file via
        os.replace() which is atomic on the same file-system. This prevents
        registry corruption if the process crashes during a write.
        Furthermore, this operation is constant, meaning os.replace()
        executes in O(1) time, regardless of the registry size.

    Parallel Registries:
        Maintain two synchronized lists:
            _registry:      list of Instruction domain objects.
            _raw_registry:  list of raw dicts used for JSON serialization.
        Both are updated together on every modification to avoid
        redundant serialization.

    Notes:
        - Registry file and its parent directories are created automatically.
        - Registry is loaded from disk on initialization if the file exists.
        - Instruction with event_types containing values not matching
            the incoming event_type is skipped entirely — it is not
            treated as a lower-priority match.
        - A default instruction is provided via __init__:
            A reason that allows top-level objects to set a default
            Instruction types for non-matching events.
        - Registry not checks to None in fields of Instruction, it checks
            for boolean bool(field of instruction) to emit properly empty sequences.
    """

    def __init__(self, registry_path: str, default: Instruction) -> None:
        """
        Initializes the registry and loads persisted Instructions from
        disk only if the registry file exists at provided registry_path,
        So ensure that the paths exists and its a JSON type of file
        with valid format only if you want to load persisted Instructions.
        """
        self._registry_path: Path = Path(registry_path)
        self._default: Instruction = default
        self._registry: list[Instruction] = []
        self._raw_registry: list[dict] = []
        self._load()

    def add(self, instruction: Instruction) -> None:
        """
        Adds an Instruction to both registries and persists immediately.
        New Instructions are appended to the end. Among Instructions with
        equal specificity the first added takes priority.
        """
        self._registry.append(instruction)
        self._raw_registry.append(self._to_dict(instruction))
        self._save()

    def get(self, event: Event) -> Instruction:
        """
        Returns the most specific matching Instruction for the given Event.
        Falls back to the default Instruction if no match is found.
        Uses match_path utility from ../utils to determine the most appropriate
        one of path patterns in instructions.
        """
        best: Optional[Instruction] = None
        best_score: tuple[int, int, int] = (-1, -1, -1)

        for instruction in self._registry:
            path_score = match_path(event.path, instruction.paths)
            if path_score is None:
                continue

            if instruction.event_types and event.event_type in instruction.event_types:
                has_event_type = True
            else:
                has_event_type = False

            if instruction.event_types and not has_event_type:
                continue

            score = (path_score[0], path_score[1], int(has_event_type))

            if score > best_score:
                best = instruction
                best_score = score

        return best if best is not None else self._default

    def show(self) -> Sequence[Instruction]:
        """
        Returns all registered Instruction objects.

        The returned collections is the live internal registry.
        Any direct modifications with snapshots must be applied to both
        the domain registry and the raw registry to keep them in sync.
        If you want to manage the entire registry, not the concrete object
        use public methods (add/delete/clear) of InstructionRegistry.
        """
        return self._registry

    def show_raw(self) -> list[dict]:
        """
        Returns the raw registry as a list of dicts.

        This gives upper layer objects a serialization-friendly view
        without manually decomposing Instruction domain objects. The same
        synchronization requirement applies: changes must be reflected
        in both registries.
        """
        return self._raw_registry

    def delete(self, target: Any) -> None:
        """
        Removes an Instruction from both registries at the given index.
        Silently ignores if the index not exist.
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
        Silently ignores if the registry is already empty.
        """
        self._registry.clear()
        self._raw_registry.clear()
        self._save()

    def _save(self) -> None:
        """
        Atomically persists the raw registry to the JSON file on disk.

        Writes to a temporary file first then renames it over the target
        file via os.replace(). On the same filesystem os.replace() is
        atomic at the kernel level - if the process crashes during the write
        the original registry file remains intact.
        """
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._registry_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._raw_registry, file, indent=4)

        replace(tmp_path, self._registry_path)

    def _load(self) -> None:
        """
        Loads Instructions from the JSON registry file on disk.
        Silently skips loading if the file does not exists,
        So ensure that before providing registry_path.
        Also if file exists, it must be a JSON type file with
        valid format.
        """
        if not self._registry_path.exists():
            return

        with open(self._registry_path, encoding="utf-8") as file:
            self._raw_registry = load(file)

        for raw in self._raw_registry:
            paths = raw.get("paths")
            event_types = raw.get("event_types")
            if event_types:
                event_types = tuple(EventType(et) for et in event_types)
            level = raw.get("level") or "info"
            types = raw.get("types")

            if types:
                types = tuple(InstructionType(inst) for inst in types)

            self._registry.append(
                Instruction(
                    paths=tuple(paths) if paths else None,
                    event_types=event_types if event_types else None,
                    level=LevelType(level),
                    types=types if types else None,
                )
            )

    @staticmethod
    def _to_dict(instruction: Instruction) -> dict:
        """Converts an Instruction domain objects to a raw dict for JSON serialization."""
        return {
            "paths": (list(instruction.paths) if instruction.paths else None),
            "event_types": (
                list(instruction.event_types) if instruction.event_types else None
            ),
            "level": instruction.level,
            "types": (list(instruction.types) if instruction.types else None),
        }
