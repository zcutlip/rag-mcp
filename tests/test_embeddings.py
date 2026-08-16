"""Tests for rag_mcp.embeddings module."""
from unittest.mock import MagicMock, patch

from rag_mcp.embeddings import get_embeddings


def test_get_embeddings_empty_input():
    """get_embeddings([]) returns [] without calling Ollama."""
    with patch("rag_mcp.embeddings.ollama.embed") as mock_embed:
        result = get_embeddings([])
        assert result == []
        mock_embed.assert_not_called()


def test_get_embeddings_success():
    """get_embeddings returns the embeddings from the Ollama response."""
    mock_response = MagicMock()
    mock_response.embeddings = [[0.1, 0.2], [0.3, 0.4]]

    with patch("rag_mcp.embeddings.ollama.embed", return_value=mock_response) as mock_embed:
        result = get_embeddings(["a", "b"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        mock_embed.assert_called_once_with(
            model="nomic-embed-text",
            input=["a", "b"],
            host="http://localhost:11434",
        )


def test_get_embeddings_custom_env(monkeypatch):
    """OLLAMA_HOST and OLLAMA_MODEL env vars override defaults."""
    monkeypatch.setenv("OLLAMA_HOST", "http://custom-host:2234")
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")

    mock_response = MagicMock()
    mock_response.embeddings = [[0.5, 0.6]]

    with patch("rag_mcp.embeddings.ollama.embed", return_value=mock_response) as mock_embed:
        get_embeddings(["test"])
        mock_embed.assert_called_once_with(
            model="custom-model",
            input=["test"],
            host="http://custom-host:2234",
        )
