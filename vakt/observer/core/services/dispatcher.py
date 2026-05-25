from __future__ import annotations

from collections.abc import Sequence
from queue import Empty, Queue
from threading import Event as ShutdownEvent
from threading import Thread

from ..domain import Event, EventContext
from ..ports import BaseHandler, BaseInstructionRegistry


class Dispatcher:
    """
    Dispatcher is a processing-layer service that responsible for processing
    incoming Events from the buffer and orchestrating all registered handlers.

    Dispatcher runs in its won thread (Dispatcher Thread) and automatically
    reads Events from thread-safe buffer produced by the Watcher Thread that puts
    Events to that buffer. For each Event it creates an EventContext ephemeral object
    that serves to describe handlers what is done and what don't happened yet with
    current event. Retrieves appropriate Instruction from InstructionRegistry and
    dives all handlers through a progress loop until no handlers
    can make further progress.

    Handlers Loop:
        Dispatcher iterates over all handlers in a loop on every Event.
        On each iteration it checks can_handle() and is_done() for each handler.
        The loop continues as long as at least one handler makes progress.
        This enables handler to depend on results of other performed handlers
        without explicit coupling between them. All handlers use EventContext.performed
        sequence to check out current performed actions flags.

    Ignoring Mechanism:
        The Dispatcher maintains a shared dictionary, ignoring_paths (dict[str, int]),
        which is injected into handlers as an attribute of the ToolKit object during
        assembly phase (on boostrap during handlers initialization).

        Each dictionary key represents the full path to a file system object whose
        events should be suppressed N times, where N is the number
        stored in thhe path: count value.

        This allows handlers to precisely register how many self-generated events should
        be suppressedd for given path. Furthermore, this mechanism allows top-level
        objects (clients or users) to permenantly mark paths they wish to ignore by setting
        the count value to an infinite number (e.g., inf or a very large value or -1).

        The ignoring_paths dictionary is not owned by the Dispatcher, although management
        of this dictionary is explicitly delegated to the Dispatcher.

        Each time an event is detected in ignoring_paths, the Dispatcher decrements
        the counter by 1. If the counter for given path decrements to zero, the entry
        is removed from the dictionary. This prevents the dictionary from expanding
        infinitely (like a bubble) and taking up unnecessary RAM.

    Why dict[str, int] and not a set or list for ignoring_paths:
        A list collapses duplicate paths into a single ignore, causing Dispatcher
        to under-ignore when multiple handlers modify the same path independently.
        A set introduces the same correctness issue - duplicate paths are collapsed
        due to uniqueness constraint, so Dispatcher effectively ignores the event
        only once even though multiple handlers depend on it. This may cause
        inconsistent state or even corruption of the object.
        A counter-based dict tracks exactly how many events to suppress per path,
        preserving correctness when several handlers operate on the same object.

    Notes:
        - Dispatcher does not implement any business logic itself,
            All logic is contained in handlers and instructions.
            Dispatcher only responsible for properly orchestrating them.
        - Dispatcher is also responsible for graceful shutdown as a Watcher that
            receives Event to a buffer, It checks shutdown_event on every iteration and stops
            after processing all Events that were placed in to the buffer by the
            Watcher before it was terminated.
        - Dispatcher is the only component responsible for managing ignoring_paths lifecycle.
        - Handlers loop is only a spare (cushion) mechanism for avoiding an infinite cycle,
            and each handler must implement their own can_handle() and is_done() methods correctly.
    """

    def __init__(
        self,
        buffer: Queue[Event],
        instruction_registry: BaseInstructionRegistry,
        handlers: Sequence[BaseHandler],
        ignoring_paths: dict[str, int],
        shutdown_event: ShutdownEvent,
    ) -> None:
        """
        Initializes all attributes of instance of Dispatcher.

        Args:
            buffer: Thread-safe buffer.
            instruction_registry: An implementation of BaseInstructionRegistry.
            handlers: Sequence of BaseHandler implementations.
            ignoring_paths: Dictionary of aboslute paths to ignore N times.
            shutdown_event: Tumbler that needs to shutdown gracefully.
        """
        self._buffer: Queue[Event] = buffer
        self._instruction_registry: BaseInstructionRegistry = instruction_registry
        self._handlers: Sequence[BaseHandler] = handlers
        self._ignoring_paths: dict[str, int] = ignoring_paths
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._thread: Thread = Thread(target=self._run, daemon=True, name="dispatcher")

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
        while not self._shutdown_event.is_set() or not self._buffer.empty():
            try:
                event = self._buffer.get(timeout=1)
            except Empty:
                continue

            if event.path in self._ignoring_paths:
                if self._ignoring_paths[event.path] == -1:
                    pass
                elif self._ignoring_paths[event.path] <= 1:
                    del self._ignoring_paths[event.path]
                else:
                    self._ignoring_paths[event.path] -= 1

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
