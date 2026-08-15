"""ChromaDB-backed vector store for the RAG MCP server."""
import uuid
from typing import Any

import chromadb


class VectorStore:
    """Persistent ChromaDB vector store."""

    def __init__(self, persist_dir: str) -> None:
        self._client = chromadb.PersistentClient(path=persist_dir)

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(name=name)

    def add(
        self,
        collection: str,
        documents: list[str],
        embeddings: list[list[float]],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        if ids is not None and len(ids) != len(documents):
            raise ValueError("ids must have the same length as documents")
        if metadatas is not None and len(metadatas) != len(documents):
            raise ValueError("metadatas must have the same length as documents")

        ids = ids or [str(uuid.uuid4()) for _ in documents]
        coll = self.get_or_create_collection(collection)
        coll.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        collection: str,
        query_embedding: list[float],
        n_results: int,
    ) -> dict[str, Any]:
        coll = self.get_or_create_collection(collection)
        return coll.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "distances", "metadatas"],
        )

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]

    def delete_collection(self, name: str) -> None:
        self._client.delete_collection(name)

    def get_all_metadata(self, collection: str) -> dict[str, Any]:
        coll = self.get_or_create_collection(collection)
        result = coll.get(include=["metadatas"])
        return {"ids": result["ids"], "metadatas": result["metadatas"]}

    def upsert(
        self,
        collection: str,
        documents: list[str],
        embeddings: list[list[float]],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        if len(ids) != len(documents):
            raise ValueError("ids must have the same length as documents")
        if metadatas is not None and len(metadatas) != len(documents):
            raise ValueError("metadatas must have the same length as documents")

        coll = self.get_or_create_collection(collection)
        coll.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_ids(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        coll = self.get_or_create_collection(collection)
        coll.delete(ids=ids)
