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
| Error policy | A failed tick (disk error, Ollama down) is caught, logged to stderr, and the loop continues — the next tick retries; sync is idempotent |
| Import safety | Watcher starts only in `main()`, never at module import |
| Env bool strictness | `RAG_MCP_INGEST_WATCH` accepts only `true`/`false` (case-insensitive); any other value raises `ValueError` naming the env var — fail fast, not truthy-tolerant |
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
    sleep (tests never sleep in real time); each tick sleeps `interval`
    first, then calls `sync` when the `threading.Event` cancel is not set;
    a cancel ends the loop cleanly; a failed sync logs the exception
    message to stderr (no traceback) and the loop continues with the next
    sleep. Amended post-RED: sleep-first tagging (was sync-first; the
    sync-first shape double-synced at startup alongside the auto-ingest —
    test `test_watch_loop_no_sleep_before_first_tick` was replaced at the
    user's contract-amendment gate by `test_watch_loop_sleeps_before_first_tick`).
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
- `test_ingest_watch.py` (new):
  - injectable sleep function so tests never sleep in real time
  - loop syncs one interval after a sleep; sleeps-before-first-tick
    semantics (amended: was sync-then-sleep; replaced test
    `test_watch_loop_no_sleep_before_first_tick` →
    `test_watch_loop_sleeps_before_first_tick`)
  - sync called with the right arguments on each tick
  - a failed tick logs to stderr and the loop continues
  - loop stops cleanly on cancel
  - importing `rag_mcp.server` starts no watcher

## Process

1. Issue branch: `scripts/issue-branch create feature 1 watch-mode`
2. Spec amendment (this file): branch metadata + interval decision lock → user review/approval gate
3. RED (tests) → user review/approval gate
4. GREEN (implementation) → user review gate
5. Docs updates → user review gate
6. User reviews, commits, merges (`scripts/issue-branch finish`), releases (minor → v2.2.0)
