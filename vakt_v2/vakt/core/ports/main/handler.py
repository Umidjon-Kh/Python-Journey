from __future__ import annotations

from abc import abstractmethod

from ...domain import EventContext
from ..protocols import AssemblyProtocol


class BaseHandler(AssemblyProtocol):
    """
    Abstract base class for all event handlers in the Dispatcher layer.

    A handler is simultaneously responsible for three things:
        1. Deciding whether it can process the incoming event in its current state.
        2. Deciding whether it has finished all its work for the given event.
        3. Processing the incoming event when both conditions above are satisfied.

    The Dispatcher does not decide what happens to an event — every handler
    decides for itself when, how, and whether it can process it. The Dispatcher
    only triggers handlers by asking these questions and, if the answer is yes,
    delivers the event for processing.

    Handler Loop Mechanism:
        The Dispatcher iterates over all registered handlers in a loop until no
        handler can make further progress on the current event. On each iteration
        the Dispatcher asks every handler can_handle() and is_done(). If both
        conditions are satisfied the handler is invoked with the current EventContext.

        This mechanism gives handlers the ability to implicitly depend on the
        results of other handlers without any direct coupling between them.
        Handlers express their dependencies entirely through EventContext state:
        the performed actions sequence, the shared metadata playground, and the
        handlers_count / processed_handlers counters. EventContext is strictly
        ephemeral — it exists only for the lifetime of a single event's processing
        cycle and disappears once all handlers have finished.

    Handler Categories:
        Handlers are not formally categorized in the codebase but can be
        classified by their behavior pattern:

        Phantom:
            Does not depend on specific other handlers — only on the overall
            state of EventContext. On first contact with an EventContext a phantom
            handler decrements ctx.handlers_count by one, permanently excluding itself
            from the loop termination condition (handlers_count == processed_handlers).
            This makes the phantom handler invisible to other handlers — especially to
            other phantom handlers — and prevents an infinite loop where multiple
            phantoms wait for each other indefinitely without anyone being able to
            finish. Completes its work once all non-phantom handlers have
            finished (ctx.handlers_count == ctx.processed_handlers).
            Examples: SysLogger, StatsCollector.

        Invoker:
            An aggregator of specific actions based on Instruction.types.
            Depends only on external helper objects provided through Configure
            via requirements(). Decrements ctx.handlers_count and marks itself
            done when it determines it cannot handle the current event at all.
            Note: certain Invokers may depend on other handlers — for example
            ResponseCollector or handlers that can inject new InstructionType
            values into Instruction.types at runtime (such as Alerter, which
            notifies the user via a desktop notification and asks what actions
            to take). Invokers that care about such dynamic instruction injection
            must check for those additions themselves via can_handle().
            Examples: BackupInvoker and RestoreInvoker that calls create()/restore()
                      on SnapshotsRegistryStore implementation or,
                      Antimutator that calls acquire() on PathLocker implementation.

        State-dependent:
            Triggers only after a specific action has been publicly signaled by
            another handler. Uses ctx.performed to check whether the required
            action has already been completed before returning True from
            can_handle(). Waits silently across loop iterations until the
            dependency signal appears in ctx.performed. Also like Invokers
            this classification of handler may depend on other handlers that
            can inject new InstructionType values into Instruction.types. This can
            trigger further handlers, including the ones this handler itself depends on.
            Examples: SnapshotsRotator (triggers only after InstructionType.BACKUP
                      appears in ctx.performed, meaning a snapshot was created).

        EndRunner:
            Triggers only after all non-phantom handlers have finished their work
            (ctx.handlers_count == ctx.processed_handlers). Similar to a phantom
            handler but runs at the very end of the processing cycle rather than
            throughout it. Unlike phantoms, decrementing ctx.handlers_count is
            optional — only necessary if the EndRunner wants to be invisible to
            phantom handlers.

    Performed Actions:
        After completing its work a handler may append a flag to ctx.performed
        using an InstructionType value to signal that a specific action was
        completed. Only flags that are meaningful and specific enough for
        State-dependent handlers to act on should be appended. Phantom handlers
        that only log or collect statistics should not pollute the performed
        sequence with irrelevant signals.

        For full details on EventContext, its attributes, and the complete set
        of capabilities it provides to handlers, refer to the EventContext class
        documentation directly.

    Notes:
        - Handlers must not depend on the execution order of other handlers
            directly. Use can_handle() to express dependencies through
            EventContext state instead.
        - Handlers must not raise exceptions. All errors must be caught and
            handled within the implementation itself. The Dispatcher does not
            handle them.
        - Handlers must not treat the Dispatcher loop safety net as their primary
            termination mechanism. The safety net exists as an additional safeguard
            against deadlocked handlers — relying on it as the primary exit strategy
            can cause incorrect behavior in other handlers sharing the same loop.
            Use is_done() to signal completion.
    """

    @abstractmethod
    def can_handle(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler is able to process the given EventContext
        in its current state.

        Called by the Dispatcher on every iteration before invoking handle().
        A handler expresses its dependencies on other handlers implicitly through
        EventContext state: checking ctx.performed for required actions, reading
        from ctx.metadata, or inspecting ctx.handlers_count and processed_handlers.
        Returning False signals the Dispatcher to skip this handler for this iteration.

        Must never raise. Return False on any unrecoverable internal condition.
        """
        ...

    @abstractmethod
    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True if this handler has finished all its work for the given
        EventContext and must not be called again by the Dispatcher.

        Called by the Dispatcher on every iteration alongside can_handle().
        Once True is returned the handler will not be triggered again for this
        event. This is the primary mechanism for signaling completion — do not
        rely on the Dispatcher loop safety net as a substitute.

        Non-phantom handlers must increment ctx.processed_handlers exactly once
        upon completing their work so that the loop termination condition
        (ctx.handlers_count == ctx.processed_handlers) is correctly maintained.

        Must never raise.
        """
        ...

    @abstractmethod
    def handle(self, ctx: EventContext) -> None:
        """
        Processes the given EventContext.

        Called by the Dispatcher only when can_handle() returns True and
        is_done() returns False. Contains the core processing logic of this
        handler. May read from and write to ctx.metadata, append to
        ctx.performed, interact with injected helper objects, and update
        ctx.processed_handlers upon completion.

        Must never raise. All errors must be caught and handled internally.
        """
        ...
