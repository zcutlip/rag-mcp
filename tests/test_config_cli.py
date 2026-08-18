"""Tests for rag_mcp._config_cli (the ``rag-mcp-config`` CLI)."""
from pathlib import Path

import pytest

from rag_mcp import _config_cli

GLOBAL_TEMPLATE = """\
# Global config for rag-mcp. See README for full reference.

[embeddings]
host = "http://localhost:11434"
model = "nomic-embed-text"
"""

PROJECT_TEMPLATE = """\
# Project-local config for rag-mcp. See README for full reference.

[chroma]
# Required: no platform-default fallback for the vector store location.
# Relative paths resolve under this directory and must stay within it.
persist_dir = "./.chroma"

[ingest]
# Optional: directory of .md/.markdown files to auto-sync into the collection
# at server startup. Must exist if set. Leave commented to skip auto-ingest.
# directory = "./docs"
collection = "default"
"""


def _no_global_config(monkeypatch, tmp_path: Path) -> Path:
    """Point the global config dir at a tmp path that does not exist yet."""
    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(
        _config_cli.platformdirs, "user_config_dir", lambda *a, **k: str(config_dir)
    )
    return config_dir


def _no_project_config(monkeypatch, tmp_path: Path) -> Path:
    """Point cwd at an empty tmp dir with no project config."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(project_dir)
    return project_dir


def _run_main(capsys, argv):
    """Run the CLI, returning (exit code, stdout, stderr)."""
    with pytest.raises(SystemExit) as exc_info:
        _config_cli.main(argv)
    captured = capsys.readouterr()
    return exc_info.value.code, captured.out, captured.err


def test_init_creates_global_when_missing(monkeypatch, tmp_path, capsys):
    """init writes both templates when neither file exists and exits 0."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)

    code, out, _ = _run_main(capsys, ["init"])

    assert code == 0
    global_path = tmp_path / "cfg" / "config.toml"
    assert global_path.read_text() == GLOBAL_TEMPLATE
    project_path = tmp_path / "proj" / ".rag-mcp.toml"
    assert project_path.read_text() == PROJECT_TEMPLATE
    assert str(global_path) in out
    assert str(project_path) in out


def test_init_creates_project_when_missing(monkeypatch, tmp_path, capsys):
    """init writes the project template to <cwd>/.rag-mcp.toml and exits 0."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)

    code, out, _ = _run_main(capsys, ["init"])

    assert code == 0
    global_path = tmp_path / "cfg" / "config.toml"
    assert global_path.read_text() == GLOBAL_TEMPLATE
    project_path = tmp_path / "proj" / ".rag-mcp.toml"
    assert project_path.read_text() == PROJECT_TEMPLATE
    assert str(global_path) in out
    assert str(project_path) in out


def test_init_skips_existing_global_with_note(monkeypatch, tmp_path, capsys):
    """init leaves an existing global config.toml untouched and notes the skip."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    global_path = tmp_path / "cfg" / "config.toml"
    global_path.parent.mkdir()
    global_path.write_text('host = "http://custom"\n')

    code, out, _ = _run_main(capsys, ["init"])

    assert code == 0
    assert global_path.read_text() == 'host = "http://custom"\n'
    assert "skip" in out.lower()
    assert "config.toml" in out


def test_init_skips_existing_project_with_note(monkeypatch, tmp_path, capsys):
    """init leaves an existing project .rag-mcp.toml untouched and notes the skip."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    project_path = tmp_path / "proj" / ".rag-mcp.toml"
    project_path.write_text('[chroma]\npersist_dir = "./custom"\n')

    code, out, _ = _run_main(capsys, ["init"])

    assert code == 0
    assert project_path.read_text() == '[chroma]\npersist_dir = "./custom"\n'
    assert "skip" in out.lower()
    assert ".rag-mcp.toml" in out


def test_init_creates_global_parent_dirs(monkeypatch, tmp_path, capsys):
    """init creates missing parent directories for the global config file."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    assert not (tmp_path / "cfg").exists()

    code, out, _ = _run_main(capsys, ["init"])

    assert code == 0
    assert (tmp_path / "cfg").is_dir()
    assert (tmp_path / "cfg" / "config.toml").is_file()
    assert str(tmp_path / "cfg" / "config.toml") in out
    assert str(tmp_path / "proj" / ".rag-mcp.toml") in out


def test_init_writes_project_to_cwd_no_walkup(monkeypatch, tmp_path, capsys):
    """init writes .rag-mcp.toml in cwd only; ancestor files stay untouched."""
    _no_global_config(monkeypatch, tmp_path)
    _no_project_config(monkeypatch, tmp_path)
    ancestor = tmp_path / ".rag-mcp.toml"
    ancestor.write_text('persist_dir = "./ancestor"\n')

    code, _, _ = _run_main(capsys, ["init"])

    assert code == 0
    project_path = tmp_path / "proj" / ".rag-mcp.toml"
    assert project_path.read_text() == PROJECT_TEMPLATE
    assert ancestor.read_text() == 'persist_dir = "./ancestor"\n'


def test_help_exits_zero(capsys):
    """--help prints usage to stdout and exits 0."""
    code, out, _ = _run_main(capsys, ["--help"])

    assert code == 0
    assert "usage" in out.lower()


def test_unknown_verb_errors(capsys):
    """An unknown verb prints usage to stderr and exits 2."""
    code, _, err = _run_main(capsys, ["bogus"])

    assert code == 2
    assert "usage" in err.lower()
