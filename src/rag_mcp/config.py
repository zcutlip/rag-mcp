"""Environment-backed configuration for the RAG MCP server."""
import os
from pathlib import Path

import platformdirs


def get_persist_dir() -> str:
    """Return the ChromaDB persistence directory.

    Honors CHROMA_PERSIST_DIR (with ``~`` expansion) if set; otherwise
    defaults to the platform user-data directory.
    """
    raw = os.environ.get("CHROMA_PERSIST_DIR")
    if raw:
        return str(Path(raw).expanduser())
    return str(Path(platformdirs.user_data_dir("rag-mcp", appauthor=False)) / "chroma_data")


def get_ingest_dir() -> str | None:
    """Return the startup auto-ingest directory, or None if unset."""
    raw = os.environ.get("RAG_INGEST_DIR")
    if not raw:
        return None
    return str(Path(raw).expanduser())
