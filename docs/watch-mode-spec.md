# Ingest Watch Mode Spec

Issue: #1
Status: planned
Branch: TBD (planned name `feature/1-watch-mode`)

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
| Interval | `ingest.watch_interval`, default 30 (validation TBD below) |
| Mechanism | Polling daemon thread started in `main()`, no new dependencies |
| Error policy | A failed tick (disk error, Ollama down) is caught, logged to stderr, and the loop continues — the next tick retries; sync is idempotent |
| Import safety | Watcher starts only in `main()`, never at module import |

## Scope

### In scope

- `config.py`: new fields `ingest_watch` (bool, default True) and
  `ingest_watch_interval` (positive integer, default 30), with env
  overrides `RAG_MCP_INGEST_WATCH` and `RAG_MCP_INGEST_WATCH_INTERVAL`,
  and project TOML keys `[ingest] watch` / `[ingest] watch_interval`.
- `server.py`: a `_start_watcher()` helper plus a daemon thread loop
  started in `main()` after the startup auto-ingest. Each tick calls
  `sync_directory` with the same arguments the startup auto-ingest passes:
  store, ingest dir, collection, embeddings host/model, patterns.
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

- `test_config.py` additions:
  - defaults: `ingest_watch=True`, `ingest_watch_interval=30`
  - project-file parsing: `[ingest] watch` / `watch_interval`
  - env overrides: `RAG_MCP_INGEST_WATCH`, `RAG_MCP_INGEST_WATCH_INTERVAL`
  - invalid interval values → `ValueError` (non-int, zero, negative)
- `test_ingest_watch.py` (new):
  - injectable sleep function so tests never sleep in real time
  - sync called with the right arguments on each tick
  - a failed tick logs to stderr and the loop continues
  - loop stops cleanly on cancel
  - importing `rag_mcp.server` starts no watcher

## Process

1. Issue branch: `./scripts/issue-branch create feature 1 watch-mode`
2. RED (tests) → user review/approval gate
3. GREEN (implementation) → user review gate
4. Docs updates → user review gate
5. User reviews, commits, merges, releases (minor bump → v2.2.0)
