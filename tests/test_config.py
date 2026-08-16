"""Tests for rag_mcp.config module."""
from pathlib import Path

import pytest

import rag_mcp.config as config


def _write_config(tmp_path: Path, text: str) -> str:
    """Write text to tmp_path/config.toml and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(text)
    return str(path)


def _no_default_config(monkeypatch, tmp_path: Path) -> None:
    """Point the default config location at an empty tmp dir."""
    monkeypatch.setattr(
        config.platformdirs, "user_config_dir", lambda *a, **k: str(tmp_path / "cfg")
    )


def test_load_config_defaults(monkeypatch, tmp_path):
    """No config file and no env vars yields built-in defaults."""
    _no_default_config(monkeypatch, tmp_path)
    cfg = config.load_config(environ={})
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.ollama_model == "nomic-embed-text"
    assert cfg.ingest_dir is None
    assert cfg.ingest_collection == "default"
    assert cfg.chroma_persist_dir.endswith("chroma_data")


def test_load_config_reads_toml(tmp_path):
    """Values come from the config file."""
    notes = tmp_path / "notes"
    notes.mkdir()
    db = tmp_path / "db"
    toml = (
        "[ollama]\n"
        'host = "http://ollama:9999"\n'
        'model = "mxbai-embed-large"\n'
        "[chroma]\n"
        f'persist_dir = "{db}"\n'
        "[ingest]\n"
        f'directory = "{notes}"\n'
        'collection = "docs"\n'
    )
    cfg = config.load_config(config_path=_write_config(tmp_path, toml), environ={})
    assert cfg.ollama_host == "http://ollama:9999"
    assert cfg.ollama_model == "mxbai-embed-large"
    assert cfg.chroma_persist_dir == str(db)
    assert cfg.ingest_dir == str(notes)
    assert cfg.ingest_collection == "docs"


def test_env_overrides_file(tmp_path):
    """RAG_MCP_* env vars take precedence over the config file."""
    path = _write_config(
        tmp_path, '[ollama]\nhost = "http://file-host"\nmodel = "file-model"\n'
    )
    cfg = config.load_config(
        config_path=path,
        environ={
            "RAG_MCP_OLLAMA_HOST": "http://env-host",
            "RAG_MCP_OLLAMA_MODEL": "env-model",
        },
    )
    assert cfg.ollama_host == "http://env-host"
    assert cfg.ollama_model == "env-model"


def test_tilde_expansion(tmp_path, monkeypatch):
    """~ in paths is expanded using HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "notes").mkdir()
    path = _write_config(
        tmp_path,
        '[chroma]\npersist_dir = "~/db"\n[ingest]\ndirectory = "~/notes"\n',
    )
    cfg = config.load_config(config_path=path)
    assert cfg.chroma_persist_dir == str(tmp_path / "db")
    assert cfg.ingest_dir == str(tmp_path / "notes")


def test_rag_mcp_config_missing_file_raises(tmp_path):
    """Explicit RAG_MCP_CONFIG pointing at a missing file raises ValueError."""
    with pytest.raises(ValueError):
        config.load_config(
            config_path=None,
            environ={"RAG_MCP_CONFIG": str(tmp_path / "nope.toml")},
        )


def test_invalid_toml_raises(tmp_path):
    """Malformed TOML raises ValueError."""
    path = tmp_path / "bad.toml"
    path.write_text("this is not [valid toml")
    with pytest.raises(ValueError):
        config.load_config(config_path=str(path), environ={})


def test_invalid_host_raises(tmp_path):
    """A non-URL ollama host raises ValueError."""
    path = _write_config(tmp_path, '[ollama]\nhost = "not a url"\n')
    with pytest.raises(ValueError):
        config.load_config(config_path=path, environ={})


def test_empty_model_raises(tmp_path):
    """An empty ollama model raises ValueError."""
    path = _write_config(tmp_path, '[ollama]\nmodel = ""\n')
    with pytest.raises(ValueError):
        config.load_config(config_path=path, environ={})


def test_missing_ingest_dir_raises(tmp_path):
    """An ingest directory that does not exist raises ValueError."""
    missing = tmp_path / "nope"
    path = _write_config(tmp_path, f'[ingest]\ndirectory = "{missing}"\n')
    with pytest.raises(ValueError):
        config.load_config(config_path=path, environ={})


def test_get_config_caches(monkeypatch, tmp_path):
    """get_config() loads once and returns the cached instance."""
    monkeypatch.setattr(config, "_config", None)
    _no_default_config(monkeypatch, tmp_path)
    assert config.get_config() is config.get_config()
