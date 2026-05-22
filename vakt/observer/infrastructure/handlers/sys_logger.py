from __future__ import annotations

from logging import (
    CRITICAL,
    DEBUG,
    INFO,
    WARNING,
    FileHandler,
    Formatter,
    Logger,
    getLogger,
)
from os import environ
from pathlib import Path
from typing import Optional

from ...core import (
    BaseHandler,
    EventContext,
    InstructionType,
    LevelType,
)

_LEVEL_MAP = {
    LevelType.SAFE: DEBUG,
    LevelType.INFO: INFO,
    LevelType.WARNING: WARNING,
    LevelType.SUSPICIOUS: WARNING,
    LevelType.CRITICAL: CRITICAL,
}


class SysLogger(BaseHandler):
    """
    Phantom handler responsible for logging EventContext state changes
    to a file throughout the handler loop lifecycle.

    SysLogger is a phantom handler - it does not perform any action on
    the file system and never increments processed_handlers. Instead it
    observes EventContext state on every iteration and logs when
    something changes, providing a continiuos audit trail of what happened during
    event processing.

    Why phantom handler decrements handlers_count on first contact:
        If multiple phantom handlers are registered they would wait for each
        other to complete indefinitely since none of them increments
        processed_handlers. By decrementing handlers_count once on first
        contact, a phantom handler becomes invisible to other phantom handlers
        and the loop can terminate correctly.

    Why _last_ctx is compared on every can_handle call:
        SysLogger logs only when something meaningful changes in EventContext -
        a new snapshot, a new performed action, or a change in processed handlers.
        Logging on every iteration without checking for changes would produce
        duplicate entries that add noise without value.

    Why _last_ctx and _excluded reset when is_done returns True:
        EventContext is ephemeral - it exists only for single event. Without
        reset, the next  event's context would be compared against the previous
        event's state producing incorrect can_handle results.

    Why logging level comes from instruction.level:
        Level describes the severity of the event itself not the action
        performed by the handler. This enables proper classification and
        filtering of file system changes in external log management tools.

    Why is VAKT_SANCTUM used as the path to save the log file instead of
    an explicit path argument injected from the top-level object:
        Upper layer objects (bootstrap, Dispatcher) do not know what each
        handler implementation requires internally. Asking upper layer to
        provide a log path would create unnecessary coupling between the
        bootstrap configuration and handler internals. VAKT_SANCTUM is a
        shared environment convention that any implementation can read
        independently without involving upper layer objects.

    Notes:
        - SysLogger never increments processed_handlers.
        - SysLogger always decrements handlers_count exactly once on first
            contact with a new event regardless of InstructionType.LOG presence
            to avoid infinite loop caused by multiple phantom handlers.
        - SysLogger resets _last_ctx and _excluded when is_done returns True.
        - ignoring_paths is None because SysLogger does not modify file system.
        - SysLogger reads VAKT_SANCTUM environment variable to determine the
            log file location. Upper layer objects do not need to provide any
            path — each handler resolves its own dependencies independently
            to avoid coupling bootstrap configuration to handler internals.
    """

    ignoring_paths = None

    _DEFAULT_VAULT = "/var/lib/.vakt"

    def __init__(self) -> None:
        """
        Initializes all attributes of handler and configures a dedicated FileHandler
        that writes logs to the common storage space of daemon VAKT_SANCTUM.
        """
        self._last_ctx: Optional[EventContext] = None
        self._excluded: bool = False
        self._log: Logger = self._setup_logger()

    def can_handle(self, ctx: EventContext) -> bool:
        """
        Decrements handlers_count once on first contact to exclude itself
        from the phantom handler infinite loop.
        Returns False if InstructionType.LOG is not in instruction.types.
        Returns True if EventContext state has changed since last log entry.
        """
        if not self._excluded:
            ctx.handlers_count -= 1
            self._excluded = True

        if ctx.instruction.types and InstructionType.LOG not in ctx.instruction.types:
            return False

        if self._last_ctx is None:
            return True

        return (
            ctx.snapshot != self._last_ctx.snapshot
            or ctx.performed != self._last_ctx.performed
            or ctx.processed_handlers != self._last_ctx.processed_handlers
        )

    def handle(self, ctx: EventContext) -> None:
        """
        Logs current EventContext state at the level defined by instruction.level.
        Saves the current ctx as the last seen state for change detection.
        """
        level = _LEVEL_MAP.get(ctx.instruction.level, INFO)

        self._log.log(
            level,
            "event=[%s] path=%s | performed=%s | snapshot=%s | handlers=%d/%d",
            ctx.event.event_type,
            ctx.event.path,
            [str(t) for t in ctx.performed],
            ctx.snapshot.backup_path if ctx.snapshot else None,
            ctx.processed_handlers,
            ctx.handlers_count,
        )

        self._last_ctx = ctx

    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True when all non-phantom handlers have finished.
        Resets internal state to prepare for the next event.
        """
        done = ctx.processed_handlers == ctx.handlers_count

        if done:
            self._last_ctx = None
            self._excluded = False

        return done

    def _setup_logger(self) -> Logger:
        """
        Configures a dedicated FileHandler that writes all performed
        operations to the EventContext. Uses a common storage of daemon
        VAKT_SANCTUM to write logs. Also SysLogger is not responsible for
        rotation and other external log management operations.
        Returns the configured Logger instance.
        """
        vault = environ.get("VAKT_SANCTUM", self._DEFAULT_VAULT)
        log_path = Path(vault + "/handlers_data/sys_logger.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = getLogger(__name__)

        if not logger.handlers:
            handler = FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(
                Formatter(
                    fmt="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)

        return logger
