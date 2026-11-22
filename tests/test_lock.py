"""Tests for rag_mcp.lock: canonical path, try/write acquisition, pass-through."""
import os

import filelock
import pytest

from rag_mcp.lock import (
    _UNLOCKED,
    WriteLockHeldError,
    try_write_lock,
    write_lock,
    write_lock_path,
)


def test_write_lock_path_canonicalizes_to_realpath_sibling(tmp_path):
    """The lock path is the realpath-resolved sibling `.lock`.

    Trailing slashes, `.` components, and symlinks all canonicalize to one
    path, so every process naming the same dir computes the same lock path.
    """
    persist = tmp_path / "persist"
    persist.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(persist)

    base = write_lock_path(str(persist))
    assert base == os.path.realpath(str(persist)) + ".lock"
    assert write_lock_path(str(persist) + os.sep) == base
    assert write_lock_path(str(alias)) == base
    assert write_lock_path(os.path.join(str(persist), os.curdir)) == base


def test_try_write_lock_free_path_acquires_and_releases(tmp_path):
    """A free lock acquires: the lock file exists at the canonical path while
    held, a second in-process acquire is blocked, and release on context exit
    leaves the file present (POSIX flock path; the suite runs on POSIX)."""
    persist = tmp_path / "persist"
    persist.mkdir()
    lock_path = write_lock_path(str(persist))

    with try_write_lock(str(persist)) as lock:
        assert lock is not None
        assert lock is not _UNLOCKED
        assert os.path.exists(lock_path)
        probe = filelock.FileLock(lock_path)
        with pytest.raises(filelock.Timeout):
            probe.acquire(timeout=0)

    with filelock.FileLock(lock_path):
        pass
    assert os.path.exists(lock_path)


def test_try_write_lock_held_elsewhere_yields_none_then_acquires(tmp_path):
    """Under a concurrent holder, try_write_lock yields None; once the holder
    releases, the next attempt acquires."""
    persist = tmp_path / "persist"
    persist.mkdir()
    lock_path = write_lock_path(str(persist))

    holder = filelock.FileLock(lock_path)
    holder.acquire(timeout=0)
    try:
        with try_write_lock(str(persist)) as lock:
            assert lock is None
    finally:
        holder.release()

    with try_write_lock(str(persist)) as lock:
        assert lock is not None
        assert lock is not _UNLOCKED


def test_try_write_lock_abrupt_exit_still_releases(tmp_path):
    """An exception raised inside the with still releases the lock."""
    persist = tmp_path / "persist"
    persist.mkdir()

    with pytest.raises(RuntimeError):
        with try_write_lock(str(persist)):
            raise RuntimeError("boom")

    with try_write_lock(str(persist)) as lock:
        assert lock is not None
        assert lock is not _UNLOCKED


def test_write_lock_free_path_enters_and_releases(tmp_path):
    """A free write_lock enters (blocking a second in-process acquire) and
    releases on exit."""
    persist = tmp_path / "persist"
    persist.mkdir()
    lock_path = write_lock_path(str(persist))

    with write_lock(str(persist)):
        probe = filelock.FileLock(lock_path)
        with pytest.raises(filelock.Timeout):
            probe.acquire(timeout=0)

    with filelock.FileLock(lock_path):
        pass


def test_write_lock_held_raises_with_pinned_wording(tmp_path):
    """A held lock raises WriteLockHeldError with the exact pinned wording,
    lock path interpolated."""
    persist = tmp_path / "persist"
    persist.mkdir()
    lock_path = write_lock_path(str(persist))

    holder = filelock.FileLock(lock_path)
    holder.acquire(timeout=0)
    try:
        with pytest.raises(WriteLockHeldError) as exc_info:
            with write_lock(str(persist)):
                pass
    finally:
        holder.release()

    assert str(exc_info.value) == (
        f"write lock held at {lock_path}; retry once the current write completes"
    )


def test_none_persist_dir_passes_through_unlocked(tmp_path):
    """A None persist dir yields _UNLOCKED from both managers — never None,
    never raising — and touches nothing on the filesystem."""
    with try_write_lock(None) as lock:
        assert lock is _UNLOCKED
    with write_lock(None) as lock:
        assert lock is _UNLOCKED
    assert not list(tmp_path.iterdir())
