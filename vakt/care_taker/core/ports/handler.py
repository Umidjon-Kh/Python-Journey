from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import EventContext


class BaseHandler(ABC):
    """
    Abstract base class for all event handlers in the Dispatcher layer.

    A Handler is responsible for performing a single action on an EventContext
    when it is triggered by the Dispatcher. Each handler decides independently
    whether it can handle the current context and whether it has completed
    its work via can_handle() and is_done().

    Dispatcher iterates over all registered handlers in a loop until no handler
    can make further progress. This enables handlers to depend on the results
    of other handlers without explicit coupling between them.

    Implementations Example:
        - Logger: logs event details and final processing state of EventContext.
        - Backuper: creates a Snapshot of the changed file and stores it
            in SnapshotsStorage.
        - Notifier: notifies the user about the event and updates EventContext
            based on the user decision.
        - RollBacker: restores the file to its previous state using a Snapshot.
        - Or any custom handler that fits your use case.

    Notes:
        - Handler must not depend on execution order of other handlers directly.
            Use can_handle() to express dependencies via EventContext state.
        - Handler must not raise exceptions that would crash the Dispatcher.
            All error handling is responsibility of the implementation.
        - Handler does not contain any storage or external state by default.
            If implementation requires it, it must be provided via __init__.
    """

    @abstractmethod
    def can_handle(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler is able to process
        the current EventContext at this moment.
        Called by Dispatcher on every iteration of the handler loop.
        """
        ...

    @abstractmethod
    def handle(self, ctx: EventContext) -> None:
        """
        Performs the handler action on the given EventContext.
        May update EventContext fields to reflect the result of its work.
        Called by Dispatcher only if can_handle() returned True
        and is_done() returned False.
        """
        ...

    @abstractmethod
    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler has completed its work
        for the current EventContext and should not be called again.
        Called by Dispatcher on every iteration of the handler loop.
        """
        ...
