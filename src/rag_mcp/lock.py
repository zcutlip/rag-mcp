"""Cross-process write lock guarding the Chroma persist directory.

Every acquisition is a non-blocking try; nothing ever waits on the lock.
The kernel owns liveness: the advisory lock (flock on POSIX, LockFileEx on
Windows) is released by the OS when the holder dies, so a leftover lock
file is inert and presence never means held. The contract is pinned in
``docs/write-lock-spec.md``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from filelock import FileLock, Timeout


class WriteLockHeldError(RuntimeError):
    """Another process holds the write lock; retry once it completes."""


def write_lock_path(persist_dir: str) -> str:
    """Canonical sibling lock path: realpath(persist_dir) + '.lock'."""
    return os.path.realpath(persist_dir) + ".lock"


class _UnlockedLock:
    """Inert no-op lock token; nothing touches the filesystem."""


_UNLOCKED = _UnlockedLock()


@contextmanager
def try_write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock | None]:
    """Try-acquire without blocking; yield the lock, or None when held
    elsewhere. A None persist_dir passes through unlocked, yielding
    _UNLOCKED — never None, which always means held elsewhere
    (Amendments 2 and 6)."""
    if persist_dir is None:
        yield _UNLOCKED
        return
    lock = FileLock(write_lock_path(persist_dir))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        yield None
        return
    try:
        yield lock
    finally:
        lock.release()


@contextmanager
def write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock]:
    """Try-acquire; raise WriteLockHeldError when held elsewhere.
    A None persist_dir passes through unlocked, yielding _UNLOCKED
    (Amendments 2 and 6)."""
    if persist_dir is None:
        yield _UNLOCKED
        return
    lock_path = write_lock_path(persist_dir)
    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise WriteLockHeldError(
            f"write lock held at {lock_path}; retry once the current write completes"
        )
    try:
        yield lock
    finally:
        lock.release()
