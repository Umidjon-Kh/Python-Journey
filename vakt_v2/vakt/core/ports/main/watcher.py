from __future__ import annotations

from abc import abstractmethod

from .port_protocol import PortProtocol


class BaseWatcher(PortProtocol):
    """
    Abstract base class for all file-system watchers.

    The Watcher is responsible for monitoring file-system changes and producing
    domain Event objects. It does not know what happens to the event after it
    places them into the buffer - that is the responsibility of the Dispatcher
    layer. Thus, the Watcher acts as the Producer in a Producer-Consumer pattern,
    while the Dispatcher is the Consumer, and the shared thread-safe buffer serves
    as the conveyor.

    The Watcher runs in its own thread (Watcher Thread)  and continuously watches
    all subscribed paths for changes. When a change is detected, it creates a domain
    event object and puts it into a thread-safe buffer that is shared across the main
    pipeline objects - more precisely, it is a common buffer for the Watcher and
    Dispatcher threads.

    Common protocol between Assembler and implementations:
        Each implementation of BaseWatcher, through its requirements() -> Configure
        object, must explicitly declare two key requirements in internal_reqs for
        the correct and coordinated operation:
            - shutdown_event: responsible for graceful shutdown, managed by the common
                ancestor, the upper-layer Observer object, which controls starting/stopping
                and the entire Observer environment (Watcher and Dispatcher).
            - thread-safe-buffer: a shared buffer accessible to both the Watcher and the
                Dispatcher, acting as a pipeline between the threads, The Watcher places
                events there, and they are later processed in the Dispatcher thread.
        This protocol must never be violated, as it directly affects the operation of
        the Observer daemon.

    Path Syntax Protocol:
        All implementations that receive a path from the client must adhere to the
        following protocol to avoid confusing the client:
            /some/path/**             -> recursive: watches path and all its sub-paths.
            /some/path/*              -> non-recursive: watches only the immediate content of the path.
            /some/path or /some/path/ -> without an explicit suffix: must be silently normalized
                                            to /some/path/* by the implementation for non-recursive
                                            watching.

    Why events() is separated from start():
        This is intentional, so that anyone reading and writing the code is not confused
        by unnecessry syntactic nosie. start() is responsible for preparing all resources
        before launch - although it does start the thread that wraps events(), its sole
        purpose is to prepare resources (e.g., subscribing to paths). events() then handles
        the actual monitoring and placement of Event objects into the thread-safe buffer.
        This clearly separates responsibilities without mixing them.

    Graceful Shutdown Protocol:
        All implementations of BaseWatcher must respect the shutdown_event flag and
        periodically check wether it is set (shutdown_event is set?), so that when asked
        to stop from above, they can correctly end their session inside events() without
        crashing.

    Implementation examples:
        - InotifyWatcher: Linux, uses the inotify kernel subsystem.
        - FanotifyWatcher: Linux, uses the fanotify kernel subsystem.
        - WindowsWatcher: Windows, uses ReadDirectoryChangesW.
        - PollingWatcher: Cross-platform, uses os.stat() polling.

    Notes:
        - Watcher runs in its own thread (Watcher Thread).
        - It must respect shutdown_event to stop gracefully.
        - It must never block indefinitely without checking shutdown_event.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Prepares all necessary resources for watching and start the main
        event-loop thread.

        This method performs initialization (path subscriptions, opening file
        descriptors/handles, source validation) before spawning the Watcher Thread.
        Immediately after succesfull setup, it launches the thread in which events()
        runs - the core loop responsible for detecting changes and enqueuing events
        into the thread-safe buffer.

        Called only when observation is about to begin, once the Observer has
        decided to start processing filesystem changes. Calling start() again
        without a prior stop() is not allowed.
        Contains no observation logic itself - purely setup and thread launch.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Waits for the Watcher Thread to exit after the shutdown_event has
        been set, then removes or clears all previously prepared
        resources: unsubscribing from paths, closes file descriptors/handles,
        releases kernel watcher, freeing memory and preventing resource leaks.

        Called only when the Observer decides to stop monitoring
        and shut down. Once this method returns, no dangling subscriptions
        or unreleased resources remain guaranteed.
        """
        ...

    @abstractmethod
    def events(self) -> None:
        """
        Core observation loop. Continuously reads file-system changes from
        subscribed sources (inotify, fanotify, ReadDirectoryChangesW, or
        polling results), transforms them into domain Event objects, and
        enqueues them into the shared thread-safe buffer.

        Runs inside the Watcher Thread as its main event loop body.
        Executes until shutdown_event is set, after which it exits cleanly
        releasing any ephemeral session resources (system-level subscriptions
        or other resources are not removed here - that is handled by stop()).
        """
        ...
