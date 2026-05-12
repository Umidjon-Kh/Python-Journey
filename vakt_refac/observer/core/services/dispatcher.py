from __future__ import annotations

from collections.abc import Sequence
from queue import Empty, Queue
from threading import Event as ShutdownEvent
from threading import Thread

from ..domain import Event, EventContext
from ..ports import BaseHandler, BaseInstructionRegistry


class Dispatcher:
    """
    Dispatcher-layer service responsible fro processing incoming Events
    from the buffer and orchestrating all registered handlers.

    Dispatcher runs in its own thread (Dispatcher Thread) and continuously
    reads Events from thread-safe buffer produced by the Watcher Thread that puts
    Events to that buffer. For each Event it creates an EventContext ephemeral object
    that serves to describe handlers what is done and what don't happened yet with
    current event. Retrieves appropriate Instruction from InstructionRegistry and
    drives all handlers through a progress loop until
    no handlers can make further progress.

    Ignoring Mechanism:
        Dispatcher maintains a shared ignoring_paths sequence that is injected
        into all handlers that opt into the mechanism by setting their ignoring_paths
        attribute to an empty sequence instead of None. When handlers adds a path to
        ignoring_paths, Dispatcher will skip and discard any incoming Event with that path
        from the buffer that enables to ignore changes that processed with handlers via
        giving knowledge to Dispatcher and any type of handlers by shared sequence.

    Handlers Loop:
        Dispatcher iterates over all handlers in a loop on every Event.
        On each iteration it checks can_handle() and is_done() fro each handler.
        The loop continues as long as at least one handler makes progress.
        This enables handler to depend on results of other performed handlers
        without explicit coupling between them. All handlers use EventContext.performed
        sequence check out current performed actions flags.

    Notes:
        - Dispatcher does not implement any business logic itself,
            All logic is contained in handlers and instructions.
            Dispatcher only responsible for properly orchestrating them.
        - Dispatcher is also responsible for graceful shutdown as a Watcher that
            receives Event to a buffer, It checks shutdown_event on every iteration and stops
            after processing all Events that were placed in to the buffer by the
            Watcher before it was terminated.
        - Dispatcher is the only component responsible for managing ignoring_paths lifecycle.
        - Why can't we use a sequence that enforces uniqueness like a set for ignoring_paths:
            Cause using a set-like structure introduces a correctness issue.
            If multiple handlers modify on the same object in the file system,
            them may attempt to register that object independently. Due to the
            uniqueness constraint of a set-like structures, duplicate paths are collapsed.
            A a result, the dispatcher effectively ignores for the event only once,
            inconsistent state or even corruption of the object.
        - Ensure that the implementation of BaseHandler must use ignoring_paths in a lock,
            if handlers work on its own thread to avoid race conditions or other exceptions.
    """

    def __init__(
        self,
        buffer: Queue[Event],
        instruction_registry: BaseInstructionRegistry,
        handlers: Sequence[BaseHandler],
        shutdown_event: ShutdownEvent,
    ) -> None:
        """
        Initializes all attributes and injects shared ignoring_paths into handlers
        only if they need it, to work properly.
        """
        self._buffer: Queue[Event] = buffer
        self._instruction_registry: BaseInstructionRegistry = instruction_registry
        self._handlers: Sequence[BaseHandler] = handlers
        self._ignoring_paths: list[str] = []
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._thread: Thread = Thread(target=self._run, daemon=True, name="dispatcher")

        for handler in self._handlers:
            if handler.ignoring_paths is not None:
                handler.ignoring_paths = self._ignoring_paths

    def start(self) -> None:
        """Starts the Dispatcher Thread."""
        self._thread.start()

    def stop(self) -> None:
        """
        Stops the Dispatcher Thread by waiting for it to finish processing
        remaining Events in the buffer. Should be called after shutdown_event is
        set by the upper layer.
        """
        self._thread.join()

    def _run(self) -> None:
        """
        Main loop of the Dispatcher Thread that processes
        all events getting them from the buffer.
        """
        while not self._shutdown_event.is_set() and not self._buffer.empty():
            try:
                event = self._buffer.get(timeout=1)
            except Empty:
                continue

            if event.path in self._ignoring_paths:
                self._ignoring_paths.remove(event.path)
                self._buffer.task_done()
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
        Drives all handlers through the progress loop for the
        given EventContext while at least one handler makes progress.
        """
        while True:
            progress = False

            for handler in self._handlers:
                if handler.can_handle(ctx) and not handler.is_done(ctx):
                    handler.handle(ctx)
                    progress = True

            if not progress:
                break
