"""Tests for rag_mcp.store module."""
import pytest

from rag_mcp.store import VectorStore


def test_store_add_and_query(tmp_path):
    """Add documents and query returns the expected results."""
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    embeddings = [[1.0, 0.0], [0.0, 1.0]]
    store.add(
        collection="test",
        documents=["first doc", "second doc"],
        embeddings=embeddings,
        ids=["id1", "id2"],
    )
    results = store.query(collection="test", query_embedding=[1.0, 0.0], n_results=2)
    assert "first doc" in results["documents"][0]


def test_store_add_generates_ids(tmp_path):
    """Adding documents without IDs generates unique string IDs."""
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    documents = ["doc one", "doc two", "doc three"]
    embeddings = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    store.add(collection="test", documents=documents, embeddings=embeddings)

    results = store.query(collection="test", query_embedding=[1.0, 0.0], n_results=3)
    ids = results["ids"][0]
    assert len(ids) == len(documents)
    assert len(set(ids)) == len(ids)  # all unique
    assert all(isinstance(i, str) for i in ids)


def test_store_add_validates_lengths(tmp_path):
    """Mismatched ids and metadatas raise ValueError."""
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with pytest.raises(ValueError):
        store.add(
            collection="test",
            documents=["doc1", "doc2"],
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            ids=["id1"],  # mismatched length
        )
    with pytest.raises(ValueError):
        store.add(
            collection="test",
            documents=["doc1", "doc2"],
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            metadatas=[{"key": "val"}],  # mismatched length
        )


def test_store_list_and_delete_collections(tmp_path):
    """list_collections and delete_collection work correctly."""
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    store.add(
        collection="my_collection",
        documents=["doc"],
        embeddings=[[1.0, 0.0]],
    )
    assert "my_collection" in store.list_collections()

    store.delete_collection("my_collection")
    assert "my_collection" not in store.list_collections()


def test_store_query_empty_collection(tmp_path):
    """Querying an empty collection returns empty results."""
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    results = store.query(collection="empty", query_embedding=[1.0, 0.0], n_results=5)
    assert results["documents"] == [[]] or results["documents"] == []
    assert results["ids"] == [[]] or results["ids"] == []
    assert results["distances"] == [[]] or results["distances"] == []
    assert results["metadatas"] == [[]] or results["metadatas"] == []
