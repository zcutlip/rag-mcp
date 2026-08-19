# rag-mcp

[![CI](https://github.com/zcutlip/rag-mcp/workflows/CI/badge.svg)](https://github.com/zcutlip/rag-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that exposes tools for ingesting document chunks and retrieving relevant context for RAG (Retrieval-Augmented Generation). Embeddings are generated via a local [Ollama](https://ollama.com) instance, and vectors are persisted in [ChromaDB](https://www.trychroma.com/).

## Prerequisites

- Python >= 3.12
- [Ollama](https://ollama.com) running locally
- The embedding model pulled: `ollama pull nomic-embed-text`

## Getting Started

### For Agents

Copy-paste this prompt to set up `rag-mcp` in a project:

```markdown
Set up the `rag-mcp` MCP server for this project:

1. Install `rag-mcp`: pipx install git+https://github.com/zcutlip/rag-mcp.git
2. From the project root, run `rag-mcp-config init` early — prefer it over hand-crafting config files.
3. Run `rag-mcp readme` and follow the README's remaining setup and client-specific guidance.
4. Offer to edit the project-local .rag-mcp.toml config file for the user.
5. Verify or reload the MCP connection.
6. Suggest to the user a few questions they can ask of the agent to tell if the rag-mcp server is functioning.

> Note: the README and the `rag://readme` resource are server setup documentation, not corpus content. For questions about the indexed corpus, use the `query_documents` tool.
```

Or if you prefer to drive yourself follow these instructions...

### For Humans

1. Meet the prerequisites: Python 3.12+, [Ollama](https://ollama.com) running locally, and the embedding model pulled (`ollama pull nomic-embed-text`).
2. Install `rag-mcp` (see [Installation](#installation)).
3. From the project root, run `rag-mcp-config init` to generate starter config files.
4. Add `.chroma/` (or your chosen `persist_dir`) to `.gitignore`.
5. Configure your coding agent (see [MCP Client Configuration](#mcp-client-configuration)).
6. Restart and verify the MCP connection.

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
[embeddings]
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
| `RAG_MCP_EMBEDDINGS_HOST` | `http://localhost:11434` | Embedding provider API endpoint |
| `RAG_MCP_EMBEDDINGS_MODEL` | `nomic-embed-text` | Embedding model name |
| `RAG_MCP_CHROMA_PERSIST_DIR` | required | ChromaDB persistence directory |
| `RAG_MCP_INGEST_DIR` | unset (skip startup sync) | Directory of markdown files to auto-sync on server startup |
| `RAG_MCP_INGEST_COLLECTION` | `default` | Collection to sync `RAG_MCP_INGEST_DIR` into |

## Initialize a starter config

The `rag-mcp-config` utility writes starter config files for both global and project-local settings:

```bash
rag-mcp-config init
```

This creates:
- **Global config** at the platform default location (e.g., `~/.config/rag-mcp/config.toml` on Linux) with `[embeddings]` defaults
- **Project config** at `<cwd>/.rag-mcp.toml` with `[chroma]` and `[ingest]` templates (including commented examples)

If either file already exists, it's skipped with a note. The command is idempotent — safe to run multiple times.

The command reports each path it writes or skips. `rag-mcp --help` prints server
usage without loading configuration or starting the MCP server. If startup
configuration is missing or invalid, `rag-mcp` reports the error on stderr and
suggests running `rag-mcp-config init`.

To give an MCP client or coding agent the project guidance directly, run:

```bash
rag-mcp readme
```

This prints the README and exits without loading configuration or starting the
MCP server.

## Server Metadata and Resources

The MCP server exposes metadata and a self-documentation resource to help agents discover and use it effectively:

- **Server instructions** guide agents toward `query_documents` for corpus questions
- **`rag://readme` resource** provides the full README for agents to read at runtime
- **Tool descriptions** explicitly identify `query_documents` as the primary tool for answering questions about the indexed corpus

When an agent connects to `rag-mcp`, it can:
1. Read server instructions to understand the server's purpose
2. List resources to discover `rag://readme`
3. Read the README resource for detailed usage guidance
4. Use `query_documents` to answer questions about the corpus

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
- `compact` (bool, default `true`) — if true, return minimal metadata per hit; if false, include full metadata

**Response format:**

Returns a structured dict with `results` and `sources` fields:

```json
{
  "results": [
    {
      "rank": 1,
      "content": "document chunk text",
      "distance": 0.123,
      "metadata": {
        "source": "path/to/file.md",
        "chunk_index": 0,
        "content_hash": "abc123"
      }
    }
  ],
  "sources": {
    "path/to/file.md": {
      "title": "Document Title",
      "url": "https://example.com",
      "tags": ["tag1", "tag2"],
      "created": "2024-01-01",
      "updated": "2024-06-01"
    }
  }
}
```

The `sources` dictionary contains deduplicated metadata from YAML frontmatter, keyed by source path. When `compact=false`, each result's `metadata` field includes the full frontmatter fields.

**YAML frontmatter support:**

Markdown files can include YAML frontmatter that will be parsed and stored as metadata:

```markdown
---
title: Document Title
url: https://example.com
tags:
  - tag1
  - tag2
created: 2024-01-01
updated: 2024-06-01
---

# Document content here
```

Supported frontmatter fields: `title`, `url`, `tags`, `created`, `updated`. The frontmatter is stripped before chunking and embedding, so it doesn't appear in the document content.

### `list_collections`

List all collection names in the vector store.

### `delete_collection`

Delete a collection and all its documents.

**Parameters:**
- `collection` (str, default `"default"`) — collection to delete

### `sync_directory`

Incrementally sync a directory of markdown files into a collection. Safe to call repeatedly: new and changed files are chunked and (re-)embedded, unchanged files are skipped, and files removed from disk have their chunks removed from the collection. Setting `RAG_MCP_INGEST_DIR` (or `[ingest] directory` in `.rag-mcp.toml`) also runs this automatically on server startup.

**Parameters:**
- `directory` (str) — path to the directory of `.md`/`.markdown` files to sync (see FAQ)
- `collection` (str, default `"default"`) — target collection name

## Development

```bash
pytest            # run tests
```

## FAQ

### What file types can I index?

Directory sync (`sync_directory` and `RAG_MCP_INGEST_DIR` auto-ingest) indexes Markdown only — `.md` and `.markdown`, recursively.

Text-like files (.txt/.rst/.mdx) would be trivial — binary types like PDF/DOCX need a text-extraction dependency and a small ingest redesign. Native extractors are doable and under consideration. They would likely be behind an opt-in dependency so the base install stays lean.

## License

[MIT](LICENSE) © 2026 Zachary Cutlip
