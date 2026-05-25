from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import EventContext
from ..helpers import ToolKit


class BaseHandler(ABC):
    """
    Abstract base class for all event handlers in the Dispatcher layer.

    A Handler is responsible for performing a single action on an EventContext
    when it is triggered by the Dispatcher loop. Each handler decides independently
    whether it can handle the current context and whether it has completed its work.

    Handler Loop Mechanism:
        Dispatcher iterates over all registered handlers in a loop until no handler
        can make further progress. On each iteration Dispatcher checks can_handle()
        and is_done() for each handler. This enables handler to depend on results
        of other handlers without explicit coupling between them - instead of direct
        dependencies, handlers express their requirements via EventContext performed
        actions sequence state and shared playground buffer (EventContext.metadata) or
        handlers_count and processed_handlers depended on their category realization.

    Handler Categories:
        Handlers are not strictly categorized but can be classified by behavior:

        - Phantom: does not depend on specific handlers, only on EventContext state.
            Excludes itself from handlers_count on the first contact to avoid infinite
            loop caused by multiple phantom handlers waiting for each other.
            Finishes when all non-phantom handlers have completed their work.
            Implementations: SysLogger, StatsCollector.

        - Invoker: invokes a specific actions based on the Instruction types.
            Depends on external objects such as a helpers from ToolKit container.
            Decrements handlers_count if it cannot process the current event.
            Example: BackupInvoker that calls create() method from SnapshotsRegistryStore
            implementation, or others: RestoreInvoker, AntiMutator.
            Note: Invokers depends on state of Instruction.types that can be managed
                with ResponseCollectors or other handler implementations that modifies
                instruction.types sequence.

        - State Depended: triggers only when specific actions have been performed
            by other handlers. Uses ctx.performed to check if required actions
            are completed before proceeding.
            Example: SnapshotsRotator that triggers only file system object has
                been backed up

        - EndRunner: triggers only after all non-phantom handlers have completed
            their work. Similar to phantom handler but runs only once at the end.
            Example: Reporter that send a final report after all actions are done.

    Performed Actions:
        After completing a specific action, handlers should append the corresponding
        InstructionType to ctx.performed. This enables State Depended handlers and
        phantom handlers monitor what actions have been performed without
        depending on specific handler implementations.

    Why BaseHandler require the __init__ method to adhere the contract and
    what is the ToolKit object:
        This is intentional, designed to avoid issues when instantiating
        the handler implementation during initialization, as different
        implementations require different parameters.

        The main goal is to adhere the open/closed principle and keep
        the code clean, strict, and predictable. To achieve this, a pragmatic
        approach was developed using ToolKit object.

        ToolKit provides additional objects (services, contexts, helper utilities)
        required by handlers. This frees developers from the hassle of adjusting
        constructor signatures for each specific case.

        Furthermore, this solution allows the source code to remain unchanged
        when adding a new handler implementation. Even if you're creating
        a very specific handler that depends on many factors simultaneously,
        you already have ready-made mechanisms:
            - EventContext.performed
            - EventContext.metadata shared buffer (playground)
            - ToolKit itself

        All this provides flexibility without breaking the contract.
        If an implementation does not require ToolKit, just ignore it during
        initialization by adding it as a stub argument.

    Ignoring Paths Mechanism:
        ignoring_paths is an attribute of the ToolKit shared dictionary (dict[str, int]).
        It is used to ensure that the handler adds (or increments) a counter to this
        dictionary each time it interacts with file system object: path: count,
        where count is the number of interactions.

        When the Dispatcher receives an event from the buffer, it first checks whether
        the path is present in ignoring_paths. If the path is present, the event is
        ignored (skipped). Before discarding the event, the dispatcher decrements the
        counter by 1. If, after decrementing. the counter reaches 0, the entry is removed
        from dictionary.

        This is done to avoid processing events generated by the daemon itself.

    Notes:
        - Handler must not depend on execution order of other handlers directly.
            Use can_handle() to express dependencies via EventContext state.
        - Handler must not raise exceptions that would crash Dispatcher.
            All error handling is the responsibility of the implementation.
    """

    @abstractmethod
    def __init__(self, toolkit: ToolKit) -> None:
        """
        Initializes all attributes of handler instance.

        Args:
            toolkit: ToolKit object that contains additional tools to help.
        """
        ...

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
