from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from .event import EventType


class LevelType(StrEnum):
    """
    Dispatcher-layer object Leveltype is a semantic classification
    label used to mark the level of a file system object change.
    It does not perform any evaluation or decision-making on its own.

    it is intended to provide way to describe
    the signature of an event in the context of specific object.

    for example:
        reading a sensitive file such as /etc/passwd may be classified as a SAFE,
        while modifications to the same file would be classified as a CRITICAL or  SUSPICIOUS,
        even though both are derived from different underlying file system events.

    Notes:
        - LevelType is used only for tagging and categorization of events after they are
            produced by the file system event layer,.
        - it does not define rules, logic or heuristics for determining event severity.
            This responsibility belongs to external processing components.

    Marks:
        SAFE - expected, non-risky operations
        INFO - neutral informational changes
        WARNING - potentially important but not harmful
        SUSPICIOUS - unexpected or potentially risky behavior
        CRITICAL - high-impact or potentially or security-relevant changes
    """

    SAFE = "safe"
    INFO = "info"
    WARNING = "warning"
    SUSPICIOUS = "suspicious"
    CRITICAL = "critical"


@dataclass(slots=True, frozen=True)
class Instruction:
    """
    An Immutable, dispatcher-layer object that represents a pre-defined
    behavioral contract for specific class of o file system events.

    An instruction is not created in response to a single event -
    it is defined in advance by the user or system configuration,
    and describes what actions should be taken when a matching event occurs.

    -------------------------------------------------------------------------------------------
    ###########################################################################
    # InstructionManager is responsible for matching incoming Events against  #
    # all registered Instruction in InstructionStorage and selecting the most #
    # appropriate one. If not match is found in storage,                      #
    # a default Instruction is used.                                          #
    ###########################################################################
    ###########################################################################################
    # CHANGELOG:                                                                              #
    #     - InstructionStorage is responsible for matching incoming Events against            #
    #         all registered Instructions in itself. It enables to give other developers      #
    #         to implement their own logic in giving most appropriate one.                    #
    #     - But InstructionManager doesn't disappears it serves like wrapper of storage and   #
    #         returns default instruction if not found any matching instruction to incoming   #
    #         Event. This was done deliberately to add another logic for instructions.        #
    ###########################################################################################
    -------------------------------------------------------------------------------------------


    Unlike Event (which describes what happened ), Instruction describes what
    should happen as a consequence. it is the bridge between observation and action
    in the pipe line.

    Attributes:
        - event_type:    Collection of EventType values this instruction applies to.
                            An incoming event matches if its type is in this collection.
        - paths:         Glob Patterns of file system paths the instrcution applies to.
        - level:         Semantic classification of the event path.
                            Used by handlers to decide how to present or react to the event.
        - should_notify: Whether the user should be notified via Notifier (default=False)
        - should_log:    Whether the matched event should be recorded by the Logger (default=True)
        - should_backup: Whether a Snapshot should be created by the Backuper (default=False)

    Notes:
        - Instruction is frozen because behavioral contracts must be not change at runtime.
            Any modifications requires creating a new instruction.
        - instruction does not contain processing logic. It is a pure data object.
        - Multiple Instruction may match a single event, Resolution strategy
            (e.g. priority, first-match) is the responsibility of InstructionStorage.
        - If you use Custom Event Type you need to provide it inherited from EventType and
            add handlers that support those custom event types.
        - If you want to apply one instruction to all events in provided path, use "all".
        - In path glob patterns field if you want to apply instruction to all
            objects in directory path you need to use "/*" in the end of directory name.
            If you want to apply instrcution to all objects recursively use "/**".

    Example:
        event_types:     Sequence[FILE_WRITE, DIR_RENAME]
        paths:           Sequence["/etc/passwd", "/user/local/*"]
        level:           LevelType.SUSPICIOUS
        should_log:      True
        should_backup:   True
        should_notify:   True
    """

    event_types: Optional[Sequence[EventType]] = None
    paths: Optional[Sequence[str]] = None
    level: Optional[LevelType] = None
    should_log: bool = True
    should_backup: bool = False
    should_notify: bool = False
