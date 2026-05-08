from __future__ import annotations

from abc import ABC, abstractmethod


class BaseHeartBeat(ABC):
    """
    Abstract base class for heart-beat mechanism.

    HeartBeat is responsible for periodiclaly sending a liveness signal
    to an external process supervisor to indicate that the daemon is alive
    and functioning correct.

    If the signal is not sent withint the expected interval, the supervisor
    assums the daemon is dead or frozen and may restart the process.

    This is a critical component for daemons that must run 24/7 without
    human supervision. It acts as an insurance policy for the entire process.

    Implementations Example:
        - LinuxHeartBeat: Linux, uses sd_notify to send WATCHDOG=1 to systemd.

    Notes:
        - HeartBeat runs in its own thread (HeartBeat Thread).
        = It must respect shutdown_event to stop gracefully.
        - Interval between must be provided via __init__
            of implementation.
        - HeartBeat monitor the entire process, not individual threads.
            If any thread causes a deadlock or the process stops responding,
            the heartbeat signal will not be sent and the supervisor will act.
    """

    @abstractmethod
    def start(self) -> None:
        """Starts the HeartBeat thread."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Stops the HeartBeat thread gracefully.
        Should ba called after shutdown_event is set.
        """
        ...
