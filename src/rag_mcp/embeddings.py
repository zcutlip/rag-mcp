"""Ollama embedding client for the RAG MCP server."""
from typing import Any

import ollama


def get_embeddings(texts: list[str], host: str, model: str) -> list[list[float]]:
    """Return embeddings for a list of texts using Ollama.

    Args:
        texts: Document or query strings to embed.
        host: Ollama API endpoint.
        model: Embedding model name.

    Returns:
        A list of embedding vectors, one per input string.
    """
    if not texts:
        return []

    try:
        response: Any = ollama.embed(model=model, input=texts, host=host)
    except TypeError:
        # ollama >= 0.4 doesn't accept host as a kwarg on embed();
        # configure it via the Client constructor instead.
        client = ollama.Client(host=host)
        response = client.embed(model=model, input=texts)
    return response.embeddings
