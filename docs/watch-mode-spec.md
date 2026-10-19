# Ingest Watch Mode Spec

Issue: #1
Status: in progress (spec amended 2026-10-18: interval locked as configurable)
Branch: dev/1-watch-mode (created with `scripts/issue-branch create feature 1 watch-mode`, dev version 2.2.0.dev1+issue-1-watch-mode)

## Objective

Detect and re-sync changes in the ingest directory automatically while the
MCP server is running, instead of requiring a manual `sync` tool call or a
server restart. Changes made to files on disk are picked up by a background
watcher without user intervention.

## Design principles

1. **Watch by default.** Whenever `ingest.directory` is set, a background
   watcher starts automatically — the mental model matches the existing
   startup auto-ingest: configure an ingest directory and sync just works,
   continuously. An explicit opt-out exists (`ingest.watch = false` /
   `RAG_MCP_INGEST_WATCH=false`).
2. **Polling, not filesystem events.** `sync_directory` is already
   idempotent: the sha256 comparison in the sync pass short-circuits before
   chunking or embedding, so an unchanged directory costs zero Ollama calls
   per interval (one `coll.get` + one SHA256 per file). Polling is simple,
   dependency-free, and avoids debounce/race complexity. Watchdog-style
   event notification remains the documented future upgrade path.
3. **Import safety.** The watcher starts only inside `main()`, never at
   module import — module-level execution would fire on every
   `import rag_mcp.server`, including test imports (same rule as the
   startup auto-ingest).

## Locked decisions

| Item | Decision |
|---|---|
| Default | Watch ON whenever `ingest.directory` is set |
| Opt-out | `ingest.watch = false` / `RAG_MCP_INGEST_WATCH=false` |
| Interval | `ingest.watch_interval` (seconds), default 30 — configurable; positive integer validated eagerly (fails fast with `ValueError` on non-int, zero, or negative) |
| Mechanism | Polling daemon thread started in `main()`, no new dependencies |
| Tick order | Sleep-first each tick: `_watch_loop` sleeps `interval`, then syncs when not cancelled — the first watcher sync lands one interval after start, so the watcher never duplicates the startup auto-ingest sync |
| Error policy | A failed sync raises `Exception` (any non-`BaseException`); it is caught, logged to stderr as a single line — `watch sync failed: {exc!r}` — no traceback, and the loop continues with the next sleep. `BaseException` subclasses (e.g. `KeyboardInterrupt`) are NOT caught: they kill the watcher thread; the server process is unaffected (daemon thread). A `sleep_fn` failure is likewise uncaught (production sleep is `time.sleep`, which cannot meaningfully fail) |
| Cancel semantics (pinned post-RED) | The cancel `threading.Event` is a test seam; no production code sets it. All phases pinned: **before loop** → no-op (never sleeps, never syncs); **mid-sleep** → the armed tick's sync is suppressed and the loop exits immediately (prompt exit — a stopped watcher never fires one more sync); **mid-sync** → the in-flight sync completes, the loop exits before the next sleep. Teardown is process exit (daemon thread dies with the process); there is no production stop path |
| Start gating | The watcher starts in `main()` only when `ingest_dir` is set AND `ingest_watch` is true, after the startup auto-ingest has run (or would have — same condition on `ingest_dir`). It is never started at module import |
| Config capture | The watcher closes over the resolved `Config` at start; config snapshot semantics apply — edits to `.rag-mcp.toml` mid-run (host, model, patterns, interval, watch flag) take effect only on restart |
| No production stop path | Nothing in `server.py` sets the watcher's cancel event; the daemon thread dies with the process. The cancel event exists as a test seam and any future stop mechanism is out of scope for this issue
| Import safety | Watcher starts only in `main()`, never at module import |
| Env bool strictness | `RAG_MCP_INGEST_WATCH` accepts only `true`/`false` (case-insensitive); any other value — including the empty string — raises `ValueError` naming the env var. An unset variable is the only way to "not set" it; empty string is invalid, not absent (fail fast, not truthy-tolerant) |
| TOML watch strictness | `[ingest] watch` accepts only a TOML boolean; any non-bool (`"yes"`, string, int) raises `ValueError` naming `ingest.watch` |
| Interval validation | `[ingest] watch_interval` and `RAG_MCP_INGEST_WATCH_INTERVAL` must parse to a positive integer; TOML accepts int only (zero, negative, non-int, float raise `ValueError`) |
| Error message | Both TOML- and env-originated interval/constraint errors report `ingest.watch_interval` in the message (single phrasing for both sources) |

## Scope

### In scope

- `config.py`: new fields `ingest_watch` (bool, default True) and
  `ingest_watch_interval` (positive integer, default 30), with env
  overrides `RAG_MCP_INGEST_WATCH` and `RAG_MCP_INGEST_WATCH_INTERVAL`,
  and project TOML keys `[ingest] watch` / `[ingest] watch_interval`.
- `server.py`: a `_start_watcher()` helper plus a daemon thread loop
  started in `main()` after the startup auto-ingest. Helper shapes are
  pinned by the tests:
  - `_watch_loop(sync, interval, sleep_fn, cancel_event)` — injectable
    sleep (tests never sleep in real time). Per-tick order and all cancel
    phases are pinned in the Locked decisions table (sleep-first; prompt
    exit; mid-sync completes). Amended post-RED: sleep-first tagging (was
    sync-first; the sync-first shape double-synced at startup alongside the
    auto-ingest — test `test_watch_loop_no_sleep_before_first_tick` was
    replaced at the user's contract-amendment gate by
    `test_watch_loop_sleeps_before_first_tick`); cancel-mid-sleep pinned to
    prompt exit (post-RED amendment 2).
  - `_make_sync_fn(store, cfg)` — builds the per-tick sync callable;
    invokes `ingest.sync_directory(store, ingest_dir, collection=...,
    embeddings_host=..., embeddings_model=..., patterns=...)` — the same
    arguments the startup auto-ingest passes.
  - `_start_watcher(sync, interval)` — spawns the daemon `threading.Thread`
    (`daemon=True`) running `_watch_loop`.
- Documentation: new `docs/watch-mode-spec.md` (this file), README section,
  AGENTS.md env-var list and ingestion architecture paragraph,
  `docs/configuration-spec.md` key tables.

### Out of scope

- `watchdog` event-based watcher (documented future upgrade path).
- Changes to `store.py` (ChromaDB wrapper stays opaque) and `ingest.py`
  (sync logic untouched — the watcher only re-invokes `sync_directory`).
- Changes to `rag-mcp-config`.
- A dedicated MCP tool for watch control.

## Concurrency note

Each stdio session is its own process. Concurrent ChromaDB READS among
processes are safe; concurrent WRITES sharing one persistence dir are not
(process-local HNSW segment writers are outside SQLite serialization). A
watcher makes a session a periodic writer, so a known caveat is that N
simultaneously running sessions are N periodic writers against one
persist dir. Fine for single-session and read-heavy use; for heavy
multi-session use a single-writer lockfile or client/server mode remain
documented future mitigations.

## Test plan (RED, flat style, tests as locked contract)

Status: **RED established** — 15 contract-shaped failures; the 16th new test
(`test_import_server_starts_no_thread`) passes immediately as a disclosed
guard: no watcher exists to start, and it will stay green through GREEN.
(`test_config.py` +6, `test_server.py` +3, `tests/test_ingest_watch.py` new 7;
62 passing elsewhere unchanged).

- `test_config.py` additions:
  - defaults: `ingest_watch=True`, `ingest_watch_interval=30`
  - project-file parsing: `[ingest] watch` / `watch_interval`
  - env overrides: `RAG_MCP_INGEST_WATCH`, `RAG_MCP_INGEST_WATCH_INTERVAL`
  - invalid interval values → `ValueError` (non-int, zero, negative)
  - (post-RED amendment 3 additions) non-bool TOML `watch` → `ValueError`
    naming `ingest.watch`; empty-string `RAG_MCP_INGEST_WATCH` → `ValueError`
    naming the env var
- `test_ingest_watch.py` (new):
  - injectable sleep function so tests never sleep in real time
  - loop syncs one interval after a sleep; sleeps-before-first-tick
    semantics (amended: was sync-then-sleep; replaced test
    `test_watch_loop_no_sleep_before_first_tick` →
    `test_watch_loop_sleeps_before_first_tick`)
  - sync called with the right arguments on each tick; cancel mid-sleep
    suppresses the armed tick (post-RED amendment 2: thresholds ≥3 sleeps /
    2 syncs, ≥4 sleeps / 3 syncs — prompt exit)
  - a failed tick logs to stderr (`watch sync failed: {exc!r}`, no
    traceback) and the loop continues
  - loop stops cleanly on cancel (preset → no-op)
  - mid-sync cancel: in-flight sync completes, no further sleep — pinned
    by amendment 3
  - importing `rag_mcp.server` starts no watcher

## Process

1. Issue branch: `scripts/issue-branch create feature 1 watch-mode`
2. Spec amendment (this file): branch metadata + interval decision lock → user review/approval gate
3. RED (tests) → user review/approval gate
4. GREEN (implementation) → user review gate
5. Docs updates → user review gate
6. User reviews, commits, merges (`scripts/issue-branch finish`), releases (minor → v2.2.0)

## Amendment ledger

- **Amendment 1** (user-approved, committed): interval locked as configurable
  `ingest.watch_interval`, default 30, positive-int validation, env
  `RAG_MCP_INGEST_WATCH_INTERVAL`; branch metadata recorded.
- **Amendment 2** (user-approved, committed): RED disclosures pinned — helper
  shapes, tick order sleep-first (replacing sync-first, which double-synced
  at startup), env/TOML validation strictness, error-message phrasing.
  Test replaced: `test_watch_loop_no_sleep_before_first_tick` →
  `test_watch_loop_sleeps_before_first_tick`.
- **Amendment 3** (consolidated, this change): full exit-path audit. Pinned:
  cancel semantics in all three phases (before-loop no-op, mid-sleep prompt
  exit, mid-sync complete-then-exit); exception breadth (`Exception` caught,
  `BaseException` kills the thread, `sleep_fn` failure uncaught); start
  gating condition (`ingest_dir` AND `ingest_watch`); config capture
  (snapshot at start, restart to re-read); TOML `watch` non-bool rejects;
  env watch empty-string rejects; failed-tick log format. Riding the same
  gate: test amendments for cancel-mid-sleep prompt exit (thresholds ≥3/≥4)
  and new tests for the two untested exit paths in `test_config.py`.
  Root cause recorded: cancel-mid-sleep was left unpinned at RED, so the
  two RED-era tests invented contradictory codes for it.
