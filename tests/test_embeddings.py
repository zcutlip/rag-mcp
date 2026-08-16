"""Tests for rag_mcp.embeddings module."""
from unittest.mock import MagicMock, patch

from rag_mcp.embeddings import get_embeddings


def test_get_embeddings_empty_input():
    """Empty input returns [] without calling Ollama."""
    assert get_embeddings([], host="http://localhost:11434", model="nomic-embed-text") == []


@patch("rag_mcp.embeddings.ollama.embed")
def test_get_embeddings_success(mock_embed):
    """Returns embeddings and passes host/model to Ollama."""
    mock_embed.return_value = MagicMock(embeddings=[[0.1, 0.2]])
    result = get_embeddings(["hello"], host="http://myhost:1234", model="my-model")
    assert result == [[0.1, 0.2]]
    mock_embed.assert_called_once()
    assert mock_embed.call_args.kwargs["host"] == "http://myhost:1234"
    assert mock_embed.call_args.kwargs["model"] == "my-model"
