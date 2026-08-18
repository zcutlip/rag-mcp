"""Tests for the structured query_documents response format."""
from unittest.mock import MagicMock, patch


def _test_config():
    """A config stub for query_documents to fetch host/model."""
    return MagicMock(
        embeddings_host="http://localhost:11434",
        embeddings_model="nomic-embed-text",
        chroma_persist_dir="/tmp/chroma",
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
    )


def _query_response():
    """A ChromaDB-shaped query result spanning two sources across three hits."""
    return {
        "documents": [["Guide intro", "Guide details", "API overview"]],
        "ids": [["guide::0", "guide::1", "api::0"]],
        "distances": [[0.12345, 0.98765, 0.21345]],
        "metadatas": [[
            {
                "source": "docs/guide.md",
                "chunk_index": 0,
                "content_hash": "hash-abc",
                "title": "User Guide",
                "url": "https://example.com/guide",
                "tags": ["docs", "guide"],
                "created": "2024-01-01",
                "updated": "2024-06-01",
            },
            {
                "source": "docs/guide.md",
                "chunk_index": 1,
                "content_hash": "hash-abc",
                "title": "User Guide",
                "url": "https://example.com/guide",
                "tags": ["docs", "guide"],
                "created": "2024-01-01",
                "updated": "2024-06-01",
            },
            {
                "source": "docs/api.md",
                "chunk_index": 0,
                "content_hash": "hash-def",
                "title": "API Reference",
                "url": "https://example.com/api",
                "tags": ["api"],
                "created": "2024-02-15",
                "updated": "2024-07-01",
            },
        ]],
    }


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_returns_structured_format(mock_get_store, mock_get_embeddings, mock_get_config):
    """query_documents returns a dict with 'results' and 'sources' keys."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide")
    assert isinstance(result, dict)
    assert set(result.keys()) == {"results", "sources"}
    assert isinstance(result["results"], list)
    assert isinstance(result["sources"], dict)


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_compact_mode_omits_metadata(mock_get_store, mock_get_embeddings, mock_get_config):
    """compact=True keeps only chunk-identity keys in each hit's metadata."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide", compact=True)
    for hit in result["results"]:
        assert set(hit["metadata"].keys()) == {"source", "chunk_index", "content_hash"}


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_full_mode_includes_metadata(mock_get_store, mock_get_embeddings, mock_get_config):
    """compact=False merges source-level metadata (title, url, tags, created, updated) into hits."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide", compact=False)
    for hit in result["results"]:
        metadata = hit["metadata"]
        for key in ("source", "chunk_index", "content_hash", "title", "url", "tags", "created", "updated"):
            assert key in metadata
    first = result["results"][0]["metadata"]
    assert first["title"] == "User Guide"
    assert first["url"] == "https://example.com/guide"
    assert first["tags"] == ["docs", "guide"]
    assert first["created"] == "2024-01-01"
    assert first["updated"] == "2024-06-01"


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_deduplicates_sources(mock_get_store, mock_get_embeddings, mock_get_config):
    """Multiple hits from the same source collapse into one 'sources' entry."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide")
    assert set(result["sources"].keys()) == {"docs/guide.md", "docs/api.md"}
    assert result["sources"]["docs/guide.md"] == {
        "title": "User Guide",
        "url": "https://example.com/guide",
        "tags": ["docs", "guide"],
        "created": "2024-01-01",
        "updated": "2024-06-01",
    }
    assert result["sources"]["docs/api.md"] == {
        "title": "API Reference",
        "url": "https://example.com/api",
        "tags": ["api"],
        "created": "2024-02-15",
        "updated": "2024-07-01",
    }


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_rounds_distances(mock_get_store, mock_get_embeddings, mock_get_config):
    """Distances in hits are rounded to 3 decimal places."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide")
    assert [hit["distance"] for hit in result["results"]] == [0.123, 0.213, 0.988]


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_empty_results(mock_get_store, mock_get_embeddings, mock_get_config):
    """query_documents returns an empty structured response when nothing matches."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = {
        "documents": [[]],
        "ids": [[]],
        "distances": [[]],
        "metadatas": [[]],
    }

    from rag_mcp.server import query_documents

    result = query_documents(query="nothing")
    assert result == {"results": [], "sources": {}}


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_preserves_ranking(mock_get_store, mock_get_embeddings, mock_get_config):
    """Hits are ranked 1..n in ascending distance order."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide")
    assert [hit["rank"] for hit in result["results"]] == [1, 2, 3]
    assert [hit["content"] for hit in result["results"]] == [
        "Guide intro",
        "API overview",
        "Guide details",
    ]


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_metadata_includes_chunk_info(mock_get_store, mock_get_embeddings, mock_get_config):
    """Each hit carries source, chunk_index, and content_hash in its metadata."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = _query_response()

    from rag_mcp.server import query_documents

    result = query_documents(query="guide")
    for hit in result["results"]:
        for key in ("source", "chunk_index", "content_hash"):
            assert key in hit["metadata"]
    first = result["results"][0]["metadata"]
    assert first["source"] == "docs/guide.md"
    assert first["chunk_index"] == 0
    assert first["content_hash"] == "hash-abc"
