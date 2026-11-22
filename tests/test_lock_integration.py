"""Cross-process acceptance tests for the write lock (issue #5).

Two real subprocesses share one tmp persist dir and one tiny corpus of
frontmatter-only files — zero chunks, so get_embeddings([]) early-returns
and no child ever calls the embedding host. The handshake is pinned: the
winner drops a `held` marker and holds until the parent drops `release`;
the loser attempts only while the winner demonstrably holds; the parent
asserts on markers and exit codes, never on timing.
"""
import subprocess
import sys
import time

from rag_mcp.lock import _UNLOCKED, try_write_lock
from rag_mcp.store import VectorStore

_CHILD_SCRIPT = '''\
"""Acceptance child. argv: role persist_dir corpus_dir collection held release."""
import os
import sys
import time

from rag_mcp.ingest import sync_directory
from rag_mcp.lock import try_write_lock
from rag_mcp.store import VectorStore

role, persist_dir, corpus_dir, collection, held_path, release_path = sys.argv[1:7]


def wait_for(path, limit_s=30.0):
    deadline = time.monotonic() + limit_s
    while not os.path.exists(path):
        if time.monotonic() > deadline:
            sys.exit(5)
        time.sleep(0.02)


if role == "doomed":
    with try_write_lock(persist_dir) as lock:
        if lock is None:
            print("SKIPPED", flush=True)
            sys.exit(3)
        with open(held_path, "w") as f:
            f.write("held")
        os._exit(1)  # die mid-hold, bypassing release

with try_write_lock(persist_dir) as lock:
    if lock is None:
        print("SKIPPED", flush=True)
        sys.exit(3)
    with open(held_path, "w") as f:
        f.write("held")
    result = sync_directory(
        VectorStore(persist_dir=persist_dir),
        corpus_dir,
        collection=collection,
        embeddings_host="http://127.0.0.1:9",  # never reached: zero chunks
        embeddings_model="nomic-embed-text",
    )
    print(
        f"SYNCED added={result['added']} unchanged={result['unchanged']}",
        flush=True,
    )
    if role == "winner":
        wait_for(release_path)  # hold the lock until the parent drops `release`

sys.exit(0)
'''


def _wait_for_marker(path, message, limit_s=30.0):
    """Block until `path` exists, failing loudly after the limit."""
    deadline = time.monotonic() + limit_s
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(message)
        time.sleep(0.02)


def _spawn_child(script, role, persist, corpus, collection, held, release):
    return subprocess.Popen(
        [
            sys.executable,
            str(script),
            role,
            str(persist),
            str(corpus),
            collection,
            str(held),
            str(release),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_two_children_one_syncs_other_skips(tmp_path):
    """Two processes on one persist dir: exactly one syncs, the other exits
    with the clean skip sentinel; a fresh store afterwards opens the index,
    and both children exit without manual cleanup."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "frontmatter-only.md").write_text(
        "---\ntitle: Only frontmatter\n---\n"
    )
    persist = tmp_path / "persist"
    held = tmp_path / "held"
    release = tmp_path / "release"
    script = tmp_path / "child.py"
    script.write_text(_CHILD_SCRIPT)

    winner = _spawn_child(
        script, "winner", persist, corpus, "acceptance", held, release
    )
    loser = None
    try:
        _wait_for_marker(held, "winner never dropped its held marker")
        loser = _spawn_child(
            script, "loser", persist, corpus, "acceptance", held, release
        )
        loser_out, loser_err = loser.communicate(timeout=60)
        release.write_text("go")
        winner_out, winner_err = winner.communicate(timeout=60)
    finally:
        for proc in (winner, loser):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()

    assert winner.returncode == 0, winner_err
    assert "SYNCED" in winner_out, winner_out
    assert loser.returncode == 3, (loser_out, loser_err)
    assert "SKIPPED" in loser_out, loser_out

    VectorStore(persist_dir=str(persist)).list_collections()


def test_holder_death_releases_lock(tmp_path):
    """A holder that dies mid-hold (os._exit while holding) leaves the lock
    acquirable with no cleanup — the kernel released it."""
    persist = tmp_path / "persist"
    persist.mkdir()
    held = tmp_path / "held"
    release = tmp_path / "release"
    script = tmp_path / "child.py"
    script.write_text(_CHILD_SCRIPT)

    doomed = _spawn_child(
        script, "doomed", persist, tmp_path, "acceptance", held, release
    )
    try:
        _wait_for_marker(held, "doomed child never dropped its held marker")
        doomed_rc = doomed.wait(timeout=60)
    finally:
        if doomed.poll() is None:
            doomed.kill()
            doomed.wait()

    assert doomed_rc == 1

    with try_write_lock(str(persist)) as lock:
        assert lock is not None
        assert lock is not _UNLOCKED
