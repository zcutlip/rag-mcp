# Sync Logging Spec

Issue: #6
Status: design agreed — Amendment 3 (file prefix) pending review
Branch: dev/6-sync-logging (created with `scripts/issue-branch create feature 6 sync-logging`)

## Objective

Make the sync lifecycle observable. Before this change the server is silent
when it succeeds: a healthy watcher and a dead one look identical, and the
only evidence of an auto-ingest is a later query returning the right
documents. Every lifecycle event — start, startup sync, changing tick,
failed tick, shutdown — is emitted as one line, to stderr and to a
project-local log file, so the operator can tell what the server resolved,
what it synced, and why it stopped.

## Design principles

1. **Silence means idle, not broken.** A tick that changed nothing prints
   nothing. This is what keeps a 5-second `watch_interval` tolerable; the
   "quiet by default" constraint is enforced structurally, not by a
   verbosity flag.
2. **Two sinks, one source of truth.** Each line goes to stderr (immediate,
   inherited by the launching client) and is appended to a project-local
   file (durable, per-project, greppable after the fact). One sink object
   owns both, so the two cannot drift.
3. **Lines identify their process.** opencode funnels every local MCP
   server's stderr into one global log tagged only by the server's config
   key — identical across projects, and ambiguous when several sessions
   run. Each stderr line therefore carries the project name and the PID; the
   per-project file needs only the PID.
4. **Logging never breaks the server.** An unusable log file degrades to
   stderr-only with one warning. Writes never raise into the sync path.
5. **stdout stays protocol-clean.** MCP stdio owns stdin/stdout for
   JSON-RPC; not one byte of logging goes there.

## Locked decisions

| Item | Decision |
|---|---|
| Channels | stderr (`<tag>` prefix) + project-local file (`<ISO timestamp> pid=<pid> ` prefix); the body is identical on both |
| Line prefix | stderr: `rag-mcp[<project-dir-name>:<pid>]` on every line — project basename, then the OS PID of this rag-mcp child process. File: `<ISO timestamp> pid=<pid>` — see File form |
| Prefix application | `_LogSink(path, tag, pid)` owns both prefixes: callers pass a bare body, the sink writes `<tag> <body>` to stderr and `<ISO timestamp> pid=<pid> <body>` to the file. The failure body stays byte-for-byte `watch sync failed: {exc!r}`, so its test remains an exact assertion |
| Project line | `project='<project root>'`, emitted once at startup, before the start line |
| Project root | Directory containing the discovered `.rag-mcp.toml`; the process cwd when no project file exists. Stored on `Config` so the tag and path rendering never re-derive it |
| Path rendering | A path inside the project root prints relative to it (`docs`, `.chroma`); a path outside prints absolute. Never `..`, never a `./` prefix |
| Log file path | `[logging] path` in `.rag-mcp.toml`, default `.rag-mcp.log` at the project root, env override `RAG_MCP_LOGGING_PATH`; relative resolves against the project root and must stay within it, absolute is used as-is |
| `[logging]` placement | Project-local only. `[logging]` in the global `config.toml` raises `ValueError` |
| Rotation | 1 MB cap checked before each write; the full file rotates to `<path>.1` (single backup, overwritten) |
| File unavailable | One `rag-mcp log file unavailable: <exc!r> (continuing stderr-only)` warning, then stderr-only for the process lifetime |
| Thread safety | One lock per sink serializes writes from the server thread and the watcher thread |
| Multi-process | Concurrent children append to the same file; interleaving at append granularity is accepted. This is diagnostic evidence, not a mitigation — see issue #5 |
| Construction site | The sink is created in `main()` only, never at module import (same import-safety rule as the watcher) |
| Error policy | Unchanged: a failed tick emits `watch sync failed: {exc!r}`, no traceback, loop retries next tick. `BaseException` is still not caught |
| Shutdown reason | `reason=exit` normally; `reason=SIGTERM` when SIGTERM was received (handler raises `SystemExit(128 + signum)`). Only SIGKILL is silent |

## Output format

### Line types

| Event | Line body (after the stderr prefix `rag-mcp[<project>:<pid>] `) | Frequency |
|---|---|---|
| Project | `project='<project root>'` | once per run, before the start line |
| Start | `start: persist_dir='<path>' ingest_dir='<path>' collection='<name>' watch=<bool> watch_interval=<int>` | once per run, after the store is built |
| Startup sync | `startup sync: added=A updated=U deleted=D unchanged=N` | once per run, only when `ingest.directory` is set |
| Tick | `watch sync: added=A updated=U deleted=D unchanged=N` | per tick, only when `added + updated + deleted > 0` |
| Failed tick | `watch sync failed: <exc repr>` | per failed tick |
| Shutdown | `shutdown: reason=exit\|SIGTERM` | once per run, from a `finally` around `mcp.run()` |

`ingest_dir` renders as `None` when no ingest directory is configured.

### Example (stderr, project `platform-security-guide-scraper`)

```text
rag-mcp[platform-security-guide-scraper:48213] project='/Users/zach/Sync/Projects/src/platform-security-guide-scraper'
rag-mcp[platform-security-guide-scraper:48213] start: persist_dir='.chroma' ingest_dir='docs' collection='platform-security' watch=True watch_interval=30
rag-mcp[platform-security-guide-scraper:48213] startup sync: added=2 updated=0 deleted=0 unchanged=180
rag-mcp[platform-security-guide-scraper:48213] watch sync: added=1 updated=0 deleted=0 unchanged=182
rag-mcp[platform-security-guide-scraper:48213] watch sync: added=0 updated=2 deleted=0 unchanged=182
rag-mcp[platform-security-guide-scraper:48213] shutdown: reason=SIGTERM
```

### Example (same run, with directories outside the project)

```text
rag-mcp[platform-security-guide-scraper:48213] project='/Users/zach/Sync/Projects/src/platform-security-guide-scraper'
rag-mcp[platform-security-guide-scraper:48213] start: persist_dir='/Volumes/External/rag-chroma' ingest_dir='/Users/zach/Sync/Notes/wiki' collection='platform-security' watch=True watch_interval=30
rag-mcp[platform-security-guide-scraper:48213] watch sync failed: OSError('disk vanished')
rag-mcp[platform-security-guide-scraper:48213] shutdown: reason=exit
```

### File form

File lines carry the identical body behind a different prefix:
`<ISO-8601 UTC timestamp> pid=<pid> `.

```text
2026-11-06T19:46:18.037Z pid=13056 project='/Users/zach/Sync/Projects/src/apple-platform-security-guide'
2026-11-06T19:46:18.038Z pid=13056 start: persist_dir='.chroma' ingest_dir='docs' collection='default' watch=True watch_interval=60
2026-11-06T19:46:18.144Z pid=13056 startup sync: added=0 updated=0 deleted=0 unchanged=187
2026-11-06T20:12:03.501Z pid=13056 watch sync: added=0 updated=1 deleted=0 unchanged=186
2026-11-06T20:14:59.220Z pid=13056 watch sync failed: OSError('disk vanished')
2026-11-06T21:03:44.910Z pid=13056 shutdown: reason=exit
```

The file is per project and named for the tool, so `rag-mcp` and the project
name add nothing the path does not already say. The PID does: two sessions on
one project append to the same file, and it is the only way to attribute a
line to one of them. `pid=` matches the `key=value` style of the bodies and
greps without escaping brackets. Timestamps are file-only so stderr stays
terse; both sinks keep the body identical, so a body substring still matches
in either channel, and a `pid=<n>` grep selects one instance across both.

## Scope

### In scope

- `config.py`: `Config.logging_path` and `Config.project_root`; `[logging] path`
  parsing with `RAG_MCP_LOGGING_PATH` override; project-root resolution and
  subpath constraint; rejection of `[logging]` in the global file and of a
  non-table `logging` key; validation of empty/non-string paths.
- `server.py`: `_LogSink` (stderr + append, rotation, warn-once degrade,
  close), `_emit()` (sink-or-stderr), `_format_sync_counts()`,
  `_instance_tag(config)`, `_display_path(path, root)`,
  `_install_sigterm_handler(state)`; `_make_sync_fn` returns the sync result;
  `_watch_loop`/`_start_watcher` take an optional sink; `main()` emits
  project/start/startup-sync/shutdown lines around `mcp.run()`.
- Tests: `test_config.py` (project root, logging path resolution/validation),
  `test_server.py` (tag, project line, start/startup/shutdown lines, path
  rendering, sink behavior including timestamp and rotation),
  `test_ingest_watch.py` (tagged tick line, gated idle ticks, unchanged
  failure text, sink forwarding).

### Out of scope

- MCP log notifications (`notifications/message`): deprecated by the spec and
  unusable from the watcher thread.
- Log levels or a verbosity flag: quiet-by-default is structural (idle ticks
  are silent), so no knob is needed.
- Fixing concurrent-writer corruption (issue #5). This spec only makes
  concurrent children visible; it does not mediate between them.
- Log shipping, structured/JSON output, per-line rotation checks beyond the
  size cap.
- Changes to `ingest.py`, `store.py`, `embeddings.py`.

## Concurrency note

Each stdio session is its own OS process; the watcher is a thread inside it.
Two children on one project therefore write two independent watchers' lines
into the same file, and the PID is the only way to attribute a tick to one of
them. Running two sessions against one project remains unsupported for writes
(issue #5); the log makes that state visible rather than preventing it.

## Test plan (flat style, tests as locked contract)

Status: the three committed test files pin the pre-amendment format (no tag,
no PID, no project line, absolute paths, no timestamps). They are amended
before implementation, and the suite must go red against the committed
implementation first.

- `test_config.py`
  - `project_root` is the `.rag-mcp.toml` directory; cwd when no project file
  - `logging_path` default `<root>/.rag-mcp.log`; relative resolves to root;
    absolute used as-is; env overrides `[logging]`; escaping relative path
    raises; empty/non-string raises naming `logging.path`; `[logging]` in the
    global file raises; non-table `logging` raises
- `test_server.py`
  - `_instance_tag()` → `rag-mcp[<basename>:<pid>]`
  - `_display_path()`: inside root → relative without `./`; outside → absolute;
    never `..`
  - `_format_sync_counts()` fixed field order, missing keys default to zero
  - project line, start line, startup sync line, shutdown line (`exit` and
    `SIGTERM`), shutdown on `SystemExit` out of `mcp.run()`
  - no startup sync line without an ingest dir
  - sink: stderr `<tag> <body>` + file `<timestamp> pid=<pid> <body>`, rotation
    at cap, warn-once degrade to stderr, close on shutdown
- `test_ingest_watch.py`
  - changed tick emits exactly one tagged line with counts
  - idle ticks emit nothing
  - failed tick emits `watch sync failed: OSError('disk vanished')` (exact body
    equality — the tag is applied by the sink, so the body is unchanged)
  - `_make_sync_fn` returns the sync result; `_start_watcher` forwards the sink

## Process

1. Branch: `scripts/issue-branch create feature 6 sync-logging` (done)
2. Spec written (this file) → user review/approval gate
3. Scaffold → already satisfied by the committed implementation `30ab67d`:
   the helpers the amended tests name (`_instance_tag`, `_display_path`,
   `_LogSink`, `Config.project_root`) exist or are part of this amendment, so
   no structural gap prevents the tests from expressing themselves. Any gap
   found at amendment time is a spec amendment first, never invented in code.
4. Test amendment → RED re-entry → user review/approval gate
5. GREEN implementation → user review gate
6. Docs: README, `docs/configuration-spec.md`, `AGENTS.md`; align
   `docs/watch-mode-spec.md` lines 41 and 126 with this spec → user review gate
7. User reviews, commits, finishes (`scripts/issue-branch finish`)

## Amendment ledger

- **Amendment 1** (this file, awaiting approval): the format agreed after the
  GREEN commit — project tag with PID on every line, `project=` line,
  root-relative path rendering, file-only timestamps, and `Config.project_root`
  as the anchor. Supersedes the untagged format pinned by commits `d6fb84c`,
  `e32061b`, `a918349` and implemented in `30ab67d`. Adds the `[logging]`
  contract to the project-local-only rule alongside `ingest.patterns`.
- **Amendment 2** (approved, committed): the prefix is applied by `_LogSink(path, tag)`,
  not by individual emit sites. Callers pass bare bodies, so the failure line
  stays byte-for-byte unchanged and its test remains an exact assertion. The
  test-plan line was corrected to match; no observable format change.
- **Amendment 3** (this change, awaiting approval): the file prefix is reduced to
  `<ISO timestamp> pid=<pid> ` — `rag-mcp` and the project name are redundant in
  a per-project, tool-named file, while the PID remains the only way to
  attribute a line to one of several sessions appending to it. The sink becomes
  `_LogSink(path, tag, pid)` and renders each channel's prefix itself; stderr is
  unchanged. Supersedes the file-prefix rule in Amendment 2 and the single-prefix
  wording of the Channels and Prefix application rows, plus the File form section.
