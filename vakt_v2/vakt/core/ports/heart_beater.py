from __future__ import annotations

from abc import ABC, abstractmethod


class BaseHeartBeater(ABC):
    """
    Abstract base class for all server heartbeat mechanism implementations.

    HeartBeater is responsible for reporting the server's status to an external
    supervisor process. It acts as a safety guard against server failures.
    This is a critically important component — the Vakt server is designed to run
    continuously 24/7 without user intervention or active monitoring. Without
    HeartBeater, the OS has no visibility into the server's current state and
    cannot take any corrective action on its behalf.

    Status Notifying Protocol:
        All implementations must periodically notify the supervisor that the server
        is alive and operating correctly. If the signal stops arriving, the supervisor
        will assume the server has died and will attempt to restart it. Beyond the
        periodic liveness signal, implementations must also send specific status
        messages — such as server started, stopped, or crashed — according to the
        conventions of the target platform. This is critical: the supervisor's
        ability to manage the server lifecycle depends entirely on these signals.
        HeartBeater is the server's insurance policy against silent failure.

        All implementations must notify the supervisor at an interval of at most
        half the configured watchdog timeout (interval / 2) as a safety margin to
        guarantee the signal always arrives before the supervisor considers the
        server dead.

    Why HeartBeater does not inherit from AssemblyProtocol:
        Unlike other ports, HeartBeater is not part of the Observer environment —
        it belongs to the Server itself and serves the Overseer directly. The client
        never decides which implementation to use or with what configuration.
        Instead, the Assembler automatically selects the most appropriate
        implementation for the current platform at server startup.

    Why the abstract base class does not declare __init__:
        Unlike other ports that may have a large number of implementations,
        HeartBeater implementations are few and the Assembler knows each of them
        directly — the assembly logic for every specific implementation is hardcoded
        into the Assembler by the author (me) and contributors. Declaring __init__ in
        the abstract class would impose an unnecessary constraint on that small set.
        However, all implementations without exception must accept terminate_event
        in their own __init__ to ensure graceful shutdown without errors.

    Example implementations:
        - SystemdHeartBeater:        Linux — uses sd_notify to report status to
                                      the systemd WATCHDOG mechanism.
        - WindowsServiceHeartBeater: Windows — uses the Windows Service Control
                                      Manager (SCM) via win32api to report service
                                      status and handle SCM control events.
        - LaunchdHeartBeater:        macOS — integrates with launchd via keepalive
                                      and CheckPort mechanisms to signal process
                                      health to the launchd supervisor.

    Notes:
        - HeartBeater runs on its own dedicated thread (HeartBeater Thread),
            started via start().
        - All implementations must respect terminate_event to shut down gracefully.
        - All implementations must notify at interval / 2 of the configured watchdog
            timeout as a safety margin.
        - HeartBeater monitors the entire server, not just the Observer. If the
            server hangs or crashes the supervisor will know immediately and restart
            it — implementations must therefore be unconditionally reliable. HeartBeater
            must never crash or raise during operation. It must be as dependable
            as a Rolex.
        - Must never propagate exceptions to the caller. All errors must be caught
            and handled internally.
    """

    @abstractmethod
    def start(self) -> None:
        """
        Starts the HeartBeater Thread and begins sending periodic status signals
        to the supervisor.

        Called once by the Overseer at server startup after initialization is
        complete. Sends the initial startup notification to the supervisor before
        entering the periodic notification loop. Must never propagate exceptions.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stops the HeartBeater Thread and sends a final shutdown notification
        to the supervisor.

        Called once by the Overseer during graceful shutdown. Waits for the
        HeartBeater Thread to finish its current iteration before stopping.
        Must never propagate exceptions.
        """
        ...
