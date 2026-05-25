from __future__ import annotations

from abc import ABC, abstractmethod


class BasePathLocker(ABC):
    """
    Abstract base class for file system level locking.

    A PathLocker is responsible for acquiring and releasing
    exclusive access to a file system object at the OS level.
    This prevents external processes from modifying a file
    while RollBacker is restoring it or any other components
    that require safe-modifying is processing with it.

    PathLocker is a helper infrastructure component designed to assist
    handlers and developers that require safe interaction with file system
    objects during critical operations. It is not a core pipeline element
    and does not participate in event processing directly.

    Implementations Example:
        - FcntlPathLocker: Linux/macOS, uses fcntl.flock().
        - WindowsPathLocker: Windows, uses msvcrt.locking().
        - ChmodPathLocker: Linux, uses chmod to restrict permissions.

    Why acquire() returns str and not None:
        This is a pragmatic architectural compromise. Different implementations
        may operate on the object at a different path than the one provided.
        For example, ChmodPathLocker renames the object to a .vakt.lock path
        before locking it, so the caller must know where the object now lives
        to interact with it safely. Returning the actual path from acquire()
        makes this contract explicit without coupling callers to specific
        implementation details. Implementations that do not move the object
        simply return the original path unchanged.

    Notes:
        - PathLocker operates at the OS level, not the thread level.
            It blocks access from external processes, not just threads
            within the same process.
        - Not all implementations can operate with full OS-level blocking.
            Implementations running without root privileges may only be
            able to restrict permissions rather than fully block access.
            Callers must not assume that acquire() provides a hard kernel lock.
        - Implementations must ensure that release() is always called
            after acquire(), even if an error occurs. Use try/finally
            or implement __enter__/__exit__ properly.
        - In base abstract cls not strictly requires __enter__/__exit__ methods
            implementations to work with context manager it only depends of realization.
        - Method release requires path to cause it enables to create an implementations
            that lock not one object at one time. But ensure this implementations have
            buffer of any other temporary sequence that stores and saves all acquired
            objects to release them after process of component is completed.
        - A single PathLocker instance is shared across all dependent components.
            Therefore, the implementation must follow one of two strategies:
            either lock at most one path at any given time, or maintain an internal
            registry of acquired paths and release all of them after processing completes.
        - If the implementation chooses to lock only one path at a time, it must ensure
            that attempts to acquire a lock from other components while a lock is already
            held, do not crash or disrupt their execution. The lock should block until
            released and never throw an unhandled exception or cause a crash.
    """

    @abstractmethod
    def acquire(self, path: str) -> str:
        """
        Acquires an exclusive lock on the object at the given path.
        Blocks access from external processes until released.
        Returns the path to the locked object which may differ from
        the original path if the implementation relocates the object
        during locking. Implementations that do not relocate the object
        must return the original path unchanged.
        """
        ...

    @abstractmethod
    def release(self, path: str) -> None:
        """
        Releases the lock on the object at the given path.
        Must always be called after acquire() to release object and
        give access to other processes.
        """
        ...
