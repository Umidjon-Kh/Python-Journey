from __future__ import annotations

from logging import (
    CRITICAL,
    DEBUG,
    INFO,
    WARNING,
    Formatter,
    StreamHandler,
    getLogger,
)
from sys import stdout
from typing import Optional

from ...core import (
    BaseHandler,
    EventContext,
    LevelType,
)

_LEVEL_MAP = {
    LevelType.SAFE: DEBUG,
    LevelType.INFO: INFO,
    LevelType.WARNING: WARNING,
    LevelType.SUSPICIOUS: WARNING,
    LevelType.CRITICAL: CRITICAL,
}

_handler = StreamHandler(stdout)
_handler.setFormatter(
    Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)

_logger = getLogger(__name__)
_logger.addHandler(_handler)
_logger.setLevel(DEBUG)


class Logger(BaseHandler):
    """
    Phantom handler responsible for logging EventContext state changes,

    Logger is a phantom handler - it does not depend on any specific handlers,
    only on EventContext state. It logs every time something changes in EventContext
    while the dispatcher loop is running, and finishes when all non-phantom handlers
    have completed their work.

    Why phantom handler excludes itself from handlers_count on first contact:
        If there are multiple phantom handlers they would wait for each
        other to finish indefinitely since none of them adds to processed_handlers.
        By decrementing handlers_count on first contact, phantom handlers becomes
        invisible to each other.

    Why _last_ctx is reset to None when done:
        Without reset, the next event's ctx would be compared against the
        previous event's ctx state causing incorrect can_handle behavior.

    Why logging level comes from instruction.level:
        Level describes the severity of the event itself not the action
        performed by the handler. This enables proper monitoring and
        classification of file system changes.

    Notes:
        - Logger never increments processed_handlers.
        - Logger always decrements handlers_count once on first contact
            with new event regardless of should_log value to avoid infinite loop.
        = Logger resets _last_ctx and _excluded to None when is_done returns True.
        - ignoring_paths is None because Logger does not modify file system.
        - Logger is not triggered on every single change of event ctx state.
            Instead, it only triggers when the handler loop gets to its queue.
    """

    ignoring_paths = None

    def __init__(self) -> None:
        """Initializing attributes of instance with default states."""
        self._last_ctx: Optional[EventContext] = None
        self._excluded: bool = False

    def can_handle(self, ctx: EventContext) -> bool:
        """
        Always excludes itself from handlers_count on first contact
        to avoid infinite loop even if should_log=False.
        Returns True if EventContext state changes since last log.
        Returns False if should_log=False in instruction.
        """
        if not self._excluded:
            ctx.handlers_count -= 1
            self._excluded = True

        if not ctx.instruction.should_log:
            return False

        return (
            ctx.backed_up != self._last_ctx.backed_up  # type: ignore[union-attr]
            or ctx.rolled_back != self._last_ctx.rolled_back  # type: ignore[union-attr]
            or ctx.snapshot != self._last_ctx.snapshot  # type: ignore[union-attr]
            or ctx.processed_handlers != self._last_ctx.processed_handlers  # type: ignore[union-attr]
        )

    def handle(self, ctx: EventContext) -> None:
        """
        Logs current EventContext state with level from instruction.
        Saves current ctx as last seen state.
        """
        level = _LEVEL_MAP.get(ctx.instruction.level, INFO)

        _logger.log(
            level,
            "Event [%s] %s | backed_up=%s rolled_back=%s snapshot=%s",
            ctx.event.event_type,
            ctx.event.path,
            ctx.backed_up,
            ctx.rolled_back,
            ctx.snapshot.backup_path if ctx.snapshot else None,
        )

        self._last_ctx = ctx

    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True when all non-phantom handlers have finished.
        Resets internal state for the next event.
        """
        done = ctx.processed_handlers == ctx.handlers_count

        if done:
            self._last_ctx = None
            self._excluded = False

        return done
