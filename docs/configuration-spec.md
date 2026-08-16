# Configuration Rework Spec

## Objective

Replace the env-var-only configuration (currently split across `config.py`, `embeddings.py`, and `server.py`) with a consolidated, validated, TOML-file-based system, with `RAG_MCP_*`-prefixed env vars as overrides. Fail fast on invalid config at startup.

## Scope

### In scope

- TOML config file (auto-discovered + `RAG_MCP_CONFIG` override)
- `Config` dataclass + pure `load_config()` + validation
- `RAG_MCP_*` env prefix (clean break from old names)
- Consolidate all config reads into `config.py`; remove `os.environ` access from `embeddings.py` and `server.py`
- Move `store` initialization from import-time to `main()` (eager, fail-fast), with `get_store()` accessor
- Tests (TDD) + README + AGENTS.md updates

### Out of scope

- Full no-globals factory refactor (deferred; pragmatic single-global approach chosen)
- Runtime re-configuration / hot reload
- Config for anything beyond the five settings

## Locked Decisions

| Item | Decision |
|---|---|
| Format | TOML (stdlib `tomllib`, zero deps) |
| Validation | Manual `ValueError`, no pydantic |
| Loading | Eager in `main()` (fail fast), cached via `get_config()` |
| Env names | Clean break: `RAG_MCP_*` only |
| Store init | Eager build in `main()` (not import, not first-request) |
| Typing | `get_store()` returns non-Optional `VectorStore` |
| Ingest dir missing | Fail fast (hard error) |

## Config File

Default location: `platformdirs.user_config_dir("rag-mcp") / "config.toml"`; override with `RAG_MCP_CONFIG`.

```toml
[ollama]
host = "http://localhost:11434"
model = "nomic-embed-text"

[chroma]
persist_dir = ""            # empty → platformdirs user-data default

[ingest]
directory = "~/notes"       # optional
collection = "default"
```

## Env Vars (override the file)

| Var | Config key |
|---|---|
| `RAG_MCP_CONFIG` | explicit config file path |
| `RAG_MCP_OLLAMA_HOST` | `ollama.host` |
| `RAG_MCP_OLLAMA_MODEL` | `ollama.model` |
| `RAG_MCP_CHROMA_PERSIST_DIR` | `chroma.persist_dir` |
| `RAG_MCP_INGEST_DIR` | `ingest.directory` |
| `RAG_MCP_INGEST_COLLECTION` | `ingest.collection` |

**Precedence:** defaults < config file < env vars.

## Validation (fail fast, at `load_config()`)

- `ollama.host` — valid URL, scheme `http`/`https`
- `ollama.model` — non-empty string
- `ingest.collection` — non-empty string
- `ingest.directory` — `~`-expanded; `None` or an **existing** directory (hard error otherwise)
- `chroma.persist_dir` — `~`-expanded; empty → platformdirs default
- Config file: invalid TOML → `ValueError` naming the path; `RAG_MCP_CONFIG` set to a missing file → `ValueError`

## File-by-File Changes

### `src/rag_mcp/config.py` (rewrite)

- `Config` frozen dataclass: `ollama_host`, `ollama_model`, `chroma_persist_dir`, `ingest_dir`, `ingest_collection`.
- `load_config(config_path=None, environ=os.environ) -> Config` — pure: resolve path, parse TOML, overlay env, validate, return.
- `get_config() -> Config` — calls `load_config()` once and caches the result; `main()` calls `get_config()` (not `load_config()` directly) to prime the cache and fail fast.

### `src/rag_mcp/embeddings.py`

- `get_embeddings(texts, host, model)` — explicit params, no `os.environ` access (full decoupling).

### `src/rag_mcp/server.py`

- `mcp = MCPServer("rag-mcp")` stays module-level.
- `store: VectorStore | None = None` placeholder + `get_store() -> VectorStore` (returns non-Optional; raises `RuntimeError("store not initialized")` if unset).
- Tool handlers use `get_store()`; fetch host/model via `get_config()` to call `get_embeddings(...)`.
- `main()`: `config = get_config()` (primes cache, fail fast) → `store = VectorStore(persist_dir=config.chroma_persist_dir)` → auto-ingest if configured → `mcp.run()`.

### `src/rag_mcp/store.py`, `ingest.py`

- Unchanged.

### `README.md`

- Document config file, `RAG_MCP_*` vars, precedence.

### `AGENTS.md`

- Update module responsibilities, env var list, test counts.

## Tests (TDD)

- **`test_config.py`** (rewritten, the meat): defaults; TOML parsing; env-over-file precedence; `~` expansion; `RAG_MCP_CONFIG` → missing file; invalid TOML; invalid host URL; empty model; missing ingest dir; `get_config()` caching (tested by monkeypatching the module-level cache back to `None` between cases).
- **`test_embeddings.py`** (updated): empty input; success passes host/model to `ollama.embed`. Env-override test moves to `test_config.py`.
- **`test_server.py`** (updated): patch `rag_mcp.server.get_store`, `rag_mcp.server.get_embeddings`, and `rag_mcp.server.get_config` (tools fetch host/model through it).

Existing locked tests change, so this needs the same approval-to-modify-tests treatment, RED→GREEN.

## Acceptance Criteria

- `pre-commit run --all-files`, `pytest`, `python -m build` all green.
- Bad config → process exits with a clear error before `mcp.run()`.
- `import rag_mcp.server` is side-effect-free (no ChromaDB, no config load).

## Risks / Notes

- `get_config()` + `get_store()` retain module-level state (the one accepted global); factory refactor remains available later.
- Clean env-name break is safe (project unreleased).

## Execution Order

1. RED — rewrite/extend tests (config, embeddings, server).
2. GREEN — implement `config.py`, `embeddings.py`, `server.py`.
3. Update README + AGENTS.md.
4. Verify: pre-commit + pytest + build.
