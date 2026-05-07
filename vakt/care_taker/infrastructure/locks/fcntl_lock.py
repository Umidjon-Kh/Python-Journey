from __future__ import annotations

from fcntl import LOCK_EX, LOCK_SH, LOCK_UN, flock
from typing import IO

from ...core import BasePathLock


class FcntlPathLock(BasePathLock):
    """
    Linux/macOS implementation of BasePathLock using fcntl.flock()
    system call.

    Provides exclusive and shared locking for file system objects
    at the OS level, preventing external processes from modifying
    a locked object while a handler is processing it.

    Notes:
        - fcntl.flock() is advisory — it only blocks other processes
            that also use flock(). Programs that do not check locks
            (like cp or mv) will ignore it.
        - Lock is attached to the file descriptor, not the file itself.
            If the file descriptor is closed, the lock is released automatically.
        - FcntlPathLock stores open file descriptors internally while
            a path is locked. They are closed on release().
        - acquire() uses LOCK_EX by default — exclusive lock.
            Use acquire_shared() for read-only access like Backuper.
    """

    def __init__(self) -> None:
        self._fds: dict[str, IO] = {}

    def acquire(self, path: str) -> None:
        """
        Acquires an exclusive lock on the object at the given path.
        Blocks access from other processes that respect flock().
        Uses LOCK_EX — no other process can read or write.
        """
        fd = open(path, "r+")
        flock(fd, LOCK_EX)
        self._fds[path] = fd

    def acquire_shared(self, path: str) -> None:
        """
        Acquires a shared lock on the object at the given path.
        Other processes can read but not write.
        Intended for Backuper which only reads the file.
        Uses LOCK_SH.
        """
        fd = open(path, "r")
        flock(fd, LOCK_SH)
        self._fds[path] = fd

    def release(self, path: str) -> None:
        """
        Releases the lock on the object at the given path.
        Closes the file descriptor which automatically releases the lock.
        Silently ignores if path is not locked.
        """
        fd = self._fds.pop(path, None)
        if fd is None:
            return
        flock(fd, LOCK_UN)
        fd.close()
