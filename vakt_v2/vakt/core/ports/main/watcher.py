from __future__ import annotations

from abc import abstractmethod

from ..protocols import AssemblyProtocol


class BaseWatcher(AssemblyProtocol):
    """
    Abstract base class for all file-system watcher implementations.

    Watcher is responsible for monitoring file-system changes and producing
    domain Event objects. It does not know what happens to an event after
    placing it into the buffer — that is the Dispatcher's concern. The Watcher
    acts as the Producer in a Producer-Consumer pattern: the Dispatcher is the
    Consumer, and the shared thread-safe buffer is the conveyor between them.

    The Watcher runs in its own dedicated thread (Watcher Thread) and
    continuously monitors all subscribed paths. When a change is detected,
    it constructs a domain Event and places it into the shared buffer.

    Common protocol between Assembler and implementations:
        Every BaseWatcher implementation must declare the following in
        internal_reqs through its requirements() -> Configure object:

            - shutdown_event: the shared threading.Event that signals graceful
                shutdown. The Watcher Thread must check it periodically and
                exit cleanly when it is set.

            - thread_safe_buffer: the shared queue between the Watcher and
                Dispatcher threads. The Watcher places Events here; the
                Dispatcher reads and processes them.

        Declaring both is mandatory for all implementations without exception.
        Violating this breaks the Observer environment.

        Implementations that cannot identify which process initiated a
        file-system event from kernel metadata — surface-level Watchers —
        must also declare:

            - occupied_paths: the shared reference-counting mapping maintained
                by server components that generate file-system events as a
                side effect of their own operations. Without this mapping,
                a surface-level Watcher has no way to distinguish events the
                server itself caused from events caused by external actors.
                Before enqueuing any event, such implementations must run
                the three-step check documented in the Occupied Paths Protocol
                section below.

        Implementations that receive kernel-level event metadata — including
        which process initiated the event — do not declare occupied_paths.
        They identify self-generated events directly from that metadata.

    Occupied Paths Protocol:
        The Watcher is the only place where occupied_paths filtering occurs.
        Filtering at this stage prevents self-generated events from ever
        entering the buffer, keeping it clean and sparing the Dispatcher
        from discarding events it never needed to process.

        Surface-level implementations must run the following three-step check
        before enqueuing each event. Steps execute in strict order — if any
        step returns True, the event is self-generated and must be dropped
        silently, never enqueued:

            Step 1 — exact match:
                occupied_paths.get(event_path, 0) > 0

            Step 2 — recursive match:
                any(
                    event_path.startswith(p + "/") and count > 0
                    for p, count in occupied_paths.get("recursive", {}).items()
                )

            Step 3 — vakt suffix strip, then repeat steps 1 and 2:
                idx = event_path.rfind(".vakt.")
                if idx != -1:
                    clean = event_path[:idx]
                    repeat step 1 on clean
                    repeat step 2 on clean

        Deep-integration implementations must check whether the initiating
        process matches the server's own process and drop the event if it
        does. occupied_paths filtering is not required for such implementations.

        The Watcher must never modify occupied_paths — only read it.
        For the full reference-counting and claim registration protocol
        see Configure documentation.

    Path Syntax Protocol:
        All implementations that receive a path from the client must adhere
        to the following protocol to avoid confusing the client:
            /some/path/**             → recursive: watches path and all its sub-paths.
            /some/path/*              → non-recursive: watches only the immediate content.
            /some/path or /some/path/ → must be silently normalized to /some/path/*
                                        by the implementation for non-recursive watching.

    Why events() is separated from start():
        start() is responsible for preparing all resources before launch —
        opening file descriptors, subscribing to paths, validating sources —
        and then spawning the Watcher Thread in which events() runs.
        events() contains the actual observation loop: detecting changes and
        placing Event objects into the buffer. The separation keeps resource
        setup and event monitoring distinct, making both easier to reason about.

    Graceful Shutdown Protocol:
        All implementations must respect shutdown_event and periodically check
        whether it is set. When it is, the implementation must exit events()
        cleanly without crashing or leaving resources open.

    Implementation examples:
        - InotifyWatcher:  Linux, inotify kernel subsystem. Surface-level.
        - FanotifyWatcher: Linux, fanotify kernel subsystem. Deep-integration.
        - WindowsWatcher:  Windows, ReadDirectoryChangesW. Surface-level.
        - PollingWatcher:  Cross-platform, os.stat() polling. Surface-level.

    Notes:
        - Watcher runs in its own dedicated thread (Watcher Thread).
        - Must respect shutdown_event — never block indefinitely without checking it.
        - Must never modify occupied_paths — only read it.
        - Surface-level implementations must declare occupied_paths in
            internal_reqs and apply the three-step Occupied Paths Protocol
            before every enqueue.
        - Deep-integration implementations do not declare occupied_paths —
            they identify and drop self-generated events from kernel metadata.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Prepares all necessary resources for watching and starts the Watcher Thread.

        Performs all initialization — opening file descriptors, subscribing to
        paths, validating sources — before spawning the thread in which events()
        runs. Called once by the Observer before observation begins. Calling
        start() again without a prior stop() is not permitted.
        Contains no observation logic itself — purely setup and thread launch.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Waits for the Watcher Thread to exit, then releases all resources.

        Unsubscribes from paths, closes file descriptors and handles, releases
        the kernel watcher, and frees any remaining allocated memory. Called
        by the Observer during graceful shutdown. Once this method returns,
        no dangling subscriptions or unreleased resources remain.
        """
        ...

    @abstractmethod
    def events(self) -> None:
        """
        Core observation loop. Continuously reads file-system changes from
        the subscribed source, transforms them into domain Event objects,
        and enqueues them into the shared thread-safe buffer.

        Must filter self-generated events before enqueuing — surface-level
        implementations apply the three-step Occupied Paths Protocol;
        deep-integration implementations check whether the initiating process
        matches the server's own process. Either way, self-generated events
        must never reach the buffer.

        Runs inside the Watcher Thread. Executes until shutdown_event is set,
        after which it exits cleanly. System-level resources opened in start()
        are not released here — that is stop()'s responsibility.
        """
        ...
