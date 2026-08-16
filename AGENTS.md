# Repository Guidelines

## Project Overview

MCP server exposing RAG (Retrieval-Augmented Generation) tools for ingesting document chunks and retrieving relevant context. Embeddings generated via local Ollama instance, vectors persisted in ChromaDB. Communicates over stdio transport using the Model Context Protocol.

## Architecture & Data Flow

```
Client (MCP) → server.py (MCPServer) → get_embeddings() → Ollama API
                                    → VectorStore → ChromaDB
```

**Module responsibilities:**
- `server.py`: MCPServer entry point, defines 5 tools (add_documents, query_documents, list_collections, delete_collection, sync_directory), creates module-level MCPServer and VectorStore instances
- `embeddings.py`: Ollama embedding client, single `get_embeddings()` function with compatibility shim for SDK >=0.4
- `store.py`: ChromaDB wrapper class `VectorStore` with add/query/upsert/get_all_metadata/delete_ids/list_collections/delete_collection operations
- `ingest.py`: directory-to-vector-store sync (`iter_markdown_files`, `chunk_text`, `file_hash`, `sync_directory`). The one module that composes the other two — takes a `VectorStore` instance as a parameter (never a global) so it stays unit-testable
- `__init__.py`: Package marker, empty `__all__`

**Data flow:**
1. Client calls `add_documents` or `query_documents` via MCP stdio
2. `server.py` tool handler calls `get_embeddings()` to generate embeddings
3. `get_embeddings()` calls Ollama API (with env-configurable host/model)
4. For add: embeddings + documents stored in ChromaDB via `VectorStore.add()`
5. For query: embeddings used to search ChromaDB via `VectorStore.query()`, results formatted and returned

**Incremental sync design** (`ingest.sync_directory`): every chunk's metadata carries `source` (relative path), `content_hash` (sha256 of the whole file, identical across all chunks of that file), and `chunk_index`. Chunk IDs are deterministic (`source::chunk_index`), which makes `VectorStore.upsert` idempotent instead of duplicating rows on re-sync. Re-syncing an unchanged file costs zero Ollama calls — the hash comparison short-circuits before chunking/embedding. A file with fewer chunks than before has its orphaned trailing chunk IDs explicitly deleted (upsert alone can't shrink a document's chunk count). Files removed from disk are detected by diffing the sync pass's seen `source` set against everything already in the collection.

No dependency injection framework — direct instantiation with environment variable configuration.

## Key Directories

```
src/rag_mcp/          # Source modules (src-layout)
  server.py           # MCPServer server and tool definitions
  embeddings.py       # Ollama embedding client
  store.py            # ChromaDB vector store wrapper
  ingest.py           # Markdown directory sync
  __init__.py         # Package marker
tests/                # Test suite (flat structure, no classes)
  test_server.py      # 7 tests for MCP tools
  test_embeddings.py  # 3 tests for embedding client
  test_store.py       # 5 tests for vector store
  test_ingest.py      # 6 tests for directory sync
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

**Environment variables:**
- `OLLAMA_HOST` (default: `http://localhost:11434`) — Ollama API endpoint
- `OLLAMA_MODEL` (default: `nomic-embed-text`) — Embedding model name
- `CHROMA_PERSIST_DIR` (default: `./chroma_data`) — ChromaDB persistence directory
- `RAG_INGEST_DIR` (unset by default) — directory auto-ingested at startup via `sync_directory`

Read via `os.environ.get()` with defaults at point of use.

**Error handling:**
- Validation errors raise `ValueError` with descriptive messages (e.g., mismatched list lengths)
- Ollama SDK compatibility: `try/except TypeError` fallback for `host` kwarg removal in SDK >=0.4
- Empty inputs handled with early returns (e.g., `get_embeddings([])` returns `[]`)

**Module-level state:**
- `server.py` creates module-level `mcp = MCPServer("rag-mcp")` and `store = VectorStore(...)` instances
- Tools are decorated with `@mcp.tool()` and reference the module-level `store`
- No global mutable state beyond the server and store singletons
- Auto-ingest (`RAG_INGEST_DIR`) runs inside `main()`, not at module level — module-level execution would fire on every `import rag_mcp.server`, including test imports, silently hitting the filesystem and Ollama during `pytest`

**Testing patterns:**
- Mock external dependencies at module level: `patch("rag_mcp.embeddings.ollama.embed")`, `patch("rag_mcp.server.store")`, `patch("rag_mcp.server.get_embeddings")`
- Use `tmp_path` fixture for ChromaDB filesystem isolation in store and ingest tests
- Inline fixtures, no `conftest.py`
- Flat test structure (functions, not classes)
- Descriptive docstrings explain test intent
- `pytest.raises(ValueError)` for validation errors
- `MagicMock()` for response objects with specific attributes (e.g., `mock_response.embeddings`)
- `test_store.py`/`test_ingest.py` use a real `VectorStore` against `tmp_path` (no Chroma mocking); `test_server.py`/`test_embeddings.py` mock module-level dependencies

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
- `src/rag_mcp/server.py` — MCPServer server, 5 tool definitions, module-level store instance
- `src/rag_mcp/embeddings.py` — `get_embeddings()` with Ollama SDK compatibility shim
- `src/rag_mcp/store.py` — `VectorStore` class wrapping `chromadb.PersistentClient`
- `src/rag_mcp/ingest.py` — `sync_directory()` with deterministic chunk IDs and hash-based incremental re-sync

## Runtime/Tooling Preferences

**Python version:** >=3.10 (uses `list[str]` syntax, not `List[str]`)

**Build system:** setuptools with src-layout. Standard PEP 517/518 packaging.

**Dependencies:**
- Runtime: `mcp`, `ollama`, `chromadb`
- Dev: `pytest`

**Package managers:** Works with `pip`, `pipx`. `uv.lock` exists but is gitignored; on macOS the configured index may lack `onnxruntime` wheels (a transitive `chromadb` dependency) — if `uv sync` fails to resolve, fall back to `venv` + `pip install -e ".[dev]"` rather than fighting the lockfile.

**Prerequisites:**
- Ollama running locally
- Embedding model pulled: `ollama pull nomic-embed-text`

## Testing & QA

**Framework:** pytest

**Test count:** 21 tests total
- `test_embeddings.py`: 3 tests (empty input, success, env override)
- `test_store.py`: 5 tests (add+query, ID generation, validation, lifecycle, empty collection)
- `test_server.py`: 7 tests (add_documents, query_documents happy+empty, list_collections, delete_collection, empty documents, validation)
- `test_ingest.py`: 6 tests (chunking short/long text, first-time sync, noop re-sync, changed-file re-sync, deleted-file re-sync)

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
- Server: `patch("rag_mcp.server.store")` and `patch("rag_mcp.server.get_embeddings")` mock module-level dependencies
- Store/Ingest: Uses real ChromaDB with `tmp_path`, no mocking

**Test contracts are locked:** Tests were committed before implementation (TDD). Do not modify tests to fix implementation bugs — fix the implementation instead.
