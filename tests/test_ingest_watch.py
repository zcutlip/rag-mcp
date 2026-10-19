"""Tests for the ingest watch mode background watcher."""
import subprocess
import sys
import threading
from unittest.mock import MagicMock, patch

from rag_mcp import server


def test_watch_loop_calls_sync_each_tick():
    """Each interval tick invokes sync once; the loop exits cleanly after cancel."""
    sync = MagicMock()
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 2:
            cancel.set()

    server._watch_loop(sync, 30, fake_sleep, cancel)
    assert sync.call_count == 2
    assert ticks == [30, 30]


def test_watch_loop_failed_tick_logs_and_continues(capsys):
    """A failed tick is logged to stderr and the loop keeps ticking."""
    sync = MagicMock(side_effect=[OSError("disk vanished"), None, None])
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 3:
            cancel.set()

    server._watch_loop(sync, 30, fake_sleep, cancel)
    assert sync.call_count == 3
    captured = capsys.readouterr()
    assert "disk vanished" in captured.err
    assert "Traceback" not in captured.err


def test_watch_loop_stops_cleanly_on_cancel():
    """A preset cancel event makes the loop a no-op."""
    sync = MagicMock()
    cancel = threading.Event()
    cancel.set()

    server._watch_loop(sync, 30, MagicMock(), cancel)
    sync.assert_not_called()


def test_watch_loop_no_sleep_before_first_tick():
    """The first sync happens immediately, before the first sleep."""
    order = []
    sync = MagicMock(side_effect=lambda: order.append("sync"))
    cancel = threading.Event()

    def fake_sleep(_interval):
        order.append("sleep")
        cancel.set()

    server._watch_loop(sync, 30, fake_sleep, cancel)
    assert order == ["sync", "sleep"]


def test_make_sync_fn_passes_ingest_args():
    """The watcher's sync callable passes store and config ingest args to sync_directory."""
    store = MagicMock()
    cfg = MagicMock(
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
        embeddings_host="http://h",
        embeddings_model="m",
        ingest_patterns=["*.md"],
    )
    sync_fn = server._make_sync_fn(store, cfg)
    with patch("rag_mcp.server.ingest.sync_directory") as mock_sync:
        sync_fn()
    mock_sync.assert_called_once_with(
        store,
        "/tmp/docs",
        collection="docs",
        embeddings_host="http://h",
        embeddings_model="m",
        patterns=["*.md"],
    )


def test_start_watcher_spawns_daemon_thread():
    """_start_watcher starts a daemon thread running the watch loop."""
    sync = MagicMock()
    with patch("rag_mcp.server.threading.Thread") as thread_cls:
        server._start_watcher(sync, 30)
    thread_cls.assert_called_once()
    instance = thread_cls.return_value
    assert thread_cls.call_args.kwargs["daemon"] is True
    instance.start.assert_called_once()


def test_import_server_starts_no_thread():
    """Importing rag_mcp.server spawns no threads (import-safety rule)."""
    code = "import threading, rag_mcp.server\nassert threading.active_count() == 1\n"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
