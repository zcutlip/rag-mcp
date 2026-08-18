"""Tests for rag_mcp.config module."""
from pathlib import Path

import pytest

from rag_mcp import config


def _write_project_config(directory: Path, text: str) -> Path:
    """Write a .rag-mcp.toml in ``directory`` and return its path."""
    path = directory / config.PROJECT_CONFIG_FILENAME
    path.write_text(text)
    return path


def _write_global_config(directory: Path, text: str) -> Path:
    """Write a config.toml under ``directory`` and return its path."""
    path = directory / "config.toml"
    path.write_text(text)
    return path


def _no_default_config(monkeypatch, tmp_path: Path) -> None:
    """Point the default global config location at an empty tmp dir."""
    monkeypatch.setattr(
        config.platformdirs, "user_config_dir", lambda *a, **k: str(tmp_path / "cfg")
    )


def _no_project_config(monkeypatch, tmp_path: Path) -> None:
    """Point cwd at a tmp dir with no project config."""
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    monkeypatch.chdir(empty)


def test_load_config_defaults_with_project_file(monkeypatch, tmp_path):
    """Project file provides persist_dir; embeddings/ingest fall back to built-in defaults."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    _write_project_config(tmp_path, f'[chroma]\npersist_dir = "{db}"\n')
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(environ={})
    assert cfg.embeddings_host == "http://localhost:11434"
    assert cfg.embeddings_model == "nomic-embed-text"
    assert cfg.chroma_persist_dir == str(db)
    assert cfg.ingest_dir is None
    assert cfg.ingest_collection == "default"


def test_missing_persist_dir_raises(monkeypatch, tmp_path):
    """No project file and no env raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="chroma.persist_dir"):
        config.load_config(environ={})


def test_global_embeddings_overrides_defaults(monkeypatch, tmp_path):
    """Global config.toml supplies [embeddings]; chroma comes from project file."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    global_path = _write_global_config(
        tmp_path,
        '[embeddings]\nhost = "http://global-host"\nmodel = "global-model"\n',
    )
    _write_project_config(tmp_path, f'[chroma]\npersist_dir = "{db}"\n')
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(config_path=str(global_path), environ={})
    assert cfg.embeddings_host == "http://global-host"
    assert cfg.embeddings_model == "global-model"
    assert cfg.chroma_persist_dir == str(db)


def test_global_chroma_ignored(monkeypatch, tmp_path):
    """[chroma] in global config.toml is ignored; project file is required."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    global_path = _write_global_config(
        tmp_path, f'[chroma]\npersist_dir = "{db}"\n'
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="chroma.persist_dir"):
        config.load_config(config_path=str(global_path), environ={})


def test_project_embeddings_overrides_global(monkeypatch, tmp_path):
    """Project [embeddings] overrides global [embeddings]."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    global_path = _write_global_config(
        tmp_path, '[embeddings]\nhost = "http://global"\nmodel = "global"\n'
    )
    _write_project_config(
        tmp_path,
        f'[embeddings]\nmodel = "project-model"\n[chroma]\npersist_dir = "{db}"\n',
    )
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(config_path=str(global_path), environ={})
    assert cfg.embeddings_host == "http://global"
    assert cfg.embeddings_model == "project-model"


def test_env_overrides_project_and_global(monkeypatch, tmp_path):
    """RAG_MCP_* env vars beat both config files."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    global_path = _write_global_config(
        tmp_path, '[embeddings]\nhost = "http://global"\nmodel = "global"\n'
    )
    _write_project_config(
        tmp_path,
        f'[embeddings]\nmodel = "project-model"\n[chroma]\npersist_dir = "{db}"\n',
    )
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(
        config_path=str(global_path),
        environ={
            "RAG_MCP_EMBEDDINGS_HOST": "http://env-host",
            "RAG_MCP_EMBEDDINGS_MODEL": "env-model",
        },
    )
    assert cfg.embeddings_host == "http://env-host"
    assert cfg.embeddings_model == "env-model"


def test_env_provides_persist_dir_without_project_file(monkeypatch, tmp_path):
    """An env var can satisfy persist_dir without a project file."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"

    cfg = config.load_config(
        environ={"RAG_MCP_CHROMA_PERSIST_DIR": str(db)},
    )
    assert cfg.chroma_persist_dir == str(db)


def test_project_config_discovered_via_cwd_walk_up(monkeypatch, tmp_path):
    """A .rag-mcp.toml in an ancestor directory is discovered."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    _write_project_config(tmp_path, f'[chroma]\npersist_dir = "{db}"\n')

    sub = tmp_path / "sub" / "deeper"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)

    cfg = config.load_config(environ={})
    assert cfg.chroma_persist_dir == str(db)


def test_project_config_not_found_no_walk_up_match(monkeypatch, tmp_path):
    """With no project file anywhere in the walk-up, config requires env vars."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="chroma.persist_dir"):
        config.load_config(environ={})


def test_relative_persist_dir_resolves_to_project_root(monkeypatch, tmp_path):
    """A relative persist_dir in the project file resolves under the project root."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    _write_project_config(tmp_path, '[chroma]\npersist_dir = "./store"\n')
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(environ={})
    assert cfg.chroma_persist_dir == str((tmp_path / "store").resolve())


def test_relative_ingest_dir_resolves_to_project_root(monkeypatch, tmp_path):
    """A relative ingest directory resolves under the project root."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_project_config(
        tmp_path,
        '[chroma]\npersist_dir = "./store"\n[ingest]\ndirectory = "./docs"\n',
    )
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(environ={})
    assert cfg.ingest_dir == str(docs.resolve())


def test_relative_path_escaping_project_root_raises(monkeypatch, tmp_path):
    """A relative path outside the project root raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    _write_project_config(tmp_path, '[chroma]\npersist_dir = "../escape"\n')
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="escapes project root"):
        config.load_config(environ={})


def test_relative_env_persist_dir_without_project_root_raises(monkeypatch, tmp_path):
    """A relative RAG_MCP_CHROMA_PERSIST_DIR with no project file raises."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="requires a project root"):
        config.load_config(environ={"RAG_MCP_CHROMA_PERSIST_DIR": "./db"})


def test_absolute_path_works_without_project_file(monkeypatch, tmp_path):
    """An absolute path env var works even without a project file."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"

    cfg = config.load_config(
        environ={"RAG_MCP_CHROMA_PERSIST_DIR": str(db)},
    )
    assert cfg.chroma_persist_dir == str(db.resolve())


def test_tilde_expansion_in_project_file(monkeypatch, tmp_path):
    """~ in the project file's persist_dir expands using HOME."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    home_db = tmp_path / "db"
    _write_project_config(tmp_path, '[chroma]\npersist_dir = "~/db"\n')
    monkeypatch.chdir(tmp_path)

    cfg = config.load_config(environ={})
    assert cfg.chroma_persist_dir == str(home_db)


def test_tilde_expansion_in_env(monkeypatch, tmp_path):
    """~ in RAG_MCP_CHROMA_PERSIST_DIR expands using HOME."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    home_db = tmp_path / "db"

    cfg = config.load_config(
        environ={"RAG_MCP_CHROMA_PERSIST_DIR": "~/db"},
    )
    assert cfg.chroma_persist_dir == str(home_db)


def test_rag_mcp_config_missing_file_raises(tmp_path):
    """Explicit RAG_MCP_CONFIG pointing at a missing file raises ValueError."""
    with pytest.raises(ValueError):
        config.load_config(
            config_path=None,
            environ={"RAG_MCP_CONFIG": str(tmp_path / "nope.toml")},
        )


def test_invalid_global_toml_raises(tmp_path):
    """Malformed global TOML raises ValueError."""
    path = tmp_path / "bad.toml"
    path.write_text("this is not [valid toml")
    with pytest.raises(ValueError):
        config.load_config(config_path=str(path), environ={})


def test_invalid_project_toml_raises(monkeypatch, tmp_path):
    """Malformed project TOML raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    _write_project_config(tmp_path, "this is not [valid toml")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError):
        config.load_config(environ={})


def test_invalid_host_raises(monkeypatch, tmp_path):
    """A non-URL embeddings host raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    _write_project_config(
        tmp_path,
        f'[embeddings]\nhost = "not a url"\n[chroma]\npersist_dir = "{db}"\n',
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError):
        config.load_config(environ={})


def test_empty_model_raises(monkeypatch, tmp_path):
    """An empty embeddings model raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    _write_project_config(
        tmp_path,
        f'[embeddings]\nmodel = ""\n[chroma]\npersist_dir = "{db}"\n',
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError):
        config.load_config(environ={})


def test_missing_ingest_dir_raises(monkeypatch, tmp_path):
    """An ingest directory that does not exist raises ValueError."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    missing = tmp_path / "nope"
    _write_project_config(
        tmp_path,
        f'[chroma]\npersist_dir = "{db}"\n[ingest]\ndirectory = "{missing}"\n',
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError):
        config.load_config(environ={})


def test_get_config_caches(monkeypatch, tmp_path):
    """get_config() loads once and returns the cached instance."""
    _no_default_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    db = tmp_path / "db"
    _write_project_config(tmp_path, f'[chroma]\npersist_dir = "{db}"\n')
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(config, "_config", None)
    assert config.get_config() is config.get_config()
