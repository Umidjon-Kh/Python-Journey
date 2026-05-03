from __future__ import annotations

from abc import ABC, abstractmethod


class BasePathLock(ABC):
    """
    Abstract base class for file system level locking.

    A PathLock is responsible for acquiring and releasing
    exclusive acces to a file system object at the OS level.
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
        - A single PathLock instance can be reused across different paths.
        - In base abstract cls not strictly requires __enter__/__exit__ methods
            implementations to work with context manager it only depends of realization.
        - Method release requires path to cause it enables to create an implementations
            that lock not one object at one time. But ensure this implementations have
            buffer of any other temporary sequence that stores and saves all acquired
            objects to release them after procces of component is completed.
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
