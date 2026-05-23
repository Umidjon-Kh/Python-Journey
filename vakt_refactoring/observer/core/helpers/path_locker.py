from __future__ import annotations

from abc import ABC, abstractmethod


class BasePathLocker(ABC):
    """
    Abstract base class for file system level locking.

    A PathLock is responsible for acquiring and releasing
    exclusive access to a file system object at the OS level.
    This prevents external processes from modifying a file
    while Rollbacker is restoring it or any other components
    that require safe-modifying is processing with it.

    Implementations Example:
        - FcntlFileLock: Linux/macOS, uses fcntl.flock().
        - WindowsPathLock: Windows, uses msvcrt.locking().

    Notes:
        - PathLock operates at the OS level, not the thread level.
            It blocks access from external processes, not just threads
            within the same process.
        - Implementations must ensure that release() is always called
            after acquire(), even if an error occurs. Use try/finally
            or implement __enter__/__exit__ properly.
        - In base abstract cls not strictly requires __enter__/__exit__ methods
            implementations to work with context manager it only depends of realization.
        - Method release requires path to cause it enables to create an implementations
            that lock not one object at one time. But ensure this implementations have
            buffer of any other temporary sequence that stores and saves all acquired
            objects to release them after process of component is completed.
        - A single PathLock instance is shared across all dependent components.
            Therefore, the implementation must follow one of two strategies:
            either lock at most one path at any given time, or maintain an internal
            registry of acquired paths and release all of them after processing completes.
        - If the implementation chooses to lock only one path at a time, it must ensure
            that attempts to acquire a lock from other components while a lock is already
            held, do not crash or disrupt their execution. The lock should block until
            released and never throw an undanlded exception or cause a crash.
    """

    @abstractmethod
    def acquire(self, path: str) -> None:
        """
        Acquires an exclusive lock on the object at the given path.
        Blocks access from external processes until released.
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
