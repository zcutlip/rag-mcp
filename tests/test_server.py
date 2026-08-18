"""Tests for rag_mcp.server MCP tools."""
from unittest.mock import MagicMock, patch

import pytest


def _test_config():
    """A config stub for tools and main() that fetch host/model and ingest settings."""
    return MagicMock(
        embeddings_host="http://localhost:11434",
        embeddings_model="nomic-embed-text",
        chroma_persist_dir="/tmp/chroma",
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
    )


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_add_documents_tool(mock_get_store, mock_get_embeddings, mock_get_config):
    """add_documents returns confirmation string with count."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2], [0.3, 0.4]]

    from rag_mcp.server import add_documents

    result = add_documents(
        documents=["# Heading\nContent one.", "## Sub\nContent two."],
        ids=["doc1", "doc2"],
    )
    assert result == "Added 2 document(s) to collection 'default'."
    mock_get_embeddings.assert_called_once()
    mock_store.add.assert_called_once()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_documents_tool(mock_get_store, mock_get_embeddings, mock_get_config):
    """query_documents returns formatted results with document text and IDs."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = {
        "documents": [["# Heading\nContent one."]],
        "ids": [["doc1"]],
        "distances": [[0.05]],
        "metadatas": [[{"key": "val"}]],
    }

    from rag_mcp.server import query_documents

    result = query_documents(query="heading", n_results=1)
    assert "Content one." in result
    assert "doc1" in result


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_documents_no_results(mock_get_store, mock_get_embeddings, mock_get_config):
    """query_documents returns 'No matching documents found.' for empty results."""
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
    assert result == "No matching documents found."


@patch("rag_mcp.server.get_store")
def test_list_collections_tool(mock_get_store):
    """list_collections returns collection names."""
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_store.list_collections.return_value = ["default", "other"]

    from rag_mcp.server import list_collections

    result = list_collections()
    assert "default" in result


@patch("rag_mcp.server.get_store")
def test_delete_collection_tool(mock_get_store):
    """delete_collection returns confirmation string."""
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_store.list_collections.return_value = ["default"]

    from rag_mcp.server import delete_collection

    result = delete_collection(collection="default")
    assert result == "Deleted collection 'default'."
    mock_store.delete_collection.assert_called_once_with("default")


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_add_documents_empty(mock_get_store, mock_get_embeddings, mock_get_config):
    """add_documents([]) returns confirmation without calling get_embeddings."""
    from rag_mcp.server import add_documents

    result = add_documents(documents=[])
    assert result == "Added 0 document(s) to collection 'default'."
    mock_get_embeddings.assert_not_called()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_add_documents_validation(mock_get_store, mock_get_embeddings, mock_get_config):
    """Mismatched ids and documents raise ValueError."""
    from rag_mcp.server import add_documents

    with pytest.raises(ValueError):
        add_documents(documents=["doc1", "doc2"], ids=["id1"])
    mock_get_embeddings.assert_not_called()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_embeddings")
@patch("rag_mcp.server.get_store")
def test_query_documents_validation(mock_get_store, mock_get_embeddings, mock_get_config):
    """query_documents rejects n_results < 1 without calling embeddings/store."""
    from rag_mcp.server import query_documents

    with pytest.raises(ValueError):
        query_documents(query="x", n_results=0)
    mock_get_embeddings.assert_not_called()
    mock_get_store.assert_not_called()


@patch("rag_mcp.server.get_store")
def test_delete_collection_missing(mock_get_store):
    """Deleting a nonexistent collection raises ValueError."""
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_store.list_collections.return_value = ["default"]

    from rag_mcp.server import delete_collection

    with pytest.raises(ValueError):
        delete_collection(collection="missing")
    mock_store.delete_collection.assert_not_called()


@patch("rag_mcp.server.get_config")
def test_main_config_error_exits_with_guidance(mock_get_config, capsys):
    """main() reports a config error on stderr, exits 1, and offers init guidance."""
    mock_get_config.side_effect = ValueError(
        "chroma.persist_dir must be configured in .rag-mcp.toml "
        "or via RAG_MCP_CHROMA_PERSIST_DIR"
    )

    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "chroma.persist_dir must be configured" in captured.err
    assert "rag-mcp-config init" in captured.err
    assert "Traceback" not in captured.err


@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_auto_ingest_forwards_host_model(
    mock_get_config, mock_vectorstore, mock_run, mock_sync
):
    """main() startup auto-ingest forwards embeddings host/model to ingest.sync_directory."""
    mock_get_config.return_value = _test_config()

    from rag_mcp.server import main

    main([])
    mock_sync.assert_called_once()
    _, kwargs = mock_sync.call_args
    assert kwargs["embeddings_host"] == "http://localhost:11434"
    assert kwargs["embeddings_model"] == "nomic-embed-text"


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
def test_main_help_exits_zero_without_starting(mock_run, mock_get_config, capsys):
    """main(["--help"]) prints usage, exits 0, without loading config or starting the server."""
    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "usage" in captured.out + captured.err
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()
