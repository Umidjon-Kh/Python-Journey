from __future__ import annotations

from collections.abc import Sequence
from typing import Optional


def _match_segment(segment: str, block: str) -> bool:
    """
    Returns True if a single path segment matches a pattern block.

    Supports any number of wildcards within a single segment:
        pass*           matches segments with pass prefix
        *.log           matches all segments that ends with .log
        les*on_*        matches segments with properly order of pieces in block.
        *               matches any single segment

    Why find() with position instead of startswith/endswith:
        Multiple wildcards in one block require sequential scaning.
        find(piece, position) advances through the segment ensuring all
        pieces are found in order without overlapping.

    Prefix and suffix anchoring:
        If the block does not start with * in the first place must appear
        at position 0. If the block does not end with * the segment
        must end with the last piece.
    """
    if "*" not in block:
        return segment == block

    pieces = block.split("*")
    position = 0

    for index, piece in enumerate(pieces):
        if not piece:
            continue
        found = segment.find(piece, position)
        if found == -1:
            return False
        if index == 0 and not block.startswith("*") and found != 0:
            return False
        position = found + len(piece)

    if pieces[-1] and not block.endswith("*") and not segment.endswith(pieces[-1]):
        return False

    return True


def _match_glob(pattern: str, path: str) -> bool:
    """
    Returns True if path matches a pattern containing **/ sequences.

    ** matches zero or more path segments at any depth. All non-**
    segments must match exactly or via _match_segment wildcards.

    Why recursive approach:
        ** can absorb any number of segments. At each ** we try
        consuming zero segments first, then one more on each
        recursive call until either a match is found or the
        path is exhausted.

    Examples:
        /etc/**/passwd          matches /etc/passwd, /etc/ssl/passwd
        /etc/ssl/**/cert.pem    matches /etc/ssl/cert.pem, /etc/ssl/src/core/cert.pem
        /etc/**/*.log           matches /etc/app.log, /etc/logs/app.log
    """
    pattern_segs = pattern.split("/")
    path_segs = path.split("/")

    def match(pi: int, si: int) -> bool:
        while pi < len(pattern_segs):
            block = pattern_segs[pi]
            if block == "**":
                # try consuming zero or more path segments
                for skip in range(len(path_segs) - si + 1):
                    if match(pi + 1, si + skip):
                        return True
                return False
            elif si >= len(path_segs):
                return False
            elif not _match_segment(path_segs[si], block):
                return False

            pi += 1
            si += 1

        return si == len(path_segs)

    return match(0, 0)


def match_path(
    path: str, patterns: Optional[Sequence[str]]
) -> Optional[tuple[int, int]]:
    """
    Returns a (priority, tiebreaker) score tuple if the event path
    matches any pattern in received patterns sequence, or None if no match.

    Priority levels (higher wins):
        6 - exact match:            /etc/settings.conf
        5 - segment wildcard:       /etc/settings* or /etc/*.conf
        4 - deep glob with anchors: /etc/**/settings.conf or /etc/**/*.conf
        3 - non-recursive:          /etc/*
        2 - recursive:              /etc/**
        1 - global name/wildcard:   settings.conf or settings* or *.conf

    Tiebreaker:
        len(pattern.replace("*", "")) - longer concrete pattern wins.
        /etc/ssl/** beats /etc/** for /etc/ssl/cert.pem
        /etc/settings beats /etc/*.conf if both match (longer concrete part)

    Notes:
        - non-recursive /* matches only direct children of base.
        - recursive /** matches any descendant at any depth.
        - global patterns (no /) match any path with that file name.
        - Patterns are evaluated independently, best score is kept and returns it.
    """
    if not patterns:
        return (1, 0)

    best: Optional[tuple[int, int]] = None
    parent, file_name = path.rsplit("/", maxsplit=1)

    def update(score: tuple[int, int]) -> None:
        nonlocal best
        if best is None or score > best:
            best = score

    for pattern in patterns:
        tiebreaker = len(pattern.replace("*", ""))

        # 1.Scenario: Exact match
        if pattern == path:
            return (6, tiebreaker)

        base = pattern.rsplit("/", maxsplit=1)[0] if "/" in pattern else ""

        # 2.Scenario: Segment wildcard
        if (
            "*" in pattern  # has a wildcard in pattern
            and "**" not in pattern  # not deep glob pattern
            and "/" in pattern  # not a global name
            and not pattern.endswith("/*")  # not non-recursive pattern
        ):
            # WildCard segment includes full size of pattern to work properly.
            # Thats why i used _match_glob()
            if _match_glob(pattern, path):
                update((5, tiebreaker))

        # 3.Scenario: Deep glob with anchors
        elif "**" in pattern and pattern not in (base + "/**", "/**"):
            if _match_glob(pattern, path):
                update((4, tiebreaker))

        # 4.Scenario: Non-recursive
        elif pattern.endswith(("/*", "/")):
            if parent == base:
                update((3, tiebreaker))

        # 5.Scenario: Recursive
        elif pattern.endswith("/**"):
            if path.startswith(base + "/"):
                update((2, len(base)))

        elif "/" not in pattern:
            if _match_segment(file_name, pattern):
                update((1, tiebreaker))

    return best
