# Repository Guidelines

## Project Overview

MCP server exposing RAG (Retrieval-Augmented Generation) tools for ingesting document chunks and retrieving relevant context. Embeddings generated via local Ollama instance, vectors persisted in ChromaDB. Communicates over stdio transport using the Model Context Protocol.

## Architecture & Data Flow

```
Client (MCP) → server.py (MCPServer) → get_embeddings() → Ollama API
                                    → VectorStore → ChromaDB
```

**Module responsibilities:**
- `config.py`: `Config` frozen dataclass plus `load_config()`/`get_config()`. Loads a TOML config file with `RAG_MCP_*` env overrides and validates eagerly (fail fast)
- `server.py`: MCPServer entry point, defines 5 tools (add_documents, query_documents, list_collections, delete_collection, sync_directory); module-level `mcp` plus a lazy `store` built in `main()` and accessed via `get_store()`
- `embeddings.py`: Ollama embedding client, `get_embeddings(texts, host, model)` with compatibility shim for SDK >=0.4 (host/model passed in, no `os.environ` access)
- `store.py`: ChromaDB wrapper class `VectorStore` with add/query/upsert/get_all_metadata/delete_ids/list_collections/delete_collection operations
- `ingest.py`: directory-to-vector-store sync (`iter_markdown_files`, `chunk_text`, `file_hash`, `sync_directory`). The one module that composes the other two — takes a `VectorStore` instance as a parameter (never a global) so it stays unit-testable
- `__init__.py`: Package marker, exports `__version__`

**Data flow:**
1. `main()` loads config via `get_config()` (fail fast) and builds the `VectorStore` from `chroma_persist_dir`
2. Client calls `add_documents` or `query_documents` via MCP stdio
3. Tool handler fetches `ollama_host`/`ollama_model` from `get_config()` and calls `get_embeddings()`
4. `get_embeddings()` calls Ollama API with the given host/model
5. For add: embeddings + documents stored in ChromaDB via `VectorStore.add()`
6. For query: embeddings used to search ChromaDB via `VectorStore.query()`, results formatted and returned

**Incremental sync design** (`ingest.sync_directory`): every chunk's metadata carries `source` (relative path), `content_hash` (sha256 of the whole file, identical across all chunks of that file), and `chunk_index`. Chunk IDs are deterministic (`source::chunk_index`), which makes `VectorStore.upsert` idempotent instead of duplicating rows on re-sync. Re-syncing an unchanged file costs zero Ollama calls — the hash comparison short-circuits before chunking/embedding. A file with fewer chunks than before has its orphaned trailing chunk IDs explicitly deleted (upsert alone can't shrink a document's chunk count). Files removed from disk are detected by diffing the sync pass's seen `source` set against everything already in the collection.

No dependency injection framework — direct instantiation with TOML + env configuration loaded by `config.py`.

## Key Directories

```
src/rag_mcp/          # Source modules (src-layout)
  config.py           # TOML + env configuration, validation
  server.py           # MCPServer server and tool definitions
  embeddings.py       # Ollama embedding client
  store.py            # ChromaDB vector store wrapper
  ingest.py           # Markdown directory sync
  __init__.py         # Package marker (exports __version__)
tests/                # Test suite (flat structure, no classes)
  test_config.py      # 10 tests for configuration loading
  test_server.py      # 9 tests for MCP tools
  test_embeddings.py  # 2 tests for embedding client
  test_store.py       # 5 tests for vector store
  test_ingest.py      # 6 tests for directory sync
  test_version.py     # 1 test for package version
docs/                 # Current specs
docs/archive/         # Completed/superseded specs, named YYYY-MM-DD-<topic>-spec.md
```

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Lint/format (pre-commit hooks: flake8, autopep8, isort, pyupgrade, shellcheck)
pre-commit run --all-files

# Run server manually
rag-mcp                          # via installed entry point
python -m rag_mcp.server         # via module

# Production install (isolated)
pipx install .
```

## Code Conventions & Common Patterns

**Type hints:** Full type annotations on all function signatures. Use `list[str]` not `List[str]` (Python 3.10+). Return types explicit.

**Configuration:** Loaded by `config.py` from a TOML file with `RAG_MCP_*` env overrides. Precedence: defaults < config file < env vars.

Environment variables (all optional, override the config file):
- `RAG_MCP_CONFIG` — explicit config file path (default: `platformdirs.user_config_dir("rag-mcp")/config.toml`)
- `RAG_MCP_OLLAMA_HOST` (default: `http://localhost:11434`) — Ollama API endpoint
- `RAG_MCP_OLLAMA_MODEL` (default: `nomic-embed-text`) — Embedding model name
- `RAG_MCP_CHROMA_PERSIST_DIR` (default: platform user-data dir) — ChromaDB persistence directory
- `RAG_MCP_INGEST_DIR` (unset by default) — directory auto-ingested at startup via `sync_directory`
- `RAG_MCP_INGEST_COLLECTION` (default: `default`) — collection for the startup auto-ingest

TOML keys mirror the vars: `[ollama] host`/`model`, `[chroma] persist_dir`, `[ingest] directory`/`collection`.

**Error handling:**
- Validation errors raise `ValueError` with descriptive messages (e.g., mismatched list lengths)
- Ollama SDK compatibility: `try/except TypeError` fallback for `host` kwarg removal in SDK >=0.4
- Empty inputs handled with early returns (e.g., `get_embeddings([])` returns `[]`)

**Module-level state:**
- `server.py` creates a module-level `mcp = MCPServer("rag-mcp")`; `store` is a `None` placeholder built in `main()` and accessed via `get_store()` (raises `RuntimeError` if unset)
- `config.py` caches a `Config` singleton via `get_config()` (loaded once, fail fast)
- Tools are decorated with `@mcp.tool()` and reference `get_store()`/`get_config()`
- Auto-ingest (`ingest.directory`/`RAG_MCP_INGEST_DIR`) runs inside `main()`, not at module level — module-level execution would fire on every `import rag_mcp.server`, including test imports, silently hitting the filesystem and Ollama during `pytest`

**Testing patterns:**
- Mock external dependencies at module level: `patch("rag_mcp.embeddings.ollama.embed")`, `patch("rag_mcp.server.get_store")`, `patch("rag_mcp.server.get_config")`, `patch("rag_mcp.server.get_embeddings")`
- Use `tmp_path` fixture for ChromaDB filesystem isolation in store and ingest tests
- Inline fixtures, no `conftest.py`
- Flat test structure (functions, not classes)
- Descriptive docstrings explain test intent
- `pytest.raises(ValueError)` for validation errors
- `MagicMock()` for response objects with specific attributes (e.g., `mock_response.embeddings`)
- `test_store.py`/`test_ingest.py` use a real `VectorStore` against `tmp_path` (no Chroma mocking); `test_config.py` passes an explicit `environ` mapping; `test_server.py`/`test_embeddings.py` mock module-level dependencies

**Naming:**
- snake_case for functions and variables
- PascalCase for classes (`VectorStore`)
- Test names: `test_<module>_<behavior>` (e.g., `test_get_embeddings_empty_input`)

## Important Files

**Entry points:**
- `src/rag_mcp/server.py:main()` — CLI entry point, calls `mcp.run()` for stdio transport
- Console script: `rag-mcp` → `rag_mcp.server:main` (defined in `pyproject.toml`)

**Configuration:**
- `pyproject.toml` — Single source of truth for package metadata, dependencies, build system, entry points, pytest config
- `.gitignore` — Excludes .venv, __pycache__, build artifacts, chroma_data/, .pytest_cache/, uv.lock
- `.pre-commit-config.yaml` — Lint/format hooks (flake8, autopep8, isort, pyupgrade, shellcheck)

**Key modules:**
- `src/rag_mcp/config.py` — `Config` dataclass, `load_config()`/`get_config()` with TOML + env validation
- `src/rag_mcp/server.py` — MCPServer server, 5 tool definitions, `get_store()`/`get_config()` wiring
- `src/rag_mcp/embeddings.py` — `get_embeddings(texts, host, model)` with Ollama SDK compatibility shim
- `src/rag_mcp/store.py` — `VectorStore` class wrapping `chromadb.PersistentClient`
- `src/rag_mcp/ingest.py` — `sync_directory()` with deterministic chunk IDs and hash-based incremental re-sync

## Runtime/Tooling Preferences

**Python version:** >=3.12 (uses `list[str]` syntax and stdlib `tomllib`)

**Build system:** setuptools with src-layout. Standard PEP 517/518 packaging.

**Dependencies:**
- Runtime: `mcp`, `ollama`, `chromadb`, `platformdirs`
- Dev: `pytest`

**Package managers:** Works with `pip`, `pipx`. `uv.lock` exists but is gitignored; on macOS the configured index may lack `onnxruntime` wheels (a transitive `chromadb` dependency) — if `uv sync` fails to resolve, fall back to `venv` + `pip install -e ".[dev]"` rather than fighting the lockfile.

**Prerequisites:**
- Ollama running locally
- Embedding model pulled: `ollama pull nomic-embed-text`

## Testing & QA

**Framework:** pytest

**Test count:** 33 tests total
- `test_config.py`: 10 tests (defaults, TOML parsing, env-over-file precedence, `~` expansion, missing/invalid config file, invalid host/model, missing ingest dir, `get_config()` caching)
- `test_embeddings.py`: 2 tests (empty input, success passes host/model)
- `test_store.py`: 5 tests (add+query, ID generation, validation, lifecycle, empty collection)
- `test_server.py`: 9 tests (add_documents, query_documents happy+empty, list_collections, delete_collection, empty documents, validation)
- `test_ingest.py`: 6 tests (chunking short/long text, first-time sync, noop re-sync, changed-file re-sync, deleted-file re-sync)
- `test_version.py`: 1 test (semver format)

**Test isolation:**
- External dependencies mocked at module level
- ChromaDB uses `tmp_path` for filesystem isolation (no shared state between tests)
- No test interdependencies

**Running tests:**
```bash
pytest                    # run all tests
pytest -v                 # verbose output
pytest tests/test_server.py  # run specific module
```

**Coverage expectations:** Tests enforce contracts around:
- Input validation (mismatched list lengths raise `ValueError`)
- Empty input handling (early returns, no external calls)
- Default behavior vs environment variable overrides
- Auto-generated IDs (UUID strings, unique)
- Collection lifecycle (create, list, delete)
- Query results (ranking, metadata, distances)
- Incremental sync (idempotent re-sync, changed/deleted file detection)

**Mocking strategy:**
- Embeddings: `patch("rag_mcp.embeddings.ollama.embed")` returns `MagicMock` with `.embeddings` attribute
- Server: `patch("rag_mcp.server.get_store")`, `patch("rag_mcp.server.get_embeddings")`, and `patch("rag_mcp.server.get_config")` mock module-level dependencies
- Config: `load_config()` accepts an explicit `environ` mapping; `test_config.py` passes one instead of mutating `os.environ`
- Store/Ingest: Uses real ChromaDB with `tmp_path`, no mocking

**Test contracts are locked:** Tests were committed before implementation (TDD). Do not modify tests to fix implementation bugs — fix the implementation instead.
