"""Markdown directory ingestion: chunking, hashing, and incremental sync into VectorStore."""
import hashlib
from pathlib import Path
from typing import Any

from rag_mcp.embeddings import get_embeddings
from rag_mcp.store import VectorStore

CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200


def iter_markdown_files(directory: str) -> list[Path]:
    """Return all .md/.markdown files under directory, recursively, sorted for determinism."""
    root = Path(directory)
    files = [p for p in root.rglob("*") if p.suffix.lower() in (".md", ".markdown") and p.is_file()]
    return sorted(files)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed-size character split with overlap. Returns [text] unchanged if it already fits."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def file_hash(text: str) -> str:
    """sha256 hex digest of file content, for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sync_directory(store: VectorStore, directory: str, collection: str = "default") -> dict[str, int]:
    """Incrementally sync markdown files under `directory` into `collection`.

    New/changed files are chunked, embedded, and upserted. Unchanged files
    (same content hash) are skipped. Files no longer present on disk have
    their chunks deleted.
    """
    existing = store.get_all_metadata(collection)
    existing_by_source: dict[str, list[dict[str, Any]]] = {}
    for chunk_id, metadata in zip(existing["ids"], existing["metadatas"]):
        existing_by_source.setdefault(metadata["source"], []).append(
            {**metadata, "id": chunk_id}
        )

    counts = {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0}
    seen_sources: set[str] = set()

    staged_ids: list[str] = []
    staged_docs: list[str] = []
    staged_metadatas: list[dict[str, Any]] = []
    ids_to_delete: list[str] = []

    root = Path(directory)
    for path in iter_markdown_files(directory):
        source = str(path.relative_to(root).as_posix())
        seen_sources.add(source)
        text = path.read_text(encoding="utf-8")
        digest = file_hash(text)
        prior_chunks = existing_by_source.get(source, [])
        prior_hash = prior_chunks[0]["content_hash"] if prior_chunks else None

        if prior_hash == digest:
            counts["unchanged"] += 1
            continue

        if not text.strip():
            ids_to_delete.extend(c["id"] for c in prior_chunks)
            counts["updated" if prior_chunks else "added"] += 1
            continue

        new_chunks = chunk_text(text)
        for i, chunk in enumerate(new_chunks):
            staged_ids.append(f"{source}::{i}")
            staged_docs.append(chunk)
            staged_metadatas.append({"source": source, "content_hash": digest, "chunk_index": i})

        if len(new_chunks) < len(prior_chunks):
            ids_to_delete.extend(
                c["id"] for c in prior_chunks if c["chunk_index"] >= len(new_chunks)
            )

        counts["updated" if prior_chunks else "added"] += 1

    for source, chunks in existing_by_source.items():
        if source not in seen_sources:
            ids_to_delete.extend(c["id"] for c in chunks)
            counts["deleted"] += 1

    if staged_ids:
        embeddings = get_embeddings(staged_docs)
        store.upsert(
            collection=collection,
            documents=staged_docs,
            embeddings=embeddings,
            ids=staged_ids,
            metadatas=staged_metadatas,
        )
    store.delete_ids(collection, ids_to_delete)

    return counts
