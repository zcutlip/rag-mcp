# Configuration Spec

## Objective

Provide a strict, project-isolated configuration model that prevents
accidental sharing of vector-store data between unrelated projects.
Configuration is loaded from a global TOML (`config.toml`) for machine-level
embedding-provider defaults and a project-local TOML (`.rag-mcp.toml`) for
per-project data settings, with `RAG_MCP_*` env vars as overrides.

## Design principles

1. **No silent shared database.** `chroma.persist_dir` has no platform
   fallback. It must be set in `.rag-mcp.toml` or via
   `RAG_MCP_CHROMA_PERSIST_DIR`.
2. **Project-local defaults are version-controllable.** Relative paths in
   `.rag-mcp.toml` resolve against the project root and are constrained to
   it, so `./.chroma` works without absolute paths leaking into git.
3. **Global config is for machine-level connection settings only.**
   `[chroma]`/`[ingest]` keys in the global file are ignored.

## Scope

### In scope

- Two-file config: global `config.toml` + project `.rag-mcp.toml`.
- Project file discovered by walking up from the current working directory.
- Relative-path resolution against project root with subpath constraint.
- Env-var override layer (`RAG_MCP_*`).
- Required `chroma.persist_dir` validation.
- README + AGENTS.md docs reflecting the new model.

### Out of scope

- Explicit `RAG_MCP_PROJECT_CONFIG` env var (declined — too fragile across
  clients with respect to env-var expansion; cwd walk-up is sufficient).
- `[chroma]`/`[ingest]` in global config (ignored to avoid confusion).
- Runtime re-configuration / hot reload.

## Locked decisions

| Item | Decision |
|---|---|
| Global file | `config.toml` at `platformdirs.user_config_dir("rag-mcp")`; reads only `[embeddings]` |
| Project file | `.rag-mcp.toml`, discovered by cwd walk-up |
| Precedence | defaults < global `<embeddings>` < project file < env vars |
| Project root | Directory containing the discovered `.rag-mcp.toml` |
| Relative paths | Resolved against project root, must stay within it |
| Global `[chroma]`/`[ingest]` | Ignored |
| `persist_dir` missing | Fail fast |
| Discovery mechanism | Cwd walk-up only (no explicit env var) |

## Config files

### Global `config.toml`

Holds machine-level embedding-provider defaults only. Located at
`platformdirs.user_config_dir("rag-mcp") / "config.toml"`. Override path
with `RAG_MCP_CONFIG`.

```toml
[embeddings]
host = "http://localhost:11434"
model = "nomic-embed-text"
```

### Project `.rag-mcp.toml`

Holds project-local data settings. Discovered by walking up from `cwd`.
Commit this file in your repo for portability:

```toml
[chroma]
persist_dir = "./.chroma"

[ingest]
directory = "./docs"
collection = "default"
```

Relative paths resolve against the directory containing `.rag-mcp.toml`
(the project root) and must stay within it. Absolute paths are also
accepted. Add `.chroma/` (or whatever you chose) to `.gitignore`.

## Env vars (override the files)

| Var | Overrides |
|---|---|
| `RAG_MCP_CONFIG` | global file path |
| `RAG_MCP_EMBEDDINGS_HOST` | `embeddings.host` (global or project) |
| `RAG_MCP_EMBEDDINGS_MODEL` | `embeddings.model` (global or project) |
| `RAG_MCP_CHROMA_PERSIST_DIR` | `chroma.persist_dir` (project only) |
| `RAG_MCP_INGEST_DIR` | `ingest.directory` (project only) |
| `RAG_MCP_INGEST_COLLECTION` | `ingest.collection` (project only) |

Precedence: defaults < global `<embeddings>` < project file < env vars.

## Validation (fail fast, at `load_config()`)

- `embeddings.host` — valid URL, scheme `http`/`https`
- `embeddings.model` — non-empty string
- `ingest.collection` — non-empty string
- `chroma.persist_dir` — required; `~`-expanded; relative paths resolve
  against project root and must stay within it
- `ingest.directory` — `~`-expanded; relative paths resolve against project
  root and must stay within it; if set, must be an existing directory
- Global file: invalid TOML → `ValueError` naming the path; `RAG_MCP_CONFIG`
  set to a missing file → `ValueError`
- Project file: invalid TOML → `ValueError` naming the path

## File-by-file changes

### `src/rag_mcp/config.py`

- New helpers: `_find_project_config_path(cwd=None)` walks up from cwd
  looking for `.rag-mcp.toml`. `_resolve_path(value, root=None)` expands
  `~`, resolves absolute paths as-is, and for relative paths requires a
  project root, joins, resolves, and validates subpath containment.
- `load_config(config_path=None, environ=os.environ)`:
  - Loads global file; reads only `[embeddings]`.
  - Discovers project file via cwd walk-up.
  - Merges: `defaults < global[embeddings] < project[embeddings/chroma/ingest] < env`.
  - Resolves `persist_dir` and `ingest.directory` with `_resolve_path`.
  - Validates: host URL, model non-empty, `persist_dir` non-empty, ingest
    dir exists if set, collection non-empty.
  - Returns `Config`.
- `get_config()` unchanged in signature; uses the updated `load_config()`.

### `src/rag_mcp/server.py`, `embeddings.py`, `store.py`, `ingest.py`

- Unchanged. They consume `Config` fields whose meanings are unchanged.

### `README.md`

- Rewrote "Configuration" section for two-file model.
- Removed "State Location" section (no default exists).
- Updated "MCP Client Configuration" to recommend project file + cwd
  walk-up, with env-var fallback.

### `AGENTS.md`

- Updated env-var list, module responsibilities, test counts.

## Tests (TDD)

`test_config.py` grew from 10 to 23 tests:

- Defaults with project file providing `persist_dir`
- Missing `persist_dir` raises
- Global `[embeddings]` overrides defaults
- Global `[chroma]` ignored
- Project `[embeddings]` overrides global `[embeddings]`
- Env overrides both files
- Env provides `persist_dir` without project file
- Project config discovered via cwd walk-up
- No walk-up match + no env → raises
- Relative `persist_dir` resolves to project root
- Relative `ingest.directory` resolves to project root
- Relative path escaping project root raises
- Relative env `persist_dir` without project root raises
- Absolute path works without project file
- `~` expansion in project file
- `~` expansion in env
- `RAG_MCP_CONFIG` missing file raises
- Invalid global TOML raises
- Invalid project TOML raises
- Invalid host raises
- Empty model raises
- Missing ingest directory raises
- `get_config()` caches

## Acceptance criteria

- `pytest` passes (46 tests total).
- `pre-commit run --all-files` passes.
- `python -m rag_mcp.server` with no project file and no relevant env
  vars exits with a clear `ValueError` before `mcp.run()`.
- `python -m rag_mcp.server` with a valid `.rag-mcp.toml` in cwd or an
  ancestor starts normally.
- Relative paths in `.rag-mcp.toml` resolve correctly; escaping paths
  raise.

## Risks / notes

- This is a breaking change. Users relying on the platform-default
  `chroma_data` directory will see the server fail until they create a
  `.rag-mcp.toml` or set `RAG_MCP_CHROMA_PERSIST_DIR`.
- `get_config()` + `get_store()` retain module-level state (the one
  accepted global); factory refactor remains available later.