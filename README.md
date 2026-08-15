# rag-mcp

An MCP server that exposes tools for ingesting document chunks and retrieving relevant context for RAG (Retrieval-Augmented Generation). Embeddings are generated via a local [Ollama](https://ollama.com) instance, and vectors are persisted in [ChromaDB](https://www.trychroma.com/).

## Prerequisites

- Python >= 3.10
- [Ollama](https://ollama.com) running locally
- The embedding model pulled: `ollama pull nomic-embed-text`

## Installation

### Development

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### End-user (pipx)

```bash
pipx install .
```

This makes the `rag-mcp` command available globally in an isolated virtual environment.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `nomic-embed-text` | Embedding model name |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `RAG_INGEST_DIR` | unset (skip startup sync) | Directory of markdown files to auto-sync on server startup |
| `RAG_INGEST_COLLECTION` | `default` | Collection to sync `RAG_INGEST_DIR` into |

## MCP Client Configuration

Add to your MCP client config (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rag": {
      "command": "rag-mcp"
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

Incrementally sync a directory of markdown files into a collection. Safe to call repeatedly: new and changed files are chunked and (re-)embedded, unchanged files are skipped, and files removed from disk have their chunks removed from the collection. Setting `RAG_INGEST_DIR` also runs this automatically on server startup.

**Parameters:**
- `directory` (str) — path to the directory of `.md`/`.markdown` files to sync
- `collection` (str, default `"default"`) — target collection name

## Development

```bash
pytest            # run tests
```
