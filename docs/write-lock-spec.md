# Write Lock Spec

Issue: #5
Status: draft — spec phase; branch created (323b6a6); awaiting user review/approval before scaffold
Branch: dev/5-writer-lock (created with `scripts/issue-branch create fix 5 writer-lock`)

## Objective

Make overlapping writers on one Chroma persist dir safe. Every opencode
tab is its own rag-mcp process, and with `ingest.directory` set each is
a periodic writer (startup sync plus watcher tick) plus an on-demand one
(`add_documents`, `sync`, `delete_collection`). Watch mode promotes
concurrency from rare to routine: N open tabs are N periodic writers.
Chroma's PersistentClient is thread-safe but not process-safe for
concurrent writers — HNSW segment writers are per-process and outside
SQLite's serialization — so overlapping writes can corrupt the index.
The fix is a cross-process advisory write lock per persist dir:
try-acquire, never block, one writer at a time, losers skip or fail
transiently.

Every constraint in the issue body is user-stated: multi-tab sharing one
project/persist dir must be safe, not "don't do that"; losing ticks skip
cleanly and retry on the next interval; nothing may pile up or block the
server; no new running services (no `chroma run`); a dead process must
not block future writers.

## Design principles

1. **One writer at a time, zero waiting.** Every acquisition is a
   non-blocking try. No code path ever waits on the lock: the watcher
   and startup skip and log; manual tools raise a named, transient
   error. No pile-up, no blocked server, no deadlocks by construction.
2. **The lock spans the whole operation.** The corruption window is the
   operation — a full sync pass including its deletion diff, an add, a
   collection delete — not the individual Chroma call. Acquire once per
   operation, release at the end.
3. **The kernel owns liveness.** Advisory file locks (`flock` via
   filelock on POSIX, `LockFileEx` on Windows) are released by the OS
   when the holder dies. No pid files, no liveness checks, no cleanup
   commands. A leftover lock file is inert: presence never means held.
4. **Inner layers stay lock-free.** `store.py`, `ingest.py`, and
   `embeddings.py` do not know the lock exists. The seam is a new
   `lock.py` module used at the server-side call sites, so nested
   acquisition is impossible by construction.
5. **Failure is transient, never damage.** A losing caller is a no-op:
   contention is detected at acquisition, before any mutation, so the
   index always holds exactly the winning writer's result. Retrying
   after the winner finishes succeeds.

## Provenance

Constraints and acceptance sketch: issue #5 body (user-authored). The
three open design decisions — mechanism (`filelock` package), startup
contention policy (skip and log), manual-tool policy (fail fast with a
named error) — were selected by the user at branch kickoff 2026-11-18.
The transient (non-permanent) failure semantics were confirmed by the
user 2026-11-19 before this spec was written.

## Locked decisions

| Item | Decision |
|---|---|
| Mechanism | `filelock` package — new runtime dependency, `filelock>=3,<4`. Cross-platform fcntl/flock + msvcrt shim; the kernel releases the lock on process death, so the no-stale-lock constraint holds by construction |
| Lock unit | One lock per persist dir. The persist dir is the corruption domain (per-process segment writers), not the collection |
| Lock path | Sibling of the persist dir: `os.path.realpath(persist_dir) + ".lock"`. realpath canonicalizes trailing slashes, relative spellings, and symlinks, so every process naming the same dir computes the same lock path. Sibling, not inside: no foreign files inside Chroma's directory (its tolerance for them is unverified), and the parent is necessarily writable wherever the persist dir is usable — Chroma creates the dir itself when missing |
| Lock file lifetime | Created on first acquire, never deleted. Presence does not mean held; releasing closes the kernel lock, not the file |
| Try-only acquisition | All acquisitions are non-blocking tries (`acquire(timeout=0)` semantics). Nothing blocks on the lock |
| Critical sections | Startup auto-ingest, every watcher tick, the `sync` tool, `add_documents`, `delete_collection` — each wraps its full operation |
| Startup contention | Skip and log: `startup sync skipped: write lock held`. Start never blocks; with watch on, the next tick converges. With watch off, a skipped startup sync stays stale until a manual `sync` — accepted and documented below |
| Watcher contention | Skip and log one line per skipped tick: `watch sync skipped: write lock held`; the loop continues and the next interval retries |
| Manual-tool contention | `sync`, `add_documents`, `delete_collection` raise `WriteLockHeldError` at acquisition, before any mutation |
| Error wording | `write lock held at <lock path>; retry once the current write completes` — transient contention, not a broken state. The holder may be another process's write or this process's own watcher tick |
| `add_documents` ordering | Embeddings are computed before the lock attempt; the lock wraps only the store write. Contention costs one wasted embedding call; embedding under the lock would instead lengthen every add's critical section by the Ollama round trip |
| `delete_collection` ordering | The `list_collections` existence pre-check stays outside the lock (a read); the delete itself is inside |
| Reads | Unlocked: `query_documents`, `list_collections`, and the sync pass's metadata reads when already inside a critical section stay as they are. Concurrent reads across processes are safe |
| Failure semantics | A losing caller is a no-op — no partial write, no state change; a retry after the winner completes succeeds. Nothing about contention is permanent |
| No config surface | No `[chroma]` key, no env var, unconditional. Safe-by-default is the deliverable, not an option |
| Line routing | Skip lines go through `_emit(sink, ...)`: stderr + project file per the sync-logging spec, silent when `[logging] enabled` is false, like every other lifecycle line |

## Pinned API (scaffold contract)

New module `src/rag_mcp/lock.py`:

```python
class WriteLockHeldError(RuntimeError): ...

def write_lock_path(persist_dir: str) -> str:
    """Canonical sibling lock path: realpath(persist_dir) + '.lock'."""

@contextmanager
def try_write_lock(persist_dir: str) -> Iterator[FileLock | None]:
    """Try-acquire without blocking; yield the lock, or None when held elsewhere."""

@contextmanager
def write_lock(persist_dir: str) -> Iterator[FileLock]:
    """Try-acquire; raise WriteLockHeldError when held elsewhere."""
```

`server.py` call sites (behavior lands in GREEN):

- `main()` startup auto-ingest → `try_write_lock`; `None` → emit the
  skip line; else sync and emit the existing `startup sync:` line
- `_make_sync_fn`'s inner `_sync()` → `try_write_lock`; `None` →
  return `None`; else the sync result. The result contract widens to
  `dict | None`, and `_watch_loop` treats `None` as a skipped tick,
  emitting the skip line
- `sync`, `add_documents`, `delete_collection` → `write_lock` around
  the mutation

## Scope

### In scope

- `src/rag_mcp/lock.py` — the pinned API above
- `server.py` — the five call sites plus `_watch_loop` skip handling
- `pyproject.toml` — `filelock>=3,<4` in runtime dependencies
- Tests: `tests/test_lock.py` and `tests/test_lock_integration.py`
  (new); additions to `tests/test_server.py` and
  `tests/test_ingest_watch.py`

### Out of scope

- Chroma client/server mode (`chroma run` + `HttpClient`) — issue #5's
  Option B, the documented heavy-use answer, not this fix
- Read-path locking (reads are already safe across processes)
- Per-collection locking (the persist dir is the corruption domain)
- Chroma-internal crash recovery: a SIGKILL mid-write may leave Chroma's
  own files inconsistent — that is Chroma's durability domain. This
  spec guarantees the lock releases and the next writer proceeds
- `config.py` — no new keys or env vars
- Changes to `store.py`, `ingest.py`, `embeddings.py`

## Residual risks (accepted, documented)

- `VectorStore.__init__` (PersistentClient construction) runs before
  any lock and is not serialized. Two sessions constructing
  simultaneously race on directory/SQLite creation exactly as they do
  today; the observed corruption modes (segment writes) are inside the
  locked operations. Construction stays out of scope; the risk is
  recorded here rather than silently taken.
- With watch off, a skipped startup sync leaves the index stale until a
  manual `sync`; the logged skip line makes that state visible.

## Test plan (flat style, tests as locked contract)

- `tests/test_lock.py` (new)
  - `write_lock_path`: sibling `.lock` of the realpath-resolved dir;
    trailing slash, relative spelling, and `.` components canonicalize
    to the same path
  - `try_write_lock` free path: acquires; lock file exists at the
    canonical path; released on context exit; file still present after
    release (inert, not deleted)
  - `try_write_lock` under a second concurrent holder: yields `None`;
    acquires once the holder releases; an abrupt holder exit
    (exception raised inside the `with`) still releases
  - `write_lock` free path: enters and releases
  - `write_lock` under a second holder: raises `WriteLockHeldError`
    with the exact pinned wording, lock path interpolated
- `tests/test_server.py` (additions)
  - `add_documents` with the lock held: embeddings called (outside the
    lock), store write NOT called, `WriteLockHeldError` raised; lock
    free: store write called and the lock released after the call
  - `sync` tool with the lock held: `sync_directory` NOT called,
    raises; lock free: called with unchanged arguments
  - `delete_collection` with the lock held: existence pre-check still
    runs, delete NOT called, raises; lock free: deletes
  - `main()` startup with the lock held: `sync_directory` NOT called,
    one `startup sync skipped: write lock held` line; lock free:
    unchanged `startup sync:` line, lock released after
- `tests/test_ingest_watch.py` (additions)
  - tick with the lock held: `_sync` returns `None`, the loop emits
    `watch sync skipped: write lock held`, `sync_directory` NOT
    called, and the loop continues; lock released before the next
    tick: that tick syncs normally
  - idle/changed-tick behavior unchanged (existing tests stay green)
- `tests/test_lock_integration.py` (new — the issue's acceptance test)
  - two `sys.executable` subprocesses on one tmp persist dir and one
    tiny corpus, both running a real `sync_directory` with embeddings
    stubbed: exactly one syncs, the other exits with a clean skip
    sentinel; a fresh `VectorStore` on the dir afterwards serves the
    corpus (index valid); both processes exit without manual cleanup
  - holder dies mid-hold (`os._exit(1)` while holding): the parent's
    next acquire succeeds with no cleanup — kernel release, the
    killed-during-write acceptance criterion

## Process

1. Branch: `scripts/issue-branch create fix 5 writer-lock` (done — 323b6a6)
2. Spec written (this file) → user review/approval gate (this step)
3. Scaffold: `lock.py` with the pinned signatures as pass-through
   placeholders (`try_write_lock` yields a dummy, `write_lock` never
   raises — the existing suite stays green), `filelock` added to
   `pyproject.toml` and installed into the project venv, the five
   `server.py` call sites wired. New tests then fail on assertions,
   not on missing symbols → user gate
4. RED: write the test plan above and establish RED via the test
   subagent (`./scripts/run-tests.sh -q`) → user gate
5. GREEN: implement `lock.py` on `filelock`, activate the call sites →
   full suite green → user gate
6. Docs: README (multi-tab is now safe; the unsupported-for-writes
   caveat retires), `docs/configuration-spec.md` and `AGENTS.md` where
   they carry that caveat, test counts → user gate
7. User reviews, commits, `scripts/issue-branch finish` (merge + tag,
   closes #5)

## Amendment ledger

(none yet)
