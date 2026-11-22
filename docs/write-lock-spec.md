# Write Lock Spec

Issue: #5
Status: spec approved 2026-11-19, Amendments 1-7 recorded; scaffold gate granted by the user 2026-11-22 ("scaffold stage approved") — scaffold landed, existing suite green; RED gate granted 2026-11-22 ("proceed") — RED contract written, RED-repair batch (checkpoint findings) applied, RED established: 17 failed / 186 passed, every failure the implementation's absence
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

## Supersedes

This spec retires a caveat that two shipped specs currently pin:

- `docs/watch-mode-spec.md`, concurrency note (lines 90-99):
  concurrent WRITES sharing one persistence dir are unsafe for
  multi-session use; a single-writer lockfile or client/server mode
  "remain documented future mitigations". The lockfile mitigation is
  this spec; that note is amended at the docs phase to say so.
- `docs/sync-logging-spec.md`, out-of-scope bullet (lines 153-154)
  and concurrency note (lines 163-165): "Running two sessions against
  one project remains unsupported for writes (issue #5)." After GREEN,
  writes are supported under the lock; both notes are amended at the
  docs phase.

README.md, `docs/configuration-spec.md`, and `AGENTS.md` carry no
concurrent-writes caveat (verified by grep 2026-11-19); the docs step
updates them only for the lock-file gitignore note, the two new log
line types, and AGENTS.md test counts.

## Design principles

1. **One writer at a time, zero waiting.** Every acquisition is a
   non-blocking try. No code path ever waits on the lock: the watcher
   and startup skip and log; manual tools raise a named, transient
   error. No pile-up, no blocked server, no deadlocks by construction.
   (Amendment 2: this guarantee is the production serving state, after
   `main()` recorded an existing persist dir; the `None` pass-through
   before that — or after the dir vanished — proceeds unlocked.
   Amendment 7: the vanished-dir arm can occur while the process is
   serving; what the store layer then does is Chroma's own behavior,
   not this spec's claim.)
2. **The lock spans the whole operation.** The corruption window is the
   operation — a full sync pass including its deletion diff, an add, a
   collection delete — not the individual Chroma call. Acquire once per
   operation, release at the end.
3. **The kernel owns liveness.** Advisory file locks via filelock
   (`fcntl.flock` on POSIX; a `LockFileEx` exclusive byte-range lock
   on Windows — both verified against the filelock 3.32.7 sources,
   the release `>=3,<4` installs, 2026-11-19) are released by the OS
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
| Mechanism | `filelock` package — new runtime dependency, `filelock>=3,<4` (resolves to 3.32.7, the newest 3.x; latest filelock is 4.2.12). POSIX: `fcntl.flock` (`LOCK_EX\|LOCK_NB`), contention = EACCES/EAGAIN/EWOULDBLOCK; Windows: `LockFileEx` exclusive byte-range lock, with `msvcrt` only bridging descriptors to handles (verified against the 3.32.7-tagged `_unix.py`/`_windows.py`, 2026-11-19). The kernel releases the lock on process death, so the no-stale-lock constraint holds by construction |
| Lock unit | One lock per persist dir. The persist dir is the corruption domain (per-process segment writers), not the collection |
| Lock path | Sibling of the persist dir: `os.path.realpath(persist_dir) + ".lock"`. realpath canonicalizes trailing slashes, relative spellings, and symlinks, so every process naming the same dir computes the same lock path. Sibling, not inside: no foreign files inside Chroma's directory (its tolerance for them is unverified), and the parent is necessarily writable wherever the persist dir is usable — Chroma creates a missing persist dir and its parents (`os.makedirs(..., exist_ok=True)` in `SqliteDB.__init__`, chromadb 1.5.9 source, verified 2026-11-19) |
| Lock file lifetime | Created on first acquire (filelock creates a missing lock-file parent directory on acquire — 3.32.7 `ensure_directory_exists`). Unix flock path: left in place after release — unlinking a locked file splits waiters across inodes; on filesystems without flock, filelock falls back to a soft lock and removes its own placeholder. Windows: deletion is attempted on release and may not succeed (3.32.7 `_release`, both verified 2026-11-19). Either way presence never means held; releasing closes the kernel lock, never the data |
| Try-only acquisition | All acquisitions are non-blocking tries (`acquire(timeout=0)` semantics). Nothing blocks on the lock |
| Critical sections | Startup auto-ingest, every watcher tick, the `sync` tool, `add_documents`, `delete_collection` — each wraps its full operation |
| Startup contention | Skip and log: `startup sync skipped: write lock held`. Start never blocks; with watch on, the next tick converges. With watch off, a skipped startup sync stays stale until a manual `sync` — accepted and documented below |
| Watcher contention | Skip and log one line per skipped tick: `watch sync skipped: write lock held`; the loop continues and the next interval retries |
| Manual-tool contention | `sync`, `add_documents`, `delete_collection` raise `WriteLockHeldError` at acquisition, before any mutation — in the production serving state; a `None` persist-dir pass-through (Amendment 2) is reachable pre-`main()` (module-internal/test use) or post-`main()` after the dir vanished, and proceeds unlocked in both arms (Amendment 7) |
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

class _UnlockedLock:
    """Inert no-op lock token; nothing touches the filesystem."""

_UNLOCKED = _UnlockedLock()

@contextmanager
def try_write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock | None]:
    """Try-acquire without blocking; yield the lock, or None when held
    elsewhere. A None persist_dir passes through unlocked, yielding
    _UNLOCKED — never None, which always means held elsewhere
    (Amendments 2 and 6)."""

@contextmanager
def write_lock(persist_dir: str | None) -> Iterator[FileLock | _UnlockedLock]:
    """Try-acquire; raise WriteLockHeldError when held elsewhere.
    A None persist_dir passes through unlocked, yielding _UNLOCKED
    (Amendments 2 and 6)."""
```

Callers distinguish solely on `is None` (Amendment 6): `None` means
held elsewhere; an acquired `FileLock` and the `_UNLOCKED`
pass-through both mean proceed.

`server.py` module state + call sites (behavior lands in GREEN):

- `main()` records `_persist_dir = config.chroma_persist_dir` once
  (module state, same pattern as the `store` singleton);
  `get_persist_dir() -> str | None` returns it only when that
  directory exists on disk, else `None` (Amendment 2)
- `main()` startup auto-ingest → `try_write_lock(get_persist_dir())`;
  yielded `None` (held elsewhere) → emit the skip line; an acquired
  lock or the `_UNLOCKED` pass-through → sync and emit the existing
  `startup sync:` line
- `_make_sync_fn`'s inner `_sync()` → `try_write_lock`; yielded
  `None` (held elsewhere) → return the module-level sentinel
  `_SKIP_TICK` (`server.py`); else the sync result. `_watch_loop`
  emits the skip line on that sentinel and continues. `None` keeps
  its existing meaning — a sync callable returning nothing to log —
  so the locked watch tests stay green untouched (Amendment 1)
- `sync`, `add_documents`, `delete_collection` →
  `write_lock(get_persist_dir())` around the mutation; all five call
  sites source the dir from `get_persist_dir()`, never `get_config()`
  (Amendment 2)

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
- The lock is advisory: it excludes only lock-aware rag-mcp writers. An
  older rag-mcp build serving another tab, or any process writing the
  persist dir through Chroma directly, never acquires it and writes
  regardless (Amendment 7).

## Test plan (flat style, tests as locked contract)

- `tests/test_lock.py` (new)
  - `write_lock_path`: sibling `.lock` of the realpath-resolved dir;
    trailing slash, relative spelling, and `.` components canonicalize
    to the same path
  - `try_write_lock` free path: acquires; lock file exists at the
    canonical path; released on context exit; file still present after
    release on the POSIX flock path (Windows attempts deletion — see
    Lock file lifetime; the suite runs on POSIX)
  - `try_write_lock` under a second concurrent holder: yields `None`;
    acquires once the holder releases; an abrupt holder exit
    (exception raised inside the `with`) still releases
  - `write_lock` free path: enters and releases
  - `write_lock` under a second holder: raises `WriteLockHeldError`
    with the exact pinned wording, lock path interpolated
  - `None` pass-through (Amendment 6 contract): `try_write_lock(None)`
    yields `_UNLOCKED`, never `None`; `write_lock(None)` yields
    `_UNLOCKED` and never raises; neither touches the filesystem
- `tests/test_server.py` (additions)
  - server-level lock simulation (Amendment 2; used by every
    following bullet): patch `rag_mcp.server.get_persist_dir` to
    return a `tmp_path` persist dir; "held" = the test pre-acquires
    the sibling lock itself
    (`filelock.FileLock(write_lock_path(str(tmp_path)))` — a second
    in-process fd contends on flock); "free" = no pre-acquire;
    "pass-through" = the patch returns `None` (Amendment 7: an
    explicit patch, never reliance on module state being unset —
    `main()` tests leave `_persist_dir` residue, so an unpatched
    accessor is order-dependent)
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
  - tick with the lock held: `_sync` returns `_SKIP_TICK`, the loop
    emits `watch sync skipped: write lock held`, `sync_directory`
    NOT called, and the loop continues; lock released before the next
    tick: that tick syncs normally
  - idle/changed-tick behavior unchanged (existing tests stay green)
- `tests/test_lock_integration.py` (new — the issue's acceptance test)
  - two `sys.executable` subprocesses on one tmp persist dir and one
    tiny corpus, both running a real `sync_directory`: exactly one
    syncs, the other exits with a clean skip sentinel; a fresh
    `VectorStore` on the dir afterwards serves the corpus (index
    valid); both processes exit without manual cleanup
  - no Ollama dependency: the corpus is frontmatter-only files, which
    chunk to nothing, so `get_embeddings([])` early-returns and the
    children never call the embedding host
  - pinned handshake so "exactly one syncs" is deterministic: the
    winner child acquires, drops a `held` marker file, and holds
    until the parent drops a `release` marker; the loser's attempt is
    made only while the winner still holds; the parent asserts on
    markers and exit sentinels, never on timing
  - holder dies mid-hold: the doomed child acquires, drops its `held`
    marker, then `os._exit(1)`s while still holding; the parent waits
    for the marker, then its next acquire succeeds with no cleanup —
    kernel release, the killed-during-write acceptance criterion

## Process

1. Branch: `scripts/issue-branch create fix 5 writer-lock` (done — 323b6a6)
2. Spec written (this file) → user review/approval gate (this step)
3. Scaffold: `lock.py` with the pinned signatures as pass-through
   placeholders (`try_write_lock` yields `_UNLOCKED`, `write_lock`
   never raises — the existing suite stays green), `filelock` added to
   `pyproject.toml` and installed into `~/.virtualenvs/rag-mcp` (the
   env `scripts/run-tests.sh` activates — the repo has no project
   venv; as of 2026-11-19 that venv is missing on this machine and
   must be recreated per the script's own guidance before any suite
   run), the five `server.py` call sites wired. New tests then fail
   on assertions, not on missing symbols → user gate
4. RED: write the test plan above and establish RED via the test
   subagent (`./scripts/run-tests.sh -q`) → user gate
5. GREEN: implement `lock.py` on `filelock`, activate the call sites →
   full suite green → user gate
6. Docs: amend the two specs that pin the retired caveat —
   `docs/watch-mode-spec.md` §Concurrency and
   `docs/sync-logging-spec.md` §Out of scope + §Concurrency note (see
   Supersedes); README (multi-tab is now safe when every overlapping
   session runs the lock-aware build; add the lock-file gitignore
   note for the sibling `<persist_dir>.lock`; add the two new line
   types `startup sync skipped:` and `watch sync skipped:` to the
   line-type list); `AGENTS.md` module list and test counts;
   `CHANGELOG.md` `[Unreleased]` bullets — the lock and the two
   skip-line types; finish promotes the section but never authors
   entries (Amendment 7) → user gate
7. User reviews, commits, `scripts/issue-branch finish` (merge + tag,
   closes #5)

## Amendment ledger

- **Amendment 1** (approved 2026-11-19, pre-scaffold): a
  lock-contention skip is signaled by the dedicated module-level
  sentinel `_SKIP_TICK` in `server.py`, not by `None`. Found while
  checking the scaffold wiring surface: the locked test
  `test_watch_loop_failed_tick_keeps_failure_format`
  (tests/test_ingest_watch.py) stubs `None` as an ordinary silent
  tick and asserts exactly one sink emit, so a None-means-skip
  contract breaks it at scaffold. `None` keeps its existing meaning
  (a sync callable returned nothing to log); `_watch_loop` owns the
  skip line; `_make_sync_fn`'s signature is unchanged. Supersedes
  the "`dict | None`, `_watch_loop` treats `None` as a skipped tick"
  wording in the Pinned API and Test plan sections.
- **Amendment 2** (approved by the user 2026-11-19, "make amendment 2
  to the spec"; originally proposed 2026-11-19, revised the same day
  per checkpoint cp-dbd338 to pin the seam): the lock path is sourced
  from module state, not live config. Pinned seam (the approved
  scaffold contract):
  - `server.py` module state `_persist_dir: str | None = None`,
    assigned once in `main()` as
    `_persist_dir = config.chroma_persist_dir` (same pattern as the
    `store` singleton; no separate setter)
  - `server.py` accessor `get_persist_dir() -> str | None`:
    returns the recorded value only when that directory exists on
    disk, else `None`
  - `lock.py` signatures widen:
    `try_write_lock(persist_dir: str | None) -> Iterator[FileLock | None]`
    and `write_lock(persist_dir: str | None) -> Iterator[FileLock]`;
    `None` passes through unlocked
  - all five call sites consume `get_persist_dir()`; no call site
    reads `get_config()` for the lock path
  **This is a deliberate fail-open**: on the `None` path a manual tool
  proceeds without exclusion instead of raising, which narrows design
  principle 1 and the Manual-tool contention decision to the
  production serving state. It is reachable before `main()` has
  run (module-internal use, as the locked tests exercise the tools)
  or after the persist dir vanished from disk; in production the
  tools serve only after `main()`, whose `VectorStore` construction
  has already created or validated the persist dir, so every
  production write sees a recorded dir — the vanished-dir arm,
  reachable while serving, passes through unlocked rather than
  locking normally.
  Reason: three locked-test collisions (the delete_collection tests
  patch no `get_config` at tests/test_server.py:108,159;
  `_make_sync_fn`'s config mock leaves `chroma_persist_dir`
  unspecified at tests/test_ingest_watch.py:86, so the auto-created
  child mock hands a non-path object to `os.path.realpath` — a
  `TypeError`, not a missing attribute; main()'s tests fake persist
  path `/tmp/project/.chroma` at tests/test_server.py:769, where a
  real acquire silently creates `/tmp/project/` plus a stray
  `/tmp/project/.chroma.lock` — filelock 3.32.7 creates a missing
  lock-file parent chain on acquire
  (`Path.parent.mkdir(parents=True, exist_ok=True)` in `_util.py`,
  verified 2026-11-19) — so a real lock in a locked test litters or
  errors depending on the machine, both unacceptable).
  Supersedes the implicit config-sourcing of the call sites in the
  Pinned API section; principles 2 and 4 and the scope table are
  unchanged. Approved with this fail-open statement and the pinned
  seam as part of what the user adopted; landing it updated the
  Pinned API signatures, the call-site bullets, principle 1, and the
  Manual-tool contention row to the narrowed production-serving
  scope.
- **Amendment 3** (checkpoint corrections, applied 2026-11-19 from
  review cp-c0c8acae of the approved draft — CONCERNS verdict, five
  findings, each verified against the tree):
  1. Adds the Supersedes section naming the shipped specs that pin
     the retired concurrent-writes caveat (`docs/watch-mode-spec.md`
     §Concurrency; `docs/sync-logging-spec.md` §Out of scope and
     §Concurrency note), and corrects the docs step to amend those —
     README, `docs/configuration-spec.md`, and `AGENTS.md` carry no
     caveat (verified by grep 2026-11-19).
  2. Names `~/.virtualenvs/rag-mcp` (the env `scripts/run-tests.sh`
     activates) as the scaffold install target; the repo has no
     project venv, so "installed into the project venv" was not
     executable as written.
  3. Pins the integration-test handshake (winner: acquire → `held`
     marker → hold until the parent's `release` marker; loser
     attempts only while the winner holds; doomed child: `held`
     marker, then `os._exit(1)` mid-hold; the parent asserts on
     markers, never on timing) and the no-Ollama mechanism
     (frontmatter-only corpus → zero chunks → `get_embeddings([])`
     early-returns).
  4. Adds to the docs step: the README lock-file gitignore note for
     the sibling `<persist_dir>.lock`, and the two new line types
     (`startup sync skipped:`, `watch sync skipped:`) missing from
     README's line-type list.
  5. States one verified locking mechanism (POSIX `fcntl.flock`
     `LOCK_EX\|LOCK_NB`; Windows `LockFileEx` exclusive byte-range
     lock, `msvcrt` only bridging descriptors — verified against
     upstream `_unix.py`/`_windows.py`, 2026-11-19), superseding the
     contradictory "flock/`LockFileEx`" and "fcntl/flock + msvcrt
     shim" wording; corrects the lock-file lifetime row (Unix keeps
     the file by design; Windows attempts deletion on release).
- **Amendment 4** (checkpoint corrections, applied 2026-11-19 from
  review cp-713f5bc of the Amendment 3 state — CONCERNS verdict, two
  findings, both verified):
  1. Reconciles the test plan with the corrected lock-file lifetime
     row: the `try_write_lock` free-path bullet no longer asserts
     "file still present after release" cross-platform — it is
     POSIX-flock-path-scoped (Windows attempts deletion; the suite
     runs on POSIX). Re-verified mechanism and release behavior
     against filelock **3.32.7**, the release `>=3,<4` actually
     installs (latest filelock is 4.2.12), replacing the upstream-
     main citations in principle 3, the Mechanism row, and the
     lifetime row, and recording two facts found in the tagged
     source: filelock creates a missing lock-file parent on acquire
     (`ensure_directory_exists`), and on flock-less filesystems it
     falls back to a soft lock that removes its own placeholder —
     the Unix "kept by design" claim is flock-path-scoped.
  2. Corrects Amendment 2's pending-proposal text: states the
     `None` path as a deliberate fail-open that narrows principle 1
     and the Manual-tool contention decision to the production
     serving state, and replaces collision 3's "cannot support a
     real acquire" rationale — under 3.32.7 a real acquire on the
     faked path would instead silently create `/tmp/project/` and a
     stray `/tmp/project/.chroma.lock` via
     `ensure_directory_exists`, so the locked main test litters
     rather than errors. Neither behavior is acceptable in a locked
     test; the collision stands with the corrected mechanism.
- **Amendment 5** (checkpoint corrections, applied 2026-11-19 from
  review cp-dbd338 of the pending Amendment 2 proposal — CONCERNS
  verdict, two findings, both verified):
  1. Completes the pending proposal as a scaffold contract: pins the
     module-state seam it introduces — `_persist_dir` assigned in
     `main()`, accessor `get_persist_dir() -> str | None`, the
     widened `try_write_lock`/`write_lock` signatures, call-site
     consumption — inside the proposal itself; the planned pointer
     note in the Pinned API section failed on an exact-match edit
     error and was never landed (recorded here for truth; with
     Amendment 2 approved, the section itself now carries the
     widened signatures, mooting the note); and pins the
     server-level lock-test simulation in the test plan (patch
     `rag_mcp.server.get_persist_dir` to a `tmp_path` dir; "held" =
     the test pre-acquires the sibling lock, a second in-process fd
     contending; "free" = no pre-acquire; unpatched = the `None`
     pass-through). A pending amendment that leaves names for the
     scaffold to invent is not approvable as-is.
  2. Corrects collision 2's failure mode: the MagicMock config at
     tests/test_ingest_watch.py:86-92 does not lack
     `chroma_persist_dir` — an unspecified attribute on a MagicMock
     auto-creates a child mock, so the mock hands a non-path object
     to `os.path.realpath` and fails with `TypeError`. The collision
     stands; the mechanism was misdescribed.
  3. Verified the collision 3 / lifetime-row basis against the
     3.32.7-tagged `_util.py`: `ensure_directory_exists` does
     `Path(filename).parent.mkdir(parents=True, exist_ok=True)` —
     the full missing parent chain is created on acquire. The
     corrected collision 3 wording stands as written.
- **Amendment 6** (approved by the user 2026-11-22, "make the edit";
  proposed the same day from a review of the approved spec): a
  `None` persist-dir pass-through yields the named no-op sentinel,
  never `None`. Pinned contract:
  - `lock.py` defines `_UnlockedLock`, an inert token (nothing
    touches the filesystem), and the module-level singleton
    `_UNLOCKED = _UnlockedLock()`
  - `try_write_lock(None)` and `write_lock(None)` yield `_UNLOCKED`;
    the pinned annotations widen to
    `Iterator[FileLock | _UnlockedLock | None]` and
    `Iterator[FileLock | _UnlockedLock]`
  - callers distinguish solely on `is None`, which keeps exactly one
    meaning — held elsewhere — so a pass-through can never emit a
    false skip line or raise a false `WriteLockHeldError`
  - the startup and watcher call-site bullets now read "yielded
    `None` (held elsewhere)", and process step 3's scaffold stub
    "yields a dummy" is now "yields `_UNLOCKED`" — the scaffold
    invents nothing
  Reason: the approved Pinned API left the pass-through yield
  unnamed, so `None` was ambiguous between held-elsewhere and
  no-persist-dir-on-record; a vanished-dir pass-through yielding
  `None` would emit a false `write lock held` skip line on every
  tick. Closes the scaffold-invention gap under Amendment 5's own
  standard ("a pending amendment that leaves names for the scaffold
  to invent is not approvable as-is"). Supersedes the "passes
  through unlocked" wording of the Pinned API docstrings, the bare
  `None` of the startup and watcher bullets, and process step 3's
  unnamed dummy; Amendment 2's ledger entry and its fail-open
  statement stand unchanged.
- **Amendment 7** (approved by the user 2026-11-22, "go ahead and make
  your amendment"; items 1-3 from the user's primary-session review of
  the Amendment 6 diff — its verdict confirmed against the tree in
  this session — items 4-5 from this session's review findings):
  1. Corrects the "never serves" family: the vanished-dir
     pass-through is reachable while the process is serving, so the
     Manual-tool contention row's "precedes `main()` and never
     serves", principle 1's "never serves in production", and
     Amendment 2's "recorded, existing dir and locks normally" were
     each false for that arm; corrected in place (the Amendment 4
     precedent). The fix does not adopt the reviewing session's
     "fails harmlessly at the store layer" wording: Chroma's
     behavior on a vanished persist dir mid-session is unverified;
     this spec claims only "proceeds unlocked".
  2. Test plan: the server-level simulation's pass-through case is an
     explicit `get_persist_dir` patch returning `None`; the previous
     "unpatched accessor (module state unset)" was order-dependent —
     `main()` tests leave `_persist_dir` residue, and residue
     pointing at an existing dir acquires a real lock instead of
     exercising the pass-through. Adds the lock-level `None`
     pass-through bullet to `tests/test_lock.py` (the Amendment 6
     contract, previously untested in the plan).
  3. Residual risks + docs step: the lock is advisory — it excludes
     only lock-aware rag-mcp writers; an older build in another tab
     or a foreign Chroma writer bypasses it. README's multi-tab
     claim gains "when every overlapping session runs the lock-aware
     build".
  4. Process step 6 gains the `CHANGELOG.md` `[Unreleased]` bullets:
     the section is empty and finish promotes without authoring, so
     the branch must write its own entries.
  5. Records the provenance gap in commit 1dd51f5: the Amendment 5
     entry was rewritten in place (the pointer-note truth-fix) with
     only an inline parenthetical; the established pattern carries
     such corrections inside a numbered amendment, which this entry
     now does.
  Also records: a checkpoint review of the pre-Amendment-6 spec
  flagged the `None`-yield ambiguity as blocking; Amendment 6's
  `_UNLOCKED` sentinel is that fix, and the four tests it cited were
  re-checked against the current wiring — each takes the proceed
  branch and stays green — so that finding is stale and nothing
  blocks scaffold on that account.
  Supersedes principle 1's "never serves in production", the
  Manual-tool contention row's "precedes `main()` and never serves",
  Amendment 2's "recorded, existing dir and locks normally" tail,
  and the test plan's "the unpatched accessor (module state unset)
  exercises the `None` pass-through".
