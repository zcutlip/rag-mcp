"""Tests for frontmatter parsing and stripping during markdown ingestion."""
import json
from unittest.mock import patch

from rag_mcp.ingest import (file_hash, parse_frontmatter, strip_frontmatter,
                            sync_directory)
from rag_mcp.store import VectorStore

EMBEDDINGS_HOST = "http://localhost:11434"
EMBEDDINGS_MODEL = "nomic-embed-text"


def _fake_embeddings(texts, host, model):
    return [[0.1, 0.2] for _ in texts]


# --- parse_frontmatter / strip_frontmatter unit tests ---


def test_parse_frontmatter_extracts_fields():
    """parse_frontmatter returns YAML frontmatter fields as a dict."""
    text = "---\ntitle: My Doc\ntags: [a, b]\n---\nbody"
    assert parse_frontmatter(text) == {"title": "My Doc", "tags": ["a", "b"]}


def test_parse_frontmatter_empty_without_block():
    """parse_frontmatter returns {} when the text has no frontmatter block."""
    assert parse_frontmatter("just body text") == {}


def test_strip_frontmatter_removes_block():
    """strip_frontmatter removes the YAML block and the following newline."""
    text = "---\ntitle: My Doc\n---\nbody text"
    assert strip_frontmatter(text) == "body text"


def test_strip_frontmatter_unchanged_without_block():
    """strip_frontmatter returns the text unchanged when no frontmatter exists."""
    text = "just body text"
    assert strip_frontmatter(text) == text


# --- sync_directory integration tests ---


def test_sync_strips_frontmatter_before_chunking(tmp_path):
    """Chunks embedded during sync exclude the YAML frontmatter block."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text(
        "---\ntitle: Test Doc\nurl: https://example.com\n---\nhello world"
    )

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    chunk = mock_emb.call_args.args[0][0]
    assert "title" not in chunk
    assert "Test Doc" not in chunk
    assert "hello world" in chunk


def test_sync_stores_frontmatter_metadata(tmp_path):
    """Frontmatter fields are stored as chunk metadata in Chroma."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text(
        "---\ntitle: Test Doc\nurl: https://example.com\n---\nhello world"
    )

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    meta = store.get_all_metadata("test")["metadatas"][0]
    assert meta["title"] == "Test Doc"
    assert meta["url"] == "https://example.com"


def test_sync_handles_no_frontmatter(tmp_path):
    """Files without frontmatter sync normally and carry no frontmatter metadata."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert result == {"added": 1, "updated": 0, "deleted": 0, "unchanged": 0}
    mock_emb.assert_called_once_with(["hello world"], EMBEDDINGS_HOST, EMBEDDINGS_MODEL)
    meta = store.get_all_metadata("test")["metadatas"][0]
    assert meta["source"] == "a.md"
    assert "title" not in meta


def test_sync_migration_adds_frontmatter(tmp_path):
    """Chunks stored before frontmatter support are re-indexed with frontmatter metadata."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    md_file = docs_dir / "a.md"
    md_file.write_text("---\ntitle: Old Doc\n---\nhello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    # Simulate a pre-frontmatter sync: hash over the raw file, no frontmatter metadata
    old_hash = file_hash(md_file.read_text(encoding="utf-8"))
    store.upsert(
        collection="test",
        documents=["hello world"],
        embeddings=[[0.1, 0.2]],
        ids=["a.md::0"],
        metadatas=[{"source": "a.md", "content_hash": old_hash, "chunk_index": 0}],
    )

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert result == {"added": 0, "updated": 1, "deleted": 0, "unchanged": 0}
    mock_emb.assert_called_once()
    meta = store.get_all_metadata("test")["metadatas"][0]
    assert meta["title"] == "Old Doc"


def test_sync_frontmatter_with_tags_list(tmp_path):
    """List-valued frontmatter (tags) is JSON-serialized for Chroma metadata."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("---\ntags: [python, rag, mcp]\n---\nhello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    meta = store.get_all_metadata("test")["metadatas"][0]
    assert json.loads(meta["tags"]) == ["python", "rag", "mcp"]


def test_sync_frontmatter_with_dates(tmp_path):
    """Date-valued frontmatter is stringified for Chroma metadata."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("---\ncreated: 2024-01-15\n---\nhello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    meta = store.get_all_metadata("test")["metadatas"][0]
    assert meta["created"] == "2024-01-15"


def test_sync_preserves_content_hash(tmp_path):
    """content_hash is computed over the stripped body, not the raw file text."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    md_file = docs_dir / "a.md"
    md_file.write_text("---\ntitle: Test Doc\n---\nhello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    raw_text = md_file.read_text(encoding="utf-8")
    body = strip_frontmatter(raw_text)
    meta = store.get_all_metadata("test")["metadatas"][0]
    assert meta["content_hash"] == file_hash(body)
    assert meta["content_hash"] != file_hash(raw_text)


def test_sync_incremental_with_frontmatter(tmp_path):
    """Re-syncing unchanged frontmatter files skips embedding."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("---\ntitle: Test Doc\n---\nhello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert result == {"added": 0, "updated": 0, "deleted": 0, "unchanged": 1}
    mock_emb.assert_not_called()
