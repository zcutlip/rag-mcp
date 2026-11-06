"""Tests for rag_mcp.server MCP tools."""
import asyncio
import os
import re
import signal
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
        project_root="/tmp/project",
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
    """query_documents returns structured results with content, distance, and metadata."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_embeddings.return_value = [[0.1, 0.2]]
    mock_store.query.return_value = {
        "documents": [["# Heading\nContent one."]],
        "ids": [["doc1"]],
        "distances": [[0.05]],
        "metadatas": [[{"source": "test.md", "chunk_index": 0, "content_hash": "abc123"}]],
    }

    from rag_mcp.server import query_documents

    result = query_documents(query="heading", n_results=1)
    assert isinstance(result, dict)
    assert "results" in result
    assert "sources" in result
    assert len(result["results"]) == 1
    assert "Content one." in result["results"][0]["content"]
    assert result["results"][0]["distance"] == 0.05
    assert result["results"][0]["rank"] == 1
    assert result["results"][0]["metadata"]["source"] == "test.md"


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
        "sync",
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


@patch("rag_mcp.server.threading.Thread")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_starts_watcher_thread(
    mock_get_config, mock_vectorstore, mock_run, mock_sync, mock_thread
):
    """main() starts one daemon watcher thread after auto-ingest when watch is on."""
    cfg = _test_config()
    cfg.ingest_watch = True
    cfg.ingest_watch_interval = 30
    mock_get_config.return_value = cfg

    from rag_mcp.server import main

    main([])
    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs["daemon"] is True
    mock_thread.return_value.start.assert_called_once()


@patch("rag_mcp.server.threading.Thread")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_watch_disabled_starts_no_thread(
    mock_get_config, mock_vectorstore, mock_run, mock_sync, mock_thread
):
    """main() starts no watcher when ingest.watch is False."""
    cfg = _test_config()
    cfg.ingest_watch = False
    cfg.ingest_watch_interval = 30
    mock_get_config.return_value = cfg

    from rag_mcp.server import main

    main([])
    mock_thread.assert_not_called()


@patch("rag_mcp.server.threading.Thread")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_without_ingest_dir_starts_no_thread(
    mock_get_config, mock_vectorstore, mock_run, mock_sync, mock_thread
):
    """main() starts no watcher when no ingest directory is configured."""
    cfg = _test_config()
    cfg.ingest_dir = None
    cfg.ingest_watch = True
    mock_get_config.return_value = cfg

    from rag_mcp.server import main

    main([])
    mock_thread.assert_not_called()


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


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_store")
@patch("rag_mcp.server.ingest.sync_directory")
def test_sync_tool_reingests_configured_corpus(
    mock_sync, mock_get_store, mock_get_config
):
    """sync() re-runs the configured corpus through ingest.sync_directory."""
    mock_get_config.return_value = _test_config()
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_sync.return_value = {"added": 1, "updated": 2, "deleted": 3, "unchanged": 4}

    from rag_mcp.server import sync

    result = sync()
    assert result == (
        "Synced '/tmp/docs' into collection 'docs': "
        "1 added, 2 updated, 3 deleted, 4 unchanged."
    )
    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert args[0] is mock_store
    assert args[1] == "/tmp/docs"
    assert kwargs["collection"] == "docs"
    assert kwargs["embeddings_host"] == "http://localhost:11434"
    assert kwargs["embeddings_model"] == "nomic-embed-text"


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_store")
@patch("rag_mcp.server.ingest.sync_directory")
def test_sync_tool_raises_when_ingest_dir_unset(
    mock_sync, mock_get_store, mock_get_config
):
    """sync() without a configured ingest directory raises guidance-bearing ValueError."""
    mock_get_config.return_value = MagicMock(
        embeddings_host="http://localhost:11434",
        embeddings_model="nomic-embed-text",
        chroma_persist_dir="/tmp/chroma",
        ingest_dir=None,
        ingest_collection="docs",
    )

    from rag_mcp.server import sync

    with pytest.raises(ValueError) as exc_info:
        sync()
    assert "[ingest] directory" in str(exc_info.value)
    assert "RAG_MCP_INGEST_DIR" in str(exc_info.value)
    mock_sync.assert_not_called()


def test_sync_description_mentions_configured_corpus():
    """The sync tool description covers re-syncing the configured corpus collection."""
    from rag_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    sync_tool = next(tool for tool in tools if tool.name == "sync")
    assert "configured" in sync_tool.description.lower()
    assert "collection" in sync_tool.description.lower()


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_store")
@patch("rag_mcp.server.ingest.sync_directory")
def test_sync_forwards_configured_patterns(mock_sync, mock_get_store, mock_get_config):
    """sync() forwards configured ingest_patterns to ingest.sync_directory."""
    mock_get_config.return_value = MagicMock(
        embeddings_host="http://localhost:11434",
        embeddings_model="nomic-embed-text",
        chroma_persist_dir="/tmp/chroma",
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
        ingest_patterns=["!private/**"],
    )
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_sync.return_value = {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0}

    from rag_mcp.server import sync

    sync()
    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert args[0] is mock_store
    assert args[1] == "/tmp/docs"
    assert kwargs["collection"] == "docs"
    assert kwargs["patterns"] == ["!private/**"]


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.get_store")
@patch("rag_mcp.server.ingest.sync_directory")
def test_sync_forwards_no_patterns_when_unset(mock_sync, mock_get_store, mock_get_config):
    """sync() forwards patterns=None when ingest_patterns is unset."""
    mock_get_config.return_value = MagicMock(
        embeddings_host="http://localhost:11434",
        embeddings_model="nomic-embed-text",
        chroma_persist_dir="/tmp/chroma",
        ingest_dir="/tmp/docs",
        ingest_collection="docs",
        ingest_patterns=None,
    )
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_sync.return_value = {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0}

    from rag_mcp.server import sync

    sync()
    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert args[0] is mock_store
    assert args[1] == "/tmp/docs"
    assert kwargs["collection"] == "docs"
    assert kwargs["patterns"] is None


@patch("rag_mcp.server.get_config")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
def test_main_version_prints_version_and_exits_zero(
    mock_vectorstore, mock_run, mock_get_config, capsys
):
    """main(["--version"]) prints bare package version to stdout, exits 0, no startup."""
    from rag_mcp import __version__
    from rag_mcp.server import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out.rstrip() == __version__
    mock_get_config.assert_not_called()
    mock_run.assert_not_called()
    mock_vectorstore.assert_not_called()


def test_format_sync_counts_orders_fields():
    """Counts render in a fixed order, defaulting missing keys to zero."""
    from rag_mcp.server import _format_sync_counts

    assert _format_sync_counts(
        {"added": 1, "updated": 2, "deleted": 3, "unchanged": 4}
    ) == "added=1 updated=2 deleted=3 unchanged=4"
    assert _format_sync_counts({}) == "added=0 updated=0 deleted=0 unchanged=0"


def test_instance_tag_uses_project_basename_and_pid():
    """The tag identifies the project directory and this OS process."""
    from rag_mcp.server import _instance_tag

    cfg = MagicMock(
        project_root="/Users/zach/projects/platform-security-guide-scraper"
    )
    assert _instance_tag(cfg) == (
        f"rag-mcp[platform-security-guide-scraper:{os.getpid()}]"
    )


def test_display_path_relative_inside_absolute_outside(tmp_path):
    """Paths inside the project render relative (no `./`); outside ones stay absolute."""
    from rag_mcp.server import _display_path

    root = str(tmp_path)
    assert _display_path(str(tmp_path / ".chroma"), root) == ".chroma"
    assert _display_path(str(tmp_path / "docs"), root) == "docs"
    assert _display_path("/Volumes/External/rag-chroma", root) == (
        "/Volumes/External/rag-chroma"
    )
    sibling = str(tmp_path.parent / (tmp_path.name + "-sibling") / "docs")
    assert _display_path(sibling, root) == sibling  # never ".."


def _assert_file_line(line: str, expected_body: str) -> None:
    """The file form is the same line behind an ISO-8601 UTC timestamp."""
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z " + re.escape(expected_body),
        line,
    ), line


def test_log_sink_emits_to_stderr_and_file(tmp_path, capsys):
    """One emit body reaches stderr tagged, and the file adds an ISO timestamp."""
    from rag_mcp.server import _LogSink

    tag = "rag-mcp[proj:123]"
    log_path = tmp_path / "rag.log"
    sink = _LogSink(str(log_path), tag)
    try:
        sink.emit("startup sync: added=1 updated=0 deleted=0 unchanged=2")
    finally:
        sink.close()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"{tag} startup sync: added=1 updated=0 deleted=0 unchanged=2\n"
    )
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    _assert_file_line(
        lines[0], f"{tag} startup sync: added=1 updated=0 deleted=0 unchanged=2"
    )


def test_log_sink_rotates_at_cap(tmp_path, monkeypatch):
    """Once the cap is reached the file rotates to a single `.1` backup."""
    from rag_mcp import server

    monkeypatch.setattr(server, "LOG_FILE_CAP_BYTES", 300)
    tag = "rag-mcp[proj:123]"
    log_path = tmp_path / "rag.log"
    sink = server._LogSink(str(log_path), tag)
    try:
        sink.emit("a" * 300)
        sink.emit("b" * 300)
    finally:
        sink.close()

    backup = (tmp_path / "rag.log.1").read_text().splitlines()
    current = log_path.read_text().splitlines()
    assert len(backup) == 1 and backup[0].endswith(" " + tag + " " + "a" * 300)
    assert len(current) == 1 and current[0].endswith(" " + tag + " " + "b" * 300)


def test_log_sink_unavailable_path_warns_once_and_keeps_stderr(tmp_path, capsys):
    """An unopenable log path warns once and degrades to stderr-only, never raising."""
    from rag_mcp.server import _LogSink

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    sink = _LogSink(str(blocker / "rag.log"), "rag-mcp[proj:123]")
    sink.emit("first")
    sink.emit("second")
    sink.close()

    captured = capsys.readouterr()
    assert captured.err.count("rag-mcp log file unavailable") == 1
    assert "first" in captured.err
    assert "second" in captured.err


def test_install_sigterm_handler_records_reason_and_exits():
    """The SIGTERM handler records the reason and exits with 128+signum."""
    from rag_mcp import server

    state = {"reason": "exit"}
    with patch("rag_mcp.server.signal.signal") as mock_signal:
        server._install_sigterm_handler(state)

    signum, handler = mock_signal.call_args.args
    assert signum == signal.SIGTERM
    with pytest.raises(SystemExit) as exc_info:
        handler(signal.SIGTERM, None)
    assert exc_info.value.code == 128 + signal.SIGTERM
    assert state["reason"] == "SIGTERM"


@patch("rag_mcp.server._LogSink")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_logs_start_startup_and_shutdown(
    mock_get_config, mock_vectorstore, mock_run, mock_sync, mock_sink_cls
):
    """main() logs the start config, startup sync counts, then shutdown; sink closes."""
    cfg = _test_config()
    cfg.ingest_watch = False
    cfg.ingest_watch_interval = 30
    cfg.logging_path = "/tmp/rag.log"
    cfg.project_root = "/tmp/project"
    cfg.chroma_persist_dir = "/tmp/project/.chroma"
    cfg.ingest_dir = "/tmp/project/docs"
    mock_get_config.return_value = cfg
    mock_sync.return_value = {
        "added": 2,
        "updated": 0,
        "deleted": 1,
        "unchanged": 180,
    }

    from rag_mcp.server import main

    main([])

    mock_sink_cls.assert_called_once()
    sink_args = mock_sink_cls.call_args.args
    assert sink_args[0] == "/tmp/rag.log"
    assert sink_args[1] == f"rag-mcp[project:{os.getpid()}]"
    sink = mock_sink_cls.return_value
    texts = [call.args[0] for call in sink.emit.call_args_list]
    assert texts[0] == "project='/tmp/project'"
    assert texts[1] == (
        "start: persist_dir='.chroma' ingest_dir='docs' "
        "collection='docs' watch=False watch_interval=30"
    )
    assert texts[2] == (
        "startup sync: added=2 updated=0 deleted=1 unchanged=180"
    )
    assert texts[-1] == "shutdown: reason=exit"
    sink.close.assert_called_once()


@patch("rag_mcp.server._LogSink")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_skips_startup_sync_line_without_ingest_dir(
    mock_get_config, mock_vectorstore, mock_run, mock_sync, mock_sink_cls
):
    """With no ingest directory there is no startup sync line, but start/shutdown stay."""
    cfg = _test_config()
    cfg.ingest_dir = None
    cfg.ingest_watch = False
    mock_get_config.return_value = cfg

    from rag_mcp.server import main

    main([])

    texts = [call.args[0] for call in mock_sink_cls.return_value.emit.call_args_list]
    assert texts[0] == "project='/tmp/project'"
    assert texts[1].startswith("start:")
    assert not any("startup sync" in text for text in texts)
    assert texts[-1] == "shutdown: reason=exit"


@patch("rag_mcp.server._install_sigterm_handler")
@patch("rag_mcp.server._LogSink")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_shutdown_line_reports_sigterm_reason(
    mock_get_config,
    mock_vectorstore,
    mock_run,
    mock_sync,
    mock_sink_cls,
    mock_install,
):
    """The shutdown line reads the live reason state, so SIGTERM reports itself."""
    cfg = _test_config()
    cfg.ingest_dir = None
    cfg.ingest_watch = False
    mock_get_config.return_value = cfg
    mock_install.side_effect = lambda state: state.update(reason="SIGTERM")

    from rag_mcp.server import main

    main([])

    mock_sink_cls.return_value.emit.assert_any_call(
        "shutdown: reason=SIGTERM"
    )


@patch("rag_mcp.server._install_sigterm_handler")
@patch("rag_mcp.server._LogSink")
@patch("rag_mcp.server.ingest.sync_directory")
@patch("rag_mcp.server.mcp.run")
@patch("rag_mcp.server.VectorStore")
@patch("rag_mcp.server.get_config")
def test_main_shutdown_line_emitted_when_run_raises(
    mock_get_config,
    mock_vectorstore,
    mock_run,
    mock_sync,
    mock_sink_cls,
    mock_install,
):
    """A SystemExit out of mcp.run() still leaves the shutdown line (finally)."""
    cfg = _test_config()
    cfg.ingest_dir = None
    cfg.ingest_watch = False
    mock_get_config.return_value = cfg
    mock_run.side_effect = SystemExit(143)

    from rag_mcp.server import main

    with pytest.raises(SystemExit):
        main([])

    mock_sink_cls.return_value.emit.assert_any_call(
        "shutdown: reason=exit"
    )
