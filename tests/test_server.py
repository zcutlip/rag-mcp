"""Tests for rag_mcp.server MCP tools."""
from unittest.mock import patch, MagicMock

import pytest


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_add_documents_tool(mock_get_embeddings, mock_store):
    """add_documents returns confirmation string with count."""
    mock_get_embeddings.return_value = [[0.1, 0.2], [0.3, 0.4]]

    from rag_mcp.server import add_documents

    result = add_documents(
        documents=["# Heading\nContent one.", "## Sub\nContent two."],
        ids=["doc1", "doc2"],
    )
    assert result == "Added 2 document(s) to collection 'default'."
    mock_get_embeddings.assert_called_once()
    mock_store.add.assert_called_once()


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_query_documents_tool(mock_get_embeddings, mock_store):
    """query_documents returns formatted results with document text and IDs."""
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


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_query_documents_no_results(mock_get_embeddings, mock_store):
    """query_documents returns 'No matching documents found.' for empty results."""
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


@patch("rag_mcp.server.store")
def test_list_collections_tool(mock_store):
    """list_collections returns collection names."""
    mock_store.list_collections.return_value = ["default", "other"]

    from rag_mcp.server import list_collections

    result = list_collections()
    assert "default" in result


@patch("rag_mcp.server.store")
def test_delete_collection_tool(mock_store):
    """delete_collection returns confirmation string."""
    from rag_mcp.server import delete_collection

    result = delete_collection(collection="default")
    assert result == "Deleted collection 'default'."
    mock_store.delete_collection.assert_called_once_with("default")


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_add_documents_empty(mock_get_embeddings, mock_store):
    """add_documents([]) returns confirmation without calling get_embeddings."""
    from rag_mcp.server import add_documents

    result = add_documents(documents=[])
    assert result == "Added 0 document(s) to collection 'default'."
    mock_get_embeddings.assert_not_called()


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_add_documents_validation(mock_get_embeddings, mock_store):
    """Mismatched ids and documents raise ValueError."""
    from rag_mcp.server import add_documents

    with pytest.raises(ValueError):
        add_documents(documents=["doc1", "doc2"], ids=["id1"])
    mock_get_embeddings.assert_not_called()


@patch("rag_mcp.server.store")
@patch("rag_mcp.server.get_embeddings")
def test_query_documents_validation(mock_get_embeddings, mock_store):
    """query_documents rejects n_results < 1 without calling embeddings/store."""
    from rag_mcp.server import query_documents

    with pytest.raises(ValueError):
        query_documents(query="x", n_results=0)
    mock_get_embeddings.assert_not_called()
    mock_store.query.assert_not_called()


@patch("rag_mcp.server.store")
def test_delete_collection_missing(mock_store):
    """Deleting a nonexistent collection raises ValueError."""
    mock_store.list_collections.return_value = ["default"]

    from rag_mcp.server import delete_collection

    with pytest.raises(ValueError):
        delete_collection(collection="missing")
    mock_store.delete_collection.assert_not_called()
