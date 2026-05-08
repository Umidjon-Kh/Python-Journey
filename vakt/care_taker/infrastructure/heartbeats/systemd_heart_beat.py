from __future__ import annotations

from os import environ
from socket import AF_UNIX, SOCK_DGRAM, socket
from threading import Event as ShutdownEvent
from threading import Thread
from time import sleep

from ...core import BaseHeartBeat


class SystemdHeartBeat(BaseHeartBeat):
    """
    Linux implementation of BaseHeartBeat using systemd watchdog mechanism.

    sends WATCHDOG=1 signal to systemd periodically via Unix socket
    to indicate that the daemon is alive and functioning correctly.

    If the signal is not sent within WatchdogSec interval defined
    in the service file, systemd will restart the daemon automatically.

    Notes:
        - if WATCHDOG_USEC is not set, default interval of 30 seconds is used.
        - Signal is sent at half the watchdog interval for safety margin.
        - Requires NOTIFY_SOCKET to be set by systemd.
        - READY=1 is sent once on start to notify systemd daemon is ready.
        - STOPPING=1 is sent once on stop to notify systemd graceful shutdown.
    """

    def __init__(self, shutdown_event: ShutdownEvent) -> None:
        """Initializes all instance attributes by injecting shutdown_event."""
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._socket_path: str = environ.get("NOTIFY_SOCKET", "")

        watchdog_usec = int(environ.get("WATCHDOG_USEC", 0))
        self._interval: float = watchdog_usec / 2_000_000 if watchdog_usec else 30

        self._thread = Thread(target=self._run, daemon=True, name="heartbeat")

    def start(self) -> None:
        """
        Starts the HeartBeat thread and notifies systemd that daemon is ready to work.
        """
        self._thread.start()

    def stop(self) -> None:
        """
        Waits for HeartBeat thread to finish after shutdown_event is set.
        Sends STOPPING=1 to systemd to indicate graceful shutdown.
        """
        self._thread.join()
        self._notify("STOPPING=1")

    def _run(self) -> None:
        """
        Main loop of the HeartBeat thread.
        Sends READY=1 once on a start then WATCHDOG=1 every half watchdog interval.
        """
        self._notify("READY=1")

        while not self._shutdown_event.is_set():
            self._notify("WATCHDOG=1")
            sleep(self._interval)

    def _notify(self, message: str) -> None:
        """
        sends a message to systemd via Unix socket.
        AF_UNIX - local communication through file, not network.
        SOCK_DGRAM - sends packet without establishing connection.
        Silently ignores if socket path is not set.
        """
        if not self._socket_path:
            return

        with socket(AF_UNIX, SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), self._socket_path)
