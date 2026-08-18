"""Tests for rag_mcp.server MCP tools."""
import asyncio
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
    assert result == {"results": [], "sources": {}}


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


# Server metadata and the rag://readme resource (planned feature).
def test_server_metadata_exposes_title_description_version_instructions():
    """The module-level MCPServer is constructed with full server metadata."""
    from rag_mcp.server import mcp

    assert mcp.title
    assert mcp.description
    assert mcp.version == "0.1.0"
    assert mcp.instructions


def test_server_instructions_mention_query_documents_and_corpus():
    """Server instructions direct clients to query_documents over the indexed corpus."""
    from rag_mcp.server import mcp

    assert mcp.instructions
    assert "query_documents" in mcp.instructions
    assert "corpus" in mcp.instructions


def test_resources_list_includes_readme_resource():
    """resources/list exposes the rag://readme resource."""
    from rag_mcp.server import mcp

    resources = asyncio.run(mcp.list_resources())
    uris = [resource.uri for resource in resources]
    assert "rag://readme" in uris


def test_read_readme_resource_returns_packaged_readme():
    """Reading rag://readme returns the packaged README content."""
    readme = "# rag-mcp\n\nRAG MCP server backed by Ollama embeddings and ChromaDB."
    with patch("rag_mcp.server._read_readme", return_value=readme, create=True):
        from rag_mcp.server import mcp

        contents = asyncio.run(mcp.read_resource("rag://readme"))
    assert contents[0].content == readme


def test_readme_resource_metadata():
    """The rag://readme resource carries name, description, and markdown mime type."""
    from rag_mcp.server import mcp

    resources = asyncio.run(mcp.list_resources())
    uris = [resource.uri for resource in resources]
    assert "rag://readme" in uris
    readme = next(resource for resource in resources if resource.uri == "rag://readme")
    assert "README" in readme.name.upper()
    assert "README" in readme.description.upper()
    assert readme.mime_type == "text/markdown"


def test_query_documents_description_mentions_questions_about_corpus():
    """query_documents description covers answering questions about the indexed corpus."""
    from rag_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    query_tool = next(tool for tool in tools if tool.name == "query_documents")
    assert "question" in query_tool.description.lower()
    assert "corpus" in query_tool.description.lower()


def test_server_registers_all_five_tools():
    """All five tools stay registered alongside the metadata and resource additions."""
    from rag_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "add_documents",
        "query_documents",
        "list_collections",
        "delete_collection",
        "sync_directory",
    }


def test_all_tool_descriptions_present():
    """Every registered tool keeps a clear, non-empty description."""
    from rag_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        assert tool.name
        assert tool.description


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


# The readme command reads the packaged README through a module-level metadata
# lookup seam (rag_mcp.server._read_readme) so tests can mock it cleanly.
@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server._read_readme", create=True)
def test_main_readme_prints_packaged_readme(mock_read, mock_run, mock_get_config, capsys):
    """main(["readme"]) prints the packaged README to stdout, exits 0, no startup."""
    mock_read.return_value = "# rag-mcp\n\nRAG MCP server backed by Ollama embeddings and ChromaDB."

    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["readme"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "# rag-mcp" in captured.out
    mock_read.assert_called_once()
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
def test_main_help_includes_readme_command(mock_run, mock_get_config, capsys):
    """main(["--help"]) lists the readme command in usage output without startup."""
    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "readme" in captured.out + captured.err
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
def test_main_unknown_command_exits_with_usage(mock_run, mock_get_config, capsys):
    """main() with an unknown command exits 2 with usage on stderr, no startup."""
    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["frobnicate"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage" in captured.err
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server._read_readme", create=True)
def test_main_readme_metadata_missing_reports_error(
    mock_read, mock_run, mock_get_config, capsys
):
    """main(["readme"]) without packaged README metadata exits nonzero with a helpful error."""
    mock_read.return_value = None

    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["readme"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "Error" in captured.err
    assert "README" in captured.err
    assert "Traceback" not in captured.err
    mock_read.assert_called_once()
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()
