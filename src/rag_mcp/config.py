"""Environment- and file-backed configuration for the RAG MCP server."""
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import platformdirs


@dataclass(frozen=True)
class Config:
    ollama_host: str
    ollama_model: str
    chroma_persist_dir: str
    ingest_dir: str | None
    ingest_collection: str


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_INGEST_COLLECTION = "default"


def default_config_path() -> str:
    """Return the default config file path (which may not exist)."""
    return str(
        Path(platformdirs.user_config_dir("rag-mcp", appauthor=False)) / "config.toml"
    )


def _default_persist_dir() -> str:
    return str(
        Path(platformdirs.user_data_dir("rag-mcp", appauthor=False)) / "chroma_data"
    )


def _parse_toml(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in config file {path}: {exc}") from exc


def _validate_host(host: str) -> None:
    parsed = urlparse(host)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"ollama.host must be a valid http(s) URL: {host}")


def load_config(
    config_path: str | None = None, environ: Mapping[str, str] = os.environ
) -> Config:
    """Load configuration from a TOML file with env overrides, validating it.

    Args:
        config_path: Explicit path to the config file. If None, resolved from
            ``RAG_MCP_CONFIG`` or the platform default.
        environ: Environment mapping to read ``RAG_MCP_*`` overrides from.

    Raises:
        ValueError: If an explicitly-requested config file is missing, the
            file is malformed, or any resolved value fails validation.
    """
    explicit = config_path is not None
    if config_path is None:
        config_path = environ.get("RAG_MCP_CONFIG")
        if config_path is None:
            config_path = default_config_path()
        else:
            explicit = True

    path = Path(config_path)
    file_data: dict = {}
    if path.exists():
        file_data = _parse_toml(str(path))
    elif explicit:
        raise ValueError(f"Config file not found: {path}")

    ollama = file_data.get("ollama", {})
    chroma = file_data.get("chroma", {})
    ingest = file_data.get("ingest", {})

    ollama_host = environ.get(
        "RAG_MCP_OLLAMA_HOST", ollama.get("host", DEFAULT_OLLAMA_HOST)
    )
    ollama_model = environ.get(
        "RAG_MCP_OLLAMA_MODEL", ollama.get("model", DEFAULT_OLLAMA_MODEL)
    )
    persist_dir = environ.get("RAG_MCP_CHROMA_PERSIST_DIR", chroma.get("persist_dir", ""))
    ingest_dir = environ.get("RAG_MCP_INGEST_DIR", ingest.get("directory"))
    ingest_collection = environ.get(
        "RAG_MCP_INGEST_COLLECTION", ingest.get("collection", DEFAULT_INGEST_COLLECTION)
    )

    _validate_host(ollama_host)
    if not ollama_model or not ollama_model.strip():
        raise ValueError("ollama.model must be a non-empty string")
    if not ingest_collection or not ingest_collection.strip():
        raise ValueError("ingest.collection must be a non-empty string")

    if persist_dir:
        persist_dir = str(Path(persist_dir).expanduser())
    else:
        persist_dir = _default_persist_dir()

    if ingest_dir:
        ingest_dir = str(Path(ingest_dir).expanduser())
        if not Path(ingest_dir).is_dir():
            raise ValueError(f"ingest.directory does not exist: {ingest_dir}")
    else:
        ingest_dir = None

    return Config(
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        chroma_persist_dir=persist_dir,
        ingest_dir=ingest_dir,
        ingest_collection=ingest_collection,
    )


_config: Config | None = None


def get_config() -> Config:
    """Return the cached config, loading it once on first access."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
