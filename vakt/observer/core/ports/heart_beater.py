from __future__ import annotations

from abc import ABC, abstractmethod


class BaseHeartBeater(ABC):
    """
    Abstract base class for heart-beat mechanism.

    HeartBeater is responsible for periodically sending a liveness signal
    to an external process supervisor to indicate that the daemon is alive
    and functioning correctly.

    If the signal is not sent within the expected interval, the supervisor
    assumes the daemon is dead or frozen and may restart the process.

    This is a critical component for daemons that must run 24/7 without
    human supervision. It acts as an insurance policy for the entire process.

    Implementations Example:
        - SystemdHeartBeater: Linux, uses sd_notify to send WATCHDOG=1 to systemd.

    Notes:
        - HeartBeater runs in its own thread (HeartBeater Thread).
        - It must respect shutdown_event to stop gracefully.
        - Interval between signals must be provided via __init__
            of implementation.
        - HeartBeater monitors the entire process, not individual threads.
            If any thread causes a deadlock or the process stops responding,
            the heartbeat signal will not be sent and the supervisor will act.
    """

    @abstractmethod
    def start(self) -> None:
        """Starts the HeartBeater thread."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stops the HeartBeater thread gracefully.
        Should be called after shutdown_event is set.
        """
        ...
