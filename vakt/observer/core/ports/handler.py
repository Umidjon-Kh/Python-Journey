from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..domain import EventContext


class BaseHandler(ABC):
    """
    Abstract base class for all event handlers in the Dispatcher layer.

    A Handler is responsible for performing a single action on an EventContext
    when it is triggered by the Dispatcher loop. Each handler decides independently
    whether it can handle the current context and whether it has completed its work.

    Handler Loop Mechanics:
        Dispatcher iterates over all registered handlers in a loop until no handler
        can make further progress. On each iteration Dispatcher checks can_handle()
        and is_done() for each handler. This enables handlers to depend on results
        of other handlers without explicit coupling between them - instead of direct
        dependencies, handlers express their requirements via EventContext state.

    Handler Categories:
        Handlers are not strictly categorized but can be classified by behavior:

        - Phantom: does not depend on specific handlers, only on EventContext state.
            Excludes itself from handlers_count on first contact to avoid infinite
            loop caused by multiple phantom handlers waiting for each other.
            Finishes when all non-phantom handlers have completed their work.
            Example: Logger, StatsCollector.

        - Non-Phantom: performs a specific action and increments processed_handlers
            after completion. Decrements handlers_count if it cannot process
            the current event.
            Example: Backuper, RollBacker, Notifier.

        - State Depended: triggers only when specific actions have been performed
            by other handlers. Uses ctx.performed to check if required actions
            are completed before proceeding.
            Example: A handler that encrypts a file only after it has been backed up.

        - Lock Depended: acquires a PathLock during processing to prevent external
            processes from modifying the file system object while working with it.
            Uses ignoring_paths to prevent Dispatcher from processing events
            caused by its own file system modifications.
            Example: RollBacker.

        - End Runner: triggers only after all non-phantom handlers have completed.
            Similar to phantom but runs only once at the end.
            Example: A handler that sends a final report after all actions are done.

    Performed Actions:
        After completing a specific action, handlers should append the corresponding
        InstructionType to ctx.performed. This enables State Depended handlers and
        phantom handlers to monitor what actions have been performed without
        depending on specific handler implementations.

    Ignoring Paths Mechanism:
        ignoring_paths is an optional shared dict[str, int] provided by Dispatcher on
        initialization. If a handler needs to prevent Dispatcher from processing
        specific paths (for example while RollBacker is restoring a file), it must
        set ignoring_paths to an empty dict instead of None to signal Dispatcher
        that this handler wants to participate in the path ignoring mechanism.
        Dispatcher will then inject the shared ignoring_paths dict into this handler.
        Each key is an absolute path and its value is the number of incoming events
        to suppress for that path. When the counter reaches zero the path is removed
        from the dict automatically by Dispatcher.
        Handlers that do not need this mechanism should leave ignoring_paths as None.


    Implementations Example:
        - Logger:     phantom handler that logs EventContext state changes.
        - Backuper:   creates a backup via SnapshotsRegistry.
        - Notifier:   notifies the user about the event.
        - RollBacker: restores the file to its previous state via SnapshotsRegistry.
        - Or any custom handler that fits your use case.

    Notes:
        - Handler must not depend on execution order of other handlers directly.
            Use can_handle() to express dependencies via EventContext state.
        - Handler must not raise exceptions that would crash the Dispatcher.
            All error handling is the responsibility of the implementation.
        - Handler does not contain any storage or external state by default.
            If implementation requires it, it must be provided via __init__.
        - If handler uses Ignoring Paths Mechanism, the SnapshotsRegistryStore
            and PathLock instances are injected automatically, without any
            request from the handlers. So verify that the handler's "__init__"
            method accepts these arguments.
    """

    ignoring_paths: Optional[dict[str, int]] = None

    @abstractmethod
    def can_handle(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler is able to process the current
        EventContext at this moment.
        Phantom handlers must decrement ctx.handlers_count on first contact
        regardless of whether they can handle the event or not.
        Non-phantom handlers must decrement ctx.handlers_count if they
        cannot process the current event.
        Called by Dispatcher on every iteration of the handler loop.
        """
        ...

    @abstractmethod
    def handle(self, ctx: EventContext) -> None:
        """
        Performs the handler action on the given EventContext.
        Non-phantom handlers must increment ctx.processed_handlers
        after completing their work.
        Handlers should append the corresponding InstructionType to
        ctx.performed after completing a specific action.
        Called by Dispatcher only if can_handle() returned True
        and is_done() returned False.
        """
        ...

    @abstractmethod
    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler has completed its work
        for the current EventContext and should not be called again.
        Phantom handlers return True when ctx.processed_handlers
        equals ctx.handlers_count indicating all non-phantom handlers
        have finished their work.
        Called by Dispatcher on every iteration of the handler loop.
        """
        ...
