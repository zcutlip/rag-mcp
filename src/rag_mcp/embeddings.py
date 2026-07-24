"""Ollama embedding client for the RAG MCP server."""
import os
from typing import Any

import ollama


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of texts using Ollama.

    Args:
        texts: Document or query strings to embed.

    Returns:
        A list of embedding vectors, one per input string.
    """
    if not texts:
        return []

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "nomic-embed-text")

    response: Any = ollama.embed(model=model, input=texts, host=host)
    return response.embeddings
