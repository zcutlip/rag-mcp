"""Tests for rag_mcp.ingest module."""
from unittest.mock import patch

from rag_mcp.ingest import chunk_text, sync_directory
from rag_mcp.store import VectorStore

EMBEDDINGS_HOST = "http://localhost:11434"
EMBEDDINGS_MODEL = "nomic-embed-text"


def test_chunk_text_short_text_single_chunk():
    """Text shorter than chunk_size returns unchanged as a single chunk."""
    text = "short text"
    assert chunk_text(text, chunk_size=100, overlap=10) == [text]


def test_chunk_text_splits_long_text_with_overlap():
    """Text longer than chunk_size splits into overlapping chunks."""
    text = "a" * 50 + "b" * 50
    chunks = chunk_text(text, chunk_size=60, overlap=10)
    assert len(chunks) > 1
    # tail of chunk n should be head of chunk n+1
    assert chunks[0][-10:] == chunks[1][:10]


def _fake_embeddings(texts, host, model):
    return [[0.1, 0.2] for _ in texts]


def test_sync_first_time(tmp_path):
    """First sync of a new file counts as added and calls embeddings once."""
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

    meta = store.get_all_metadata("test")
    assert meta["metadatas"][0]["source"] == "a.md"


def test_sync_noop_resync(tmp_path):
    """Re-syncing an unchanged directory does not call embeddings again."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello world")

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


def test_sync_changed_file_resync(tmp_path):
    """Editing a file's content triggers re-embedding and updates its hash."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    md_file = docs_dir / "a.md"
    md_file.write_text("hello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    old_hash = store.get_all_metadata("test")["metadatas"][0]["content_hash"]
    md_file.write_text("goodbye world, this content is different")

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert result == {"added": 0, "updated": 1, "deleted": 0, "unchanged": 0}
    mock_emb.assert_called_once_with(
        ["goodbye world, this content is different"],
        EMBEDDINGS_HOST,
        EMBEDDINGS_MODEL,
    )
    new_hash = store.get_all_metadata("test")["metadatas"][0]["content_hash"]
    assert new_hash != old_hash


def test_sync_deleted_file_resync(tmp_path):
    """Removing a file from disk removes its chunks from the store on resync."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    md_file = docs_dir / "a.md"
    md_file.write_text("hello world")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    md_file.unlink()

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert result == {"added": 0, "updated": 0, "deleted": 1, "unchanged": 0}
    meta = store.get_all_metadata("test")
    assert meta["ids"] == []


def _sync_all(store, docs_dir):
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        return sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )


def test_sync_frontmatter_reserved_keys_do_not_overwrite_source(tmp_path):
    """Frontmatter `source:`/`content_hash:`/`chunk_index:` must not displace sync keys.

    Regression: an Obsidian-style `source:` URL used to overwrite the file-path
    source in stored metadata, so every pass looked the file up by path, found
    nothing, re-added it, and purged the URL-labeled rows as orphans — the
    sync never converged.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "note.md").write_text(
        "---\n"
        "title: Real Title\n"
        "source: https://example.com/article\n"
        "content_hash: bogus\n"
        "chunk_index: 99\n"
        "---\n"
        "body text here\n"
    )

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    first = _sync_all(store, docs_dir)
    assert first == {"added": 1, "updated": 0, "deleted": 0, "unchanged": 0}

    meta = store.get_all_metadata("test")
    assert meta["metadatas"][0]["source"] == "note.md"
    assert meta["metadatas"][0]["chunk_index"] == 0
    assert meta["metadatas"][0]["title"] == "Real Title"
    assert meta["metadatas"][0]["content_hash"] != "bogus"

    second = _sync_all(store, docs_dir)
    assert second == {"added": 0, "updated": 0, "deleted": 0, "unchanged": 1}


def test_sync_empty_file_converges(tmp_path):
    """A frontmatter-only file stores nothing and settles as unchanged."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "empty.md").write_text('---\nsorting-spec: "order-asc: a-z"\n---\n')

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch(
        "rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings
    ) as mock_emb:
        first = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )
        second = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )

    assert first == {"added": 0, "updated": 0, "deleted": 0, "unchanged": 1}
    assert second == {"added": 0, "updated": 0, "deleted": 0, "unchanged": 1}
    mock_emb.assert_not_called()
    assert store.get_all_metadata("test")["ids"] == []
