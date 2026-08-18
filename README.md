# rag-mcp

[![CI](https://github.com/zcutlip/rag-mcp/workflows/CI/badge.svg)](https://github.com/zcutlip/rag-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that exposes tools for ingesting document chunks and retrieving relevant context for RAG (Retrieval-Augmented Generation). Embeddings are generated via a local [Ollama](https://ollama.com) instance, and vectors are persisted in [ChromaDB](https://www.trychroma.com/).

## Prerequisites

- Python >= 3.12
- [Ollama](https://ollama.com) running locally
- The embedding model pulled: `ollama pull nomic-embed-text`

## Installation

### End-user (pipx)

```bash
pipx install git+https://github.com/zcutlip/rag-mcp.git
```

This installs `rag-mcp` into an isolated virtual environment and makes the command available globally. If you don't use pipx:

```bash
pip install git+https://github.com/zcutlip/rag-mcp.git
```

Once the package is published to PyPI, it can be installed directly with `pipx install rag-mcp`.

### Development

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Configuration

Configuration is loaded from two files with `RAG_MCP_*` environment variables
as overrides. Precedence: defaults < global file < project file < env vars.

### Global config (`config.toml`)

Holds machine-level Ollama defaults only. Located at
`platformdirs.user_config_dir("rag-mcp") / "config.toml"`, e.g.
`~/Library/Application Support/rag-mcp/config.toml` on macOS or
`~/.config/rag-mcp/config.toml` on Linux. Override with `RAG_MCP_CONFIG`.

```toml
[ollama]
host = "http://localhost:11434"
model = "nomic-embed-text"
```

### Project config (`.rag-mcp.toml`)

Holds project-local data settings. Discovered by walking up from the current
working directory. Commit this file in your repo for portability:

```toml
[chroma]
persist_dir = "./.chroma"

[ingest]
directory = "./docs"
collection = "default"
```

Relative paths in the project file resolve against the directory containing
`.rag-mcp.toml` (the project root) and must stay within it. Add `.chroma/`
(or whatever you chose) to `.gitignore`.

### Environment variables

All env vars are optional overrides. `chroma.persist_dir` is required and
must be set in `.rag-mcp.toml` or via `RAG_MCP_CHROMA_PERSIST_DIR`.

| Variable | Default | Description |
|---|---|---|
| `RAG_MCP_CONFIG` | platform config dir | Explicit global config file path |
| `RAG_MCP_OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `RAG_MCP_OLLAMA_MODEL` | `nomic-embed-text` | Embedding model name |
| `RAG_MCP_CHROMA_PERSIST_DIR` | required | ChromaDB persistence directory |
| `RAG_MCP_INGEST_DIR` | unset (skip startup sync) | Directory of markdown files to auto-sync on server startup |
| `RAG_MCP_INGEST_COLLECTION` | `default` | Collection to sync `RAG_MCP_INGEST_DIR` into |

## MCP Client Configuration

Register `rag-mcp` as a server in your MCP client. The recommended setup
is to commit a `.rag-mcp.toml` in each project and have the client launch
the server from the project root so cwd-walk-up finds it.

**Claude Code** — project-scoped `.mcp.json` in the repo root:

```json
{
  "mcpServers": {
    "rag": {
      "command": "rag-mcp"
    }
  }
}
```

**OpenCode** — `opencode.json` (or `.jsonc`):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "rag": {
      "type": "local",
      "command": ["rag-mcp"],
      "cwd": "."
    }
  }
}
```

If your client doesn't launch from the project root, or you can't use
`.rag-mcp.toml`, set `RAG_MCP_*` env vars explicitly:

```json
{
  "mcpServers": {
    "rag": {
      "command": "rag-mcp",
      "env": {
        "RAG_MCP_CHROMA_PERSIST_DIR": "/abs/path/to/project/.chroma",
        "RAG_MCP_INGEST_DIR": "/abs/path/to/project/docs"
      }
    }
  }
}
```

## Tools

### `add_documents`

Add document chunks to a collection. Accepts markdown text as-is.

**Parameters:**
- `documents` (list[str]) — document text chunks
- `ids` (list[str], optional) — explicit IDs; auto-generated if omitted
- `metadatas` (list[dict], optional) — metadata per document
- `collection` (str, default `"default"`) — target collection name

### `query_documents`

Retrieve the most relevant document chunks for a query string.

**Parameters:**
- `query` (str) — the search query
- `n_results` (int, default `5`) — number of results to return
- `collection` (str, default `"default"`) — collection to search

### `list_collections`

List all collection names in the vector store.

### `delete_collection`

Delete a collection and all its documents.

**Parameters:**
- `collection` (str, default `"default"`) — collection to delete

### `sync_directory`

Incrementally sync a directory of markdown files into a collection. Safe to call repeatedly: new and changed files are chunked and (re-)embedded, unchanged files are skipped, and files removed from disk have their chunks removed from the collection. Setting `RAG_MCP_INGEST_DIR` (or `[ingest] directory` in `.rag-mcp.toml`) also runs this automatically on server startup.

**Parameters:**
- `directory` (str) — path to the directory of `.md`/`.markdown` files to sync
- `collection` (str, default `"default"`) — target collection name

## Development

```bash
pytest            # run tests
```

## License

[MIT](LICENSE) © 2026 Zachary Cutlip

