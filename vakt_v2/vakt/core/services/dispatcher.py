from __future__ import annotations

from queue import Empty, Queue
from threading import Event as ShutdownEvent
from threading import Thread

from ..domain import Event, EventContext
from ..ports import BaseHandler, BaseInstructionRegistry


class Dispatcher:
    """
    A fixed processing-layer service responsible for reading incoming Events
    from the shared buffer and orchestrating all registered handlers.

    Why Dispatcher is not a port:
        A port exists because an implementation needs to be replaceable — different
        platforms, different strategies, different storage backends. Dispatcher
        requires none of this. Its logic — read from the buffer, retrieve the
        matching Instruction, create an EventContext, and drive it through the
        handlers loop — is identical everywhere and always, regardless of platform
        specifics. Platform-specific concerns are already hidden behind ports:
        Watcher, Handler, InstructionRegistry, and helpers. Dispatcher simply
        orchestrates them. Nothing to replace — no port needed.

    Dispatcher Thread:
        Dispatcher runs on its own dedicated thread (Dispatcher Thread) and
        continuously reads and processes incoming Events from the thread-safe buffer.
        For each event it creates an ephemeral EventContext paired with the most
        appropriate Instruction retrieved from InstructionRegistry — describing what
        happened and what actions should follow. It then drives the EventContext
        through the handlers loop until no active handler can make further progress
        on that event.

        Dispatcher has no knowledge of handler implementations. It communicates with
        handlers exclusively through their public interface: can_handle(), is_done(),
        and handle().

    Main Handlers Loop Mechanism:
        For each Event, the Dispatcher iterates over all registered handlers in a
        loop. On every iteration it asks each handler can_handle() and is_done().
        If both conditions are satisfied the handler is given the EventContext to
        process. The loop continues as long as at least one handler can still make
        progress on the current event. If a full iteration passes without any handler
        processing the event, the Dispatcher treats this as a signal that all active
        work is complete and breaks the loop. This gives handlers the ability to
        depend on the results of other handlers without any explicit coupling between
        them — all coordination happens through the shared ephemeral EventContext.

    Graceful Shutdown:
        Dispatcher continues reading and processing events until shutdown_event is
        set and the buffer has been fully drained. This guarantees that no in-flight
        events are lost during server shutdown — all events already in the buffer at
        the moment of shutdown are processed to completion before the Dispatcher
        Thread exits.

    Notes:
        - Dispatcher implements no business logic itself. All logic is contained in
            handlers and Instructions. Dispatcher is solely responsible for correctly
            orchestrating them.
        - Dispatcher is responsible for graceful shutdown of the processing loop —
            on shutdown it must ensure all remaining events in the buffer are fully
            processed before the Dispatcher Thread exits.
        - The handlers loop safety net (break on zero progress in a full iteration)
            is a spare cushion mechanism against infinite cycles. Each handler must
            implement can_handle() and is_done() correctly and must not rely on the
            safety net as its primary termination mechanism.
    """

    def __init__(
        self,
        shutdown_event: ShutdownEvent,
        instruction_registry: BaseInstructionRegistry,
        handlers: list[BaseHandler],
        buffer: Queue[Event],
    ) -> None:
        """
        Initializes all internal state of the Dispatcher.

        No resources are acquired and no threads are started here.
        The Dispatcher Thread is created but remains idle until start() is called.
        All dependencies are injected by the Observer at construction time.
        """
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._instruction_registry: BaseInstructionRegistry = instruction_registry
        self._handlers: list[BaseHandler] = handlers
        self._buffer: Queue[Event] = buffer
        self._thread: Thread = Thread(target=self._run, daemon=True, name="Dispatcher")

    def start(self) -> None:
        """
        Starts the Dispatcher Thread and begins processing incoming Events.

        Called once by the Observer after all components are initialized and
        the Watcher has started. After this call, _run() begins continuously
        reading from the buffer and dispatching events to handlers.
        """
        self._thread.start()

    def stop(self) -> None:
        """
        Waits for the Dispatcher Thread to finish and exit cleanly.

        The thread exits on its own once shutdown_event is set and the buffer
        is fully drained. This method blocks until that condition is met,
        guaranteeing that all in-flight events are processed before returning.
        Called by the Observer during graceful shutdown, after shutdown_event
        has been set.
        """
        self._thread.join()

    def _run(self) -> None:
        """
        Core loop of the Dispatcher Thread.

        Runs continuously while shutdown_event is not set or the buffer still
        contains unprocessed events — ensuring the buffer is always fully drained
        before the thread exits, even during shutdown.

        On each iteration, attempts to retrieve an Event from the buffer with a
        one-second timeout. If the buffer is empty (Empty exception), the loop
        continues and re-evaluates the shutdown condition — this keeps shutdown
        responsive without busy-waiting. For each retrieved event, the matching
        Instruction is fetched from InstructionRegistry, an ephemeral EventContext
        is created, and the event is dispatched to _process(). task_done() is called
        after processing to signal queue completion to any waiting join() calls.
        """
        while not self._shutdown_event.is_set() or not self._buffer.empty():
            try:
                event = self._buffer.get(timeout=1)
            except Empty:
                continue
            instruction = self._instruction_registry.get(event)
            ctx = EventContext(
                event=event,
                instruction=instruction,
                handlers_count=len(self._handlers),
            )
            self._process(ctx)
            self._buffer.task_done()

    def _process(self, ctx: EventContext) -> None:
        """
        Drives the given EventContext through the handlers loop until no handler
        can make further progress.

        On each iteration, every handler is asked can_handle() and is_done().
        If both conditions are satisfied the handler is invoked with the context.
        A progress flag tracks whether any handler acted during the current
        iteration. If a full iteration completes with no handler having acted,
        the loop breaks — this is the safety cushion against infinite cycles
        caused by handlers that fail to correctly signal completion via is_done().
        """
        while True:
            progress = False
            for handler in self._handlers:
                if handler.can_handle(ctx) and not handler.is_done(ctx):
                    handler.handle(ctx)
                    progress = True
            if not progress:
                break
