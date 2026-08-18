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

PROJECT_CONFIG_FILENAME = ".rag-mcp.toml"


def default_config_path() -> str:
    """Return the default config file path (which may not exist)."""
    return str(
        Path(platformdirs.user_config_dir("rag-mcp", appauthor=False)) / "config.toml"
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


def _find_project_config_path(cwd: str | None = None) -> str | None:
    """Walk up from ``cwd`` looking for ``.rag-mcp.toml``.

    Returns the first matching path or ``None``.
    """
    start = Path(cwd or os.getcwd()).resolve()
    for directory in [start, *start.parents]:
        candidate = directory / PROJECT_CONFIG_FILENAME
        if candidate.is_file():
            return str(candidate)
    return None


def _resolve_path(value: str, root: str | None) -> str:
    """Expand ``~`` and resolve ``value``.

    Absolute paths are returned resolved. Relative paths require a project
    ``root``; they are joined to ``root``, resolved, and validated to ensure
    they stay within ``root``. Raises ``ValueError`` if the path escapes
    the root or if a relative path is supplied without one.
    """
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return str(expanded.resolve())
    if root is None:
        raise ValueError(
            f"Relative path requires a project root: {value!r}"
        )
    resolved = (Path(root) / expanded).resolve()
    root_resolved = Path(root).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"Path escapes project root: {value!r}")
    return str(resolved)


def _load_global_config(
    config_path: str | None, environ: Mapping[str, str]
) -> dict:
    """Resolve and load the global ``config.toml``."""
    explicit = config_path is not None
    if config_path is None:
        config_path = environ.get("RAG_MCP_CONFIG")
        if config_path is None:
            config_path = default_config_path()
        else:
            explicit = True

    path = Path(config_path)
    if path.exists():
        return _parse_toml(str(path))
    if explicit:
        raise ValueError(f"Config file not found: {path}")
    return {}


def load_config(
    config_path: str | None = None, environ: Mapping[str, str] = os.environ
) -> Config:
    """Load configuration from a global TOML, project ``.rag-mcp.toml``, and env overrides.

    The global file contributes only ``[ollama]`` (host/model). The project
    file, discovered by walking up from the current working directory,
    contributes ``[ollama]``, ``[chroma]``, and ``[ingest]``. Environment
    variables override anything from the files.

    Precedence: built-in defaults < global file < project file < env vars.

    ``chroma.persist_dir`` is required: it must be set in the project file
    or via ``RAG_MCP_CHROMA_PERSIST_DIR``. Relative paths in the project
    file are resolved against the project root and must stay within it.

    Args:
        config_path: Explicit path to the global config file. If ``None``,
            resolved from ``RAG_MCP_CONFIG`` or the platform default.
        environ: Environment mapping to read ``RAG_MCP_*`` overrides from.

    Raises:
        ValueError: If an explicitly-requested config file is missing, the
            file is malformed, any resolved value fails validation, or
            ``chroma.persist_dir`` is not configured.
    """
    global_data = _load_global_config(config_path, environ)
    ollama_from_global = global_data.get("ollama", {})

    project_path = _find_project_config_path()
    project_data: dict = {}
    project_root: str | None = None
    if project_path is not None:
        project_data = _parse_toml(project_path)
        project_root = str(Path(project_path).parent.resolve())

    ollama = {
        "host": DEFAULT_OLLAMA_HOST,
        "model": DEFAULT_OLLAMA_MODEL,
        **ollama_from_global,
        **project_data.get("ollama", {}),
    }
    ollama_host = environ.get("RAG_MCP_OLLAMA_HOST", ollama["host"])
    ollama_model = environ.get("RAG_MCP_OLLAMA_MODEL", ollama["model"])

    chroma = project_data.get("chroma", {})
    ingest = project_data.get("ingest", {})

    persist_dir_raw = environ.get(
        "RAG_MCP_CHROMA_PERSIST_DIR", chroma.get("persist_dir", "")
    )
    persist_dir = (
        _resolve_path(persist_dir_raw, project_root) if persist_dir_raw else ""
    )

    ingest_dir_raw = environ.get("RAG_MCP_INGEST_DIR", ingest.get("directory", ""))
    ingest_dir = (
        _resolve_path(ingest_dir_raw, project_root) if ingest_dir_raw else None
    )

    ingest_collection = environ.get(
        "RAG_MCP_INGEST_COLLECTION",
        ingest.get("collection", DEFAULT_INGEST_COLLECTION),
    )

    _validate_host(ollama_host)
    if not ollama_model or not ollama_model.strip():
        raise ValueError("ollama.model must be a non-empty string")
    if not persist_dir or not persist_dir.strip():
        raise ValueError(
            "chroma.persist_dir must be configured in .rag-mcp.toml "
            "or via RAG_MCP_CHROMA_PERSIST_DIR"
        )
    if not ingest_collection or not ingest_collection.strip():
        raise ValueError("ingest.collection must be a non-empty string")
    if ingest_dir is not None and not Path(ingest_dir).is_dir():
        raise ValueError(f"ingest.directory does not exist: {ingest_dir}")

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
