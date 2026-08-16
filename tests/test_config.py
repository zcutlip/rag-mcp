"""Tests for rag_mcp.config module."""
import os
from unittest.mock import patch

import rag_mcp.config as config


def test_get_persist_dir_default(monkeypatch):
    """Defaults to the platform user-data dir plus 'chroma_data'."""
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
    with patch(
        "rag_mcp.config.platformdirs.user_data_dir", return_value="/data/rag-mcp"
    ) as mock_ud:
        assert config.get_persist_dir() == "/data/rag-mcp/chroma_data"
    mock_ud.assert_called_once()


def test_get_persist_dir_env_override(monkeypatch):
    """CHROMA_PERSIST_DIR overrides the default and expands '~'."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "~/my_db")
    assert config.get_persist_dir() == os.path.expanduser("~/my_db")


def test_get_ingest_dir_unset(monkeypatch):
    """Unset RAG_INGEST_DIR returns None."""
    monkeypatch.delenv("RAG_INGEST_DIR", raising=False)
    assert config.get_ingest_dir() is None


def test_get_ingest_dir_set(monkeypatch):
    """RAG_INGEST_DIR returns the expanded path."""
    monkeypatch.setenv("RAG_INGEST_DIR", "~/notes")
    assert config.get_ingest_dir() == os.path.expanduser("~/notes")