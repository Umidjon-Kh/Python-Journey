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

        Path scoring (higher is more specific):
            4 - exact path match:       /etc/passwd == /etc/passwd
            3 - non-recursive match:    /etc/*      matches /etc/passwd
            2 - recursive match:        /etc/**     matches /etc/ssl/cert.pem
            1 - paths is None:          matches any path it is semantic to root/**

        Within the same path score level, longer base paths win:
            /etc/ssl/** beats /etc/** for the path /etc/ssl/cert.pem

        EventType scoring:
            1 - event.event_type is found in instruction.event_types
            0 - instruction.event_type is None

        Full priority table (descending):
            1. exact path    | event_type equal
            2. exact path    | event_type is None
            3. /*            | event_type equal
            4. /*            | event_type is None
            5. /**           | event_type equal
            6. /**           | event_type is None
            7. paths is None | event_type equal
            8. paths is None | event_type is None


    Atomic Persistence:
        All registry modifications are persisted atomically using a
        write-to-temp-then-replace strategy. The registry is written to
        a temporary file first, then renamed over the target file via
        os.replace() which is atomic on the same file-system. This prevents
        registry corruptionif the process crashes during a write.
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
            for boolean bool(field of instructon) to emit properly empty sequences.
    """

    def __init__(self, registry_path: str, default: Instruction) -> None:
        """
        Initializes the registry and loads persisted Instructions from disk.
        Ensure that the path file is exists and its a JSON file in correct format.
        """
        self._registry_path: Path = Path(registry_path)
        self._default: Instruction = default
        self._registry: list[Instruction] = []
        self._raw_registry: list[dict] = []
        self._load()

    def add(self, instruction: Instruction) -> None:
        """
        Adds an Instruction to both registries and persists immediately.
        New Instrcutions are appended to the end. Among Instrcutions with
        equal specificity the first added takes priority.
        """
        self._registry.append(instruction)
        self._raw_registry.append(self._to_dict(instruction))
        self._save()

    def get(self, event: Event) -> Instruction:
        """
        Returns the most specific matching Instruction for the given Event.
        Falls back to the default Instruction if no match is found.
        """
        best: Optional[Instruction] = None
        best_score: tuple[int, int, int] = (-1, -1, -1)

        for instruction in self._registry:
            path_score = self._match_path(event.path, instruction)
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
        """Returns all Instruction from the registry."""
        return self._registry.copy()

    def show_raw(self) -> list[dict]:
        """Returns raw registry metadata, not original only copy."""
        return self._raw_registry.copy()

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

    @staticmethod
    def _match_path(path: str, instruction: Instruction) -> Optional[tuple[int, int]]:
        """
        Returns a (path_level, base_len) score tuple if the event path
        matches any pattern in instruction.paths, or None if no match.

        Score meaning:
            path_level: 4=exact, 3=non-recursive, 2=recursive, 1=None
            base_len:   length of matched base path used as tiebreaker
                        when two patterns have the same path_level.

        Why base_len as tiebreaker:
            /etc/ssl/** is more specific than /etc/** for /etc/ssl/cert.pem/
            Both have path_level=2 but /etc/ssl has a longer base
            so (2, 8) beats (3, 4).
            Also in other situations that needs more specifity.

        Non-recursive matching (/*):
            Matches only direct children of the base directory.
            /etc/* matches /etc/passwd but not /etc/ssl/cert.pem.
            Checked by comparing the event path parent to the pattern base.

        Recursive matching (/**):
            Matches any descendant of the base directory at any depth.
            /etc/** matches /etc/passwd and /etc/ssl/cert.pem.
            Checked by verifying the event path starts with base + "/".
        """
        if not instruction.paths:
            return (1, 0)

        best: Optional[tuple[int, int]] = None

        for pattern in instruction.paths:
            if pattern == path:
                return (4, len(path))

            if pattern.endswith("/**"):
                base = pattern.rsplit("/", maxsplit=1)[0]
                if path.startswith(base + "/"):
                    score = (2, len(base))
                    if best is None or score > best:
                        best = score

            elif pattern.endswith(("/*", "/")):
                base = pattern.rsplit("/", maxsplit=1)[0]
                parent = path.rsplit("/", maxsplit=1)[0]
                if parent == base:
                    score = (3, len(base))
                    if best is None or score > best:
                        best = score

        return best
