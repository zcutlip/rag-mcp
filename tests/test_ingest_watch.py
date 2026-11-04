"""Tests for the ingest watch mode background watcher."""
import subprocess
import sys
import threading
from unittest.mock import MagicMock, patch

from rag_mcp import server


def test_watch_loop_calls_sync_each_tick():
    """Each completed sleep invokes sync once; cancel mid-sleep exits before any sync.

    Amended at the prompt-exit gate (amendment 3): a cancel set during a sleep
    suppresses that tick's sync instead of firing it.
    """
    sync = MagicMock()
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 3:
            cancel.set()

    server._watch_loop(sync, 30, fake_sleep, cancel)
    assert sync.call_count == 2
    assert ticks == [30, 30, 30]


def test_watch_loop_failed_tick_logs_and_continues(capsys):
    """A failed tick is logged to stderr and the loop keeps ticking.

    Amended at the prompt-exit gate (amendment 3): cancel threshold shifted so
    the cancel lands mid-sleep after the failed tick's sync.
    """
    sync = MagicMock(side_effect=[OSError("disk vanished"), None, None])
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 4:
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


def test_watch_loop_sleeps_before_first_tick():
    """The loop sleeps before its first sync; cancel mid-sleep ends the loop.

    Amended from test_watch_loop_no_sleep_before_first_tick (sync-then-sleep)
    at the contract-amendment gate: sleep-first avoids double-syncing at
    startup alongside the auto-ingest pass.
    """
    order = []
    sync = MagicMock(side_effect=lambda: order.append("sync"))
    cancel = threading.Event()

    def fake_sleep(_interval):
        order.append("sleep")
        if order.count("sleep") >= 2:
            cancel.set()

    server._watch_loop(sync, 30, fake_sleep, cancel)
    assert order == ["sleep", "sync", "sleep"]
    assert sync.call_count == 1


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


def test_watch_loop_logs_changed_tick_with_counts():
    """A tick that changed something emits exactly one line with the counts."""
    sync = MagicMock(
        return_value={"added": 2, "updated": 1, "deleted": 3, "unchanged": 40}
    )
    sink = MagicMock()
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 2:
            cancel.set()

    server._watch_loop(sync, 5, fake_sleep, cancel, sink)
    assert sync.call_count == 1
    sink.emit.assert_called_once_with(
        "rag-mcp watch sync: added=2 updated=1 deleted=3 unchanged=40"
    )


def test_watch_loop_idle_tick_emits_nothing():
    """Fully-idle ticks stay silent even as `unchanged` grows."""
    sync = MagicMock(
        return_value={"added": 0, "updated": 0, "deleted": 0, "unchanged": 900}
    )
    sink = MagicMock()
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 3:
            cancel.set()

    server._watch_loop(sync, 5, fake_sleep, cancel, sink)
    assert sync.call_count == 2
    sink.emit.assert_not_called()


def test_watch_loop_failed_tick_keeps_failure_format():
    """A failed tick emits the unchanged `watch sync failed: {exc!r}` line."""
    sync = MagicMock(side_effect=[OSError("disk vanished"), None])
    sink = MagicMock()
    cancel = threading.Event()
    ticks = []

    def fake_sleep(_interval):
        ticks.append(_interval)
        if len(ticks) >= 3:
            cancel.set()

    server._watch_loop(sync, 5, fake_sleep, cancel, sink)
    sink.emit.assert_called_once_with(
        "watch sync failed: OSError('disk vanished')"
    )


def test_make_sync_fn_returns_sync_result():
    """The watcher callable returns sync_directory's result for tick logging."""
    store = MagicMock()
    cfg = MagicMock(
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
        embeddings_host="http://h",
        embeddings_model="m",
        ingest_patterns=None,
    )
    sync_fn = server._make_sync_fn(store, cfg)
    counts = {"added": 1, "updated": 0, "deleted": 2, "unchanged": 3}
    with patch("rag_mcp.server.ingest.sync_directory") as mock_sync:
        mock_sync.return_value = counts
        assert sync_fn() == counts


def test_start_watcher_passes_sink_to_loop():
    """_start_watcher forwards the sink into the watch loop thread args."""
    sync = MagicMock()
    sink = MagicMock()
    with patch("rag_mcp.server.threading.Thread") as thread_cls:
        server._start_watcher(sync, 30, sink)
    args = thread_cls.call_args.kwargs["args"]
    assert args[4] is sink
