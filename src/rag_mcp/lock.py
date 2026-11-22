"""Cross-process write lock guarding the Chroma persist directory.

Scaffold state: ``try_write_lock`` and ``write_lock`` are pass-through
placeholders that yield ``_UNLOCKED``; real acquisition (filelock) and
``WriteLockHeldError`` raising land in the GREEN phase. The contract is
pinned in ``docs/write-lock-spec.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from filelock import FileLock


class WriteLockHeldError(RuntimeError):
    """Another process holds the write lock; retry once it completes."""


def write_lock_path(persist_dir: str) -> str:
    """Canonical sibling lock path: realpath(persist_dir) + '.lock'."""
    raise NotImplementedError("scaffold: lands in GREEN")


class _UnlockedLock:
    """Inert no-op lock token; nothing touches the filesystem."""


_UNLOCKED = _UnlockedLock()


@contextmanager
def try_write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock | None]:
    """Try-acquire without blocking; yield the lock, or None when held
    elsewhere. A None persist_dir passes through unlocked, yielding
    _UNLOCKED — never None, which always means held elsewhere
    (Amendments 2 and 6)."""
    # Scaffold: pass-through placeholder — every attempt yields _UNLOCKED.
    yield _UNLOCKED


@contextmanager
def write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock]:
    """Try-acquire; raise WriteLockHeldError when held elsewhere.
    A None persist_dir passes through unlocked, yielding _UNLOCKED
    (Amendments 2 and 6)."""
    # Scaffold: pass-through placeholder — never raises, yields _UNLOCKED.
    yield _UNLOCKED
