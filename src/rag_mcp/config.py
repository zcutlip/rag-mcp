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
    embeddings_host: str
    embeddings_model: str
    chroma_persist_dir: str
    ingest_dir: str | None
    ingest_collection: str
    ingest_patterns: list[str] | None = None
    ingest_watch: bool = True
    ingest_watch_interval: int = 30


DEFAULT_EMBEDDINGS_HOST = "http://localhost:11434"
DEFAULT_EMBEDDINGS_MODEL = "nomic-embed-text"
DEFAULT_INGEST_COLLECTION = "default"
DEFAULT_INGEST_WATCH_INTERVAL = 30

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
        raise ValueError(f"embeddings.host must be a valid http(s) URL: {host}")


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


def _parse_watch_bool(environ: Mapping[str, str]) -> bool | None:
    """Parse the ``RAG_MCP_INGEST_WATCH`` env override.

    Returns ``None`` when the variable is unset. Accepts only
    ``true``/``false`` (case-insensitive); anything else is a ``ValueError``.
    """
    raw = environ.get("RAG_MCP_INGEST_WATCH")
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(
        f"RAG_MCP_INGEST_WATCH must be 'true' or 'false', got: {raw!r}"
    )


def _parse_watch_interval(
    raw: str | int, source: str
) -> int:
    """Validate a watch interval from TOML (int) or env (string).

    Returns the interval when it is a positive integer; raises ``ValueError``
    otherwise. ``source`` names the config key for error messages
    (``ingest.watch_interval`` for both TOML and env values).
    """
    if isinstance(raw, bool):
        raise ValueError(f"{source} must be a positive integer: {raw!r}")
    if isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(
                f"{source} must be a positive integer: {raw!r}"
            ) from None
    elif isinstance(raw, int):
        value = raw
    else:
        raise ValueError(f"{source} must be a positive integer: {raw!r}")
    if value <= 0:
        raise ValueError(f"{source} must be a positive integer: {raw!r}")
    return value


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

    The global file contributes only ``[embeddings]`` (host/model). The project
    file, discovered by walking up from the current working directory,
    contributes ``[embeddings]``, ``[chroma]``, and ``[ingest]``. Environment
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
    # ingest.patterns is project-local only — reject if present in global config
    _global_ingest = global_data.get("ingest")
    if isinstance(_global_ingest, dict) and "patterns" in _global_ingest:
        raise ValueError(
            "ingest.patterns is project-local and cannot be set in global config"
        )
    embeddings_from_global = global_data.get("embeddings", {})

    project_path = _find_project_config_path()
    project_data: dict = {}
    project_root: str | None = None
    if project_path is not None:
        project_data = _parse_toml(project_path)
        project_root = str(Path(project_path).parent.resolve())

    embeddings = {
        "host": DEFAULT_EMBEDDINGS_HOST,
        "model": DEFAULT_EMBEDDINGS_MODEL,
        **embeddings_from_global,
        **project_data.get("embeddings", {}),
    }
    embeddings_host = environ.get("RAG_MCP_EMBEDDINGS_HOST", embeddings["host"])
    embeddings_model = environ.get("RAG_MCP_EMBEDDINGS_MODEL", embeddings["model"])

    chroma = project_data.get("chroma", {})
    ingest = project_data.get("ingest", {})

    # Parse and validate ingest.patterns (project-local only)
    if not isinstance(ingest, dict) or "patterns" not in ingest:
        ingest_patterns: list[str] | None = None
    else:
        raw_patterns = ingest["patterns"]
        if not isinstance(raw_patterns, list):
            raise ValueError("ingest.patterns must be a list")
        for pat in raw_patterns:
            if not isinstance(pat, str):
                raise ValueError("ingest.patterns must be a list of strings")
            if pat == "" or pat == "!":
                raise ValueError(
                    "ingest.patterns must not contain empty string or bare '!'"
                )
            if pat.startswith("!"):
                remainder = pat[1:]
                if remainder == "" or remainder == "!":
                    raise ValueError(
                        "ingest.patterns must not contain empty string or bare '!'"
                    )
        ingest_patterns = raw_patterns

    # Watch settings: defaults, project TOML, env overrides (project-local [ingest])
    ingest_watch_env = _parse_watch_bool(environ)
    if ingest_watch_env is not None:
        ingest_watch = ingest_watch_env
    elif isinstance(ingest.get("watch", True), bool):
        ingest_watch = ingest["watch"] if "watch" in ingest else True
    else:
        raise ValueError(
            "ingest.watch must be a boolean: "
            f"{ingest.get('watch')!r}"
        )

    if "RAG_MCP_INGEST_WATCH_INTERVAL" in environ:
        ingest_watch_interval = _parse_watch_interval(
            environ["RAG_MCP_INGEST_WATCH_INTERVAL"], "ingest.watch_interval"
        )
    elif "watch_interval" in ingest:
        ingest_watch_interval = _parse_watch_interval(
            ingest["watch_interval"], "ingest.watch_interval"
        )
    else:
        ingest_watch_interval = DEFAULT_INGEST_WATCH_INTERVAL

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

    _validate_host(embeddings_host)
    if not embeddings_model or not embeddings_model.strip():
        raise ValueError("embeddings.model must be a non-empty string")
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
        embeddings_host=embeddings_host,
        embeddings_model=embeddings_model,
        chroma_persist_dir=persist_dir,
        ingest_dir=ingest_dir,
        ingest_collection=ingest_collection,
        ingest_patterns=ingest_patterns,
        ingest_watch=ingest_watch,
        ingest_watch_interval=ingest_watch_interval,
    )


_config: Config | None = None


def get_config() -> Config:
    """Return the cached config, loading it once on first access."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
