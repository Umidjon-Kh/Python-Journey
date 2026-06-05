from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from .event import EventType
from .semantic_type import SemanticType


class LevelType(SemanticType):
    """
    Processing-layer semantic classification label used to mark
    the severity level of a file system object change.
    It does not perform any evaluation or decision-making on its own.

    It is intended to provide a way to describe the signature of an
    event in the context of a specific object.

    For example:
        Reading a sensitive file such as "/etc/passwd" may be classified
        as SAFE, while modifications to the same file would be classified
        as CRITICAL or SUSPICIOUS, even though both are derived from
        different underlying file system events.

    Why not StrEnum:
        SemanticType is used instead of StrEnum to allow subclassing
        for custom severity level extensions without Python's StrEnum
        subclassing restrictions.

    Notes:
        - LevelType is used only for tagging and categorization of events
            after they are produced by the file system event layer.
        - It does not define rules, logic or heuristics for determining
            event severity. This responsibility belongs to external
            processing components.

    Marks:
        SAFE       - expected, non-risky operations
        INFO       - neutral informational changes
        WARNING    - potentially important but not harmful
        SUSPICIOUS - unexpected or potentially risky behavior
        CRITICAL   - high-impact or security-relevant changes
    """

    SAFE = "safe"
    INFO = "info"
    WARNING = "warning"
    SUSPICIOUS = "suspicious"
    CRITICAL = "critical"


class InstructionType(SemanticType):
    """
    Domain-level instruction action types.

    InstructionType defines what actions should be performed
    when a matching event occurs. It is designed to be extended
    with custom action types for specific use cases.

    For example:
        - LOG:    record the event via Logger handler
        - BACKUP: create a snapshot via BackupInvoker handler
        - ALERT: alerts the user via Alerter

    Why not StrEnum:
        SemanticType is used instead of StrEnum to allow subclassing
        for custom action type extensions without Python's StrEnum
        subclassing restrictions. Custom handlers can introduce their
        own InstructionType subclass values without touching core objects.

    Notes:
        - InstructionType defines the minimal set of actions that can
            be performed on a file system event.
        - It is designed to be extended. Custom subclasses for example:
            CustomInstructionType - may introduce additional action types
            aligned with the capabilities of custom handlers.
        - Such extensions are not automatically supported by the core
            processing pipeline. Consumers introducing custom instruction
            types are responsible for providing compatible handlers that
            explicitly recognize and handle those extended action types.
        - InstructionType is similar to EventType but serves to describe
            what to do with a specific file system event rather than
            what happened.
    """

    LOG = "log"
    BACKUP = "backup"
    ALERT = "alert"


@dataclass(slots=True, frozen=True)
class Instruction:
    """
    An immutable processing-layer object that represents a pre-defined
    behavioral contract for a specific class of file system events.

    An Instruction is not created in response to a single event -
    it is defined in advance by the user or system configuration,
    and describes what actions should be taken when a matching event occurs.

    Unlike Event (which describes what happened), Instruction describes what
    should happen as a consequence. It is the bridge between observation
    and action in the pipeline.

    Attributes:
        - event_types: Collection of EventType values this instruction applies to.
                        An incoming event matches if its type is in the collection.
                        If None, instruction applies to all event types.
        - paths:       Glob patterns of file system paths the instruction applies to.
                        If None, instruction applies to all paths unconditionally.
                        Patterns follow the Path Syntax Protocol described below.
                        When multiple patterns match a single path, the highest-priority
                        pattern wins. On equal priority, the pattern with more concrete
                        characters (fewer wildcards) wins.
        - level:       Semantic classification of the event.
                        Used by handlers to decide how to present or react to the event.
        - types:       Collection of InstructionType values that define what actions
                        should be performed when a matching event occurs.
                        If None, no actions are performed.

    Path Syntax Protocol:
        Patterns are matched against the full absolute path of an incoming event.
        Six pattern types are recognized, ordered from highest to lowest priority:

        Priority 6 — Exact match:
            /etc/passwd
            /var/log/syslog
            Matches only the exact absolute path. Highest priority — always
            preferred over any wildcard pattern when both match.

        Priority 5 — Segment wildcard:
            /etc/settings*          matches /etc/settings.conf, /etc/settings_backup
            /etc/*.conf             matches /etc/app.conf, /etc/nginx.conf
            /var/log/app_*_v2.log   pieces within the segment must appear in order
            A wildcard (*) within a path segment. Must contain a "/" (rooted) and
            must not end with "/*" (that is the non-recursive pattern). ** is not
            allowed in this category. Multiple wildcards within one segment are
            supported and matched sequentially.

        Priority 4 — Deep glob with anchors:
            Patterns containing ** with at least one concrete anchor segment
            before or after it. Split into three sub-levels by suffix type:

            Priority 4.3 — Concrete anchor (highest among deep globs):
                /etc/**/passwd          matches /etc/passwd, /etc/ssl/passwd
                /etc/**/*.conf          matches /etc/app.conf, /etc/ssl/nginx.conf
                /var/**/app_*.log       matches any path with that filename at any depth
                ** absorbs zero or more segments; suffix is a concrete name or
                segment wildcard — not /* or /**.

            Priority 4.2 — Deep glob + recursive suffix:
                /etc/**/folder/**       matches anything inside folder/ at any depth
                                        under /etc/
                /var/**/logs/**         matches any descendant of any logs/ under /var/

            Priority 4.1 — Deep glob + non-recursive suffix:
                /etc/**/folder/*        matches only direct children of folder/
                                        wherever folder/ appears under /etc/
                /var/**/logs/*          matches only direct children of any logs/ under /var/

                Priority 3 — Non-recursive:
                    /etc/*
                    /var/log/
                    Matches only the direct children of the base path. Does not descend
                    into subdirectories. Trailing "/" is treated identically to "/*".

        Priority 2 — Recursive:
            /etc/**
            /var/log/**
            Matches any descendant at any depth under the base path.
            /etc/passwd, /etc/ssl/cert.pem, /etc/ssl/certs/ca-bundle.pem all match
            /etc/**. Lower priority than all anchored patterns, so /etc/**/passwd
            (Priority 4) always beats /etc/** (Priority 2) for /etc/ssl/passwd.

        Priority 1 — Global name / wildcard (lowest):
            passwd                  matches any path whose filename is "passwd"
            *.conf                  matches any path whose filename ends with .conf
            app_*                   matches any path whose filename starts with app_
            No "/" in the pattern — matched against the filename component only,
            regardless of the directory. Lowest priority, always loses to any
            rooted pattern when both match.

        Invalid patterns (not supported, produce no match):
            /**          - bare global recursive, no base path
            /**/**       - chained globals
            **/**        - unrooted double glob
            /**/*        - bare global non-recursive

        Tiebreaker (equal priority):
            Among patterns at the same priority level, the one with more concrete
            characters wins (len(pattern) after removing all "*" characters).
            /etc/ssl/** beats /etc/** for /etc/ssl/cert.pem (longer concrete base).
            /etc/settings.conf beats /etc/*.conf if both somehow reach the same
            priority (longer concrete part wins).

    Notes:
        - Instruction is frozen because behavioral contracts must not change at runtime.
            Any modification requires creating a new Instruction.
        - Instruction does not contain processing logic. It is a pure data object.
        - Multiple Instructions may match a single event. Resolution strategy
            (e.g. priority, first-match) is the responsibility of InstructionRegistry.
        - If you use a Custom EventType you need to provide it inherited from EventType and
            add handlers that support those custom event types.
        - If you use a Custom InstructionType you need to provide it inherited from
            InstructionType and add handlers that support those custom instruction types.

    Example:
        event_types: Sequence[CrossPlatformEventType.FILE_MODIFIED]
        paths:       Sequence["/etc/passwd", "/etc/ssl/**", "/var/log/*.log"]
        level:       LevelType.SUSPICIOUS
        types:       Sequence[InstructionType.LOG, InstructionType.BACKUP]
    """

    event_types: Optional[Sequence[EventType]] = None
    paths: Optional[Sequence[str]] = None
    level: LevelType = LevelType.INFO  # type: ignore[assignment]
    types: Optional[Sequence[InstructionType]] = None
