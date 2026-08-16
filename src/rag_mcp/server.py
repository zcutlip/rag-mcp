"""MCP server exposing RAG tools backed by Ollama embeddings and ChromaDB."""
from typing import Any

from mcp.server.mcpserver import MCPServer

import rag_mcp.ingest as ingest
from rag_mcp.config import get_config
from rag_mcp.embeddings import get_embeddings
from rag_mcp.store import VectorStore

mcp = MCPServer("rag-mcp")
store: VectorStore | None = None


def get_store() -> VectorStore:
    """Return the initialized store, raising if ``main()`` has not run yet."""
    if store is None:
        raise RuntimeError("store not initialized")
    return store


@mcp.tool()
def add_documents(
    documents: list[str],
    ids: list[str] | None = None,
    metadatas: list[dict[str, Any]] | None = None,
    collection: str = "default",
) -> str:
    """Add document chunks to a collection. Markdown text is accepted as-is."""
    if not documents:
        return f"Added 0 document(s) to collection '{collection}'."

    if ids is not None and len(ids) != len(documents):
        raise ValueError("ids must have the same length as documents")
    if metadatas is not None and len(metadatas) != len(documents):
        raise ValueError("metadatas must have the same length as documents")

    cfg = get_config()
    embeddings = get_embeddings(documents, cfg.ollama_host, cfg.ollama_model)
    get_store().add(
        collection=collection,
        documents=documents,
        embeddings=embeddings,
        ids=ids,
        metadatas=metadatas,
    )
    return f"Added {len(documents)} document(s) to collection '{collection}'."


@mcp.tool()
def query_documents(query: str, n_results: int = 5, collection: str = "default") -> str:
    """Retrieve the most relevant document chunks for a query."""
    if n_results < 1:
        raise ValueError("n_results must be >= 1")

    cfg = get_config()
    query_embedding = get_embeddings([query], cfg.ollama_host, cfg.ollama_model)[0]
    results = get_store().query(
        collection=collection,
        query_embedding=query_embedding,
        n_results=n_results,
    )

    documents = results.get("documents", [[]])[0]
    if not documents:
        return "No matching documents found."

    ids = results["ids"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]

    lines: list[str] = []
    for i, (doc_id, distance, document, metadata) in enumerate(
        zip(ids, distances, documents, metadatas)
    ):
        lines.append(f"Rank {i + 1} (distance: {distance:.4f})")
        lines.append(f"ID: {doc_id}")
        lines.append(document)
        lines.append(f"Metadata: {metadata}")
        lines.append("---")
    return "\n".join(lines)


@mcp.tool()
def list_collections() -> list[str]:
    """List all collection names in the vector store."""
    return get_store().list_collections()


@mcp.tool()
def delete_collection(collection: str = "default") -> str:
    """Delete a collection from the vector store."""
    s = get_store()
    if collection not in s.list_collections():
        raise ValueError(f"Collection '{collection}' does not exist.")
    s.delete_collection(collection)
    return f"Deleted collection '{collection}'."


@mcp.tool()
def sync_directory(directory: str, collection: str = "default") -> str:
    """Sync a directory of markdown files into a collection.

    Adds new/changed files, removes deleted ones.
    """
    result = ingest.sync_directory(get_store(), directory, collection=collection)
    return (
        f"Synced '{directory}' into collection '{collection}': "
        f"{result['added']} added, {result['updated']} updated, "
        f"{result['deleted']} deleted, {result['unchanged']} unchanged."
    )


def main() -> None:
    """Run the MCP server using stdio transport."""
    global store
    config = get_config()
    store = VectorStore(persist_dir=config.chroma_persist_dir)
    if config.ingest_dir:
        ingest.sync_directory(
            store, config.ingest_dir, collection=config.ingest_collection
        )
    mcp.run()


if __name__ == "__main__":
    main()
