"""Markdown directory ingestion: chunking, hashing, and incremental sync into VectorStore."""
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from rag_mcp.embeddings import get_embeddings
from rag_mcp.store import VectorStore

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n?---\s*\n', re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown text.

    Returns the frontmatter dict.
    If no frontmatter is found or YAML is invalid, returns {}.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}

    yaml_content = match.group(1)
    try:
        data = yaml.safe_load(yaml_content)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        # Invalid YAML - return empty dict
        return {}


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown text.

    Returns the text without the frontmatter block.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return text
    return text[match.end():]


def _serialize_metadata_value(value: Any) -> Any:
    """Serialize a metadata value for Chroma storage.

    Chroma requires metadata values to be strings, ints, floats, or bools.
    Lists and dicts are JSON-encoded. Dates are converted to ISO strings.
    """
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    elif isinstance(value, (list, dict)):
        return json.dumps(value)
    else:
        return value


def _serialize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Serialize all metadata values for Chroma storage."""
    return {k: _serialize_metadata_value(v) for k, v in metadata.items()}


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


def sync_directory(
    store: VectorStore,
    directory: str,
    collection: str = "default",
    *,
    embeddings_host: str,
    embeddings_model: str,
) -> dict[str, int]:
    """Incrementally sync markdown files under `directory` into `collection`.

    New/changed files are chunked, embedded, and upserted. Unchanged files
    (same content hash) are skipped. Files no longer present on disk have
    their chunks deleted.

    Frontmatter is stripped before chunking and stored as metadata.
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
        raw_text = path.read_text(encoding="utf-8")

        # Parse and strip frontmatter
        frontmatter = parse_frontmatter(raw_text)
        stripped_text = strip_frontmatter(raw_text)

        # Hash the stripped content (not raw)
        digest = file_hash(stripped_text)
        prior_chunks = existing_by_source.get(source, [])
        prior_hash = prior_chunks[0]["content_hash"] if prior_chunks else None

        # Check if we need to re-index (hash changed OR frontmatter metadata missing)
        needs_reindex = (prior_hash != digest)
        if not needs_reindex and prior_chunks:
            # Check if any chunk is missing frontmatter metadata (migration case)
            has_frontmatter = bool(frontmatter)  # Current file has frontmatter
            chunks_have_frontmatter = any(
                "title" in chunk or "url" in chunk or "tags" in chunk
                for chunk in prior_chunks
            )
            if has_frontmatter and not chunks_have_frontmatter:
                needs_reindex = True

        if not needs_reindex:
            counts["unchanged"] += 1
            continue

        if not stripped_text.strip():
            ids_to_delete.extend(c["id"] for c in prior_chunks)
            counts["updated" if prior_chunks else "added"] += 1
            continue

        # Serialize frontmatter for Chroma
        serialized_frontmatter = _serialize_metadata(frontmatter)

        new_chunks = chunk_text(stripped_text)
        for i, chunk in enumerate(new_chunks):
            staged_ids.append(f"{source}::{i}")
            staged_docs.append(chunk)
            # Base metadata + frontmatter
            chunk_metadata = {
                "source": source,
                "content_hash": digest,
                "chunk_index": i,
                **serialized_frontmatter,
            }
            staged_metadatas.append(chunk_metadata)

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
        embeddings = get_embeddings(staged_docs, embeddings_host, embeddings_model)
        store.upsert(
            collection=collection,
            documents=staged_docs,
            embeddings=embeddings,
            ids=staged_ids,
            metadatas=staged_metadatas,
        )
    store.delete_ids(collection, ids_to_delete)

    return counts
