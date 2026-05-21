from __future__ import annotations

from os import environ
from socket import AF_UNIX, SOCK_DGRAM, socket
from threading import Event as ShutdownEvent
from threading import Thread

from ...core import BaseHeartBeat


class SystemdHeartBeat(BaseHeartBeat):
    """
    Linux implementation of BaseHeartBeat using systemd watchdog mechanism.

    Sends WATCHDOG=1 to systemd periodically via a Unix domain socket to
    indicate that the daemon is alive and functioning correctly. If the
    signal is not received within WatchdogSec defined in the service file,
    systemd will restart the daemon automatically.

    Watchdog Interval:
        The signal is sent at half the WatchdogSec interval as recommended
        by systemd documentation. This provides a safety margin so that
        a single delayed signal does not trigger an unintended restart.
        If WATCHDOG_USEC is not set by systemd, a default of 30 seconds
        is used so the heartbeat remains functional outside of systemd.

    Lifecycle Signals:
        READY=1    — sent once when the heartbeat thread starts, notifying
                     systemd that the daemon has finished initializing and
                     is ready to handle requests.
        WATCHDOG=1 — sent every half-interval throughout the daemon lifetime.
        STOPPING=1 — sent once when stop() is called, notifying systemd
                     that the daemon is shutting down gracefully so it does
                     not treat the silence as a crash.

    Shutdown Behaviour:
        Uses shutdown_event.wait(timeout) instead of time.sleep() so the
        heartbeat thread wakes up immediately when shutdown is requested
        rather than waiting until the end of the current interval.

    Unix Socket:
        Each notification opens a fresh SOCK_DGRAM socket, sends the
        message and closes immediately. This avoids holding a persistent
        file descriptor and handles the case where systemd restarts and
        recreates the socket path transparently.
        Silently ignores if NOTIFY_SOCKET is not set so the implementation
        works correctly in development environments without systemd.

    Notes:
        - Requires NOTIFY_SOCKET environment variable to be set by systemd.
        - WATCHDOG_USEC environment variable is set by systemd when
            WatchdogSec is defined in the service file.
        - HeartBeat monitors the entire process, not individual threads.
            If any thread deadlocks or the process stops responding,
            the watchdog signal will not be sent and systemd will act.
    """

    _DEFAULT_INTERVAL: float = 30.0

    def __init__(self, shutdown_event: ShutdownEvent) -> None:
        """
        Initializes the heartbeat and reads watchdog configuration from
        the environment. Interval is set to half of WATCHDOG_USEC if
        provided by systemd, otherwise falls back to _DEFAULT_INTERVAL.
        """
        self._shutdown_event: ShutdownEvent = shutdown_event
        self._socket_path: str = environ.get("NOTIFY_SOCKET", "")

        watchdog_usec = int(environ.get("WATCHDOG_USEC", 0))
        self._interval: float = (
            watchdog_usec / 2_000_000 if watchdog_usec else self._DEFAULT_INTERVAL
        )

        self._thread = Thread(target=self._run, daemon=True, name="HeartBeat")

    def start(self) -> None:
        """
        Starts the HeartBeat thread.
        READY=1 is sent from within the thread on its first iteration
        so it is delivered only after the thread is confirmed running.
        """
        self._thread.start()

    def stop(self) -> None:
        """
        Sends STOPPING=1 to notify systemd of graceful shutdown then
        waits for the HeartBeat thread to finish.
        STOPPING=1 is sent before join() so systemd receives the signal
        while the process is still running and does not mistake the
        upcoming silence for a crash.
        """
        self._notify("STOPPING=1")
        self._thread.join()

    def _run(self) -> None:
        """
        Main loop of the HeartBeat thread.
        Sends READY=1 once on startup then WATCHDOG=1 every half interval.
        Uses shutdown_event.wait() instead of sleep() so the thread
        responds to shutdown immediately without waiting out the interval.
        """
        self._notify("READY=1")

        while not self._shutdown_event.is_set():
            self._notify("WATCHDOG=1")
            self._shutdown_event.wait(timeout=self._interval)

    def _notify(self, message: str) -> None:
        """
        Sends a notification message to systemd via Unix domain socket.
        Opens a fresh socket per call so stale file descriptors never
        accumulate and socket recreation by systemd is handled transparently.
        Silently ignores if NOTIFY_SOCKET is not set.
        """
        if not self._socket_path:
            return

        with socket(AF_UNIX, SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), self._socket_path)
