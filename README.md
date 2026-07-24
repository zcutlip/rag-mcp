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

## Development

```bash
pytest            # run tests
```
