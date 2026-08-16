# rag-mcp — Public Distribution Spec

Version 0.1.0 · 2026-08-15

## Objective

Prepare `rag-mcp` for public distribution as a GitHub-hosted open-source project. This spec covers only repository **content** changes. Repo creation (`zcutlip/rag-mcp`, public, empty, no push) is a separate step performed outside this spec, and the initial push is performed by the repository owner.

## Scope

### In scope

- MIT license
- Full PyPI-ready package metadata in `pyproject.toml` (distributed via `pipx install git+https://…`, but metadata is written to PyPI standards)
- Platform-appropriate default state location via `platformdirs`
- Input-validation hardening (`n_results`, `delete_collection`)
- A `__version__` export with single-source-of-truth wiring
- CI workflow (GitHub Actions)
- README refresh (install path, license, state location, badges)
- Pre-commit / `.gitignore` housekeeping
- CHANGELOG
- Tests for all new logic, written test-first (TDD)

### Out of scope

- Repo creation and initial push (owner performs the push)
- Publishing to PyPI
- Functional/feature changes beyond the hardening listed above
- Refactoring the module-level `store` singleton (see Risks)

## Locked Decisions

| Item | Decision |
|---|---|
| License | MIT, `Copyright (c) 2026 Zachary Cutlip` |
| Repo | `zcutlip/rag-mcp`, public |
| Python floor | `>=3.12`; CI matrix `3.12` / `3.13` / `3.14` |
| Version | `0.1.0`, single-sourced from `rag_mcp.__version__` |
| State location | `platformdirs` per-OS user-data dir; `CHROMA_PERSIST_DIR` override with `~` expansion |
| Dependencies | `mcp>=2,<3`, `ollama>=0.4`, `chromadb>=1.5`, add `platformdirs>=4` |
| Install path | `pipx install git+https://github.com/zcutlip/rag-mcp.git` (PyPI later) |
| Verification gate | `pre-commit run --all-files`, `pytest`, `python -m build` |

## File-by-File Changes

### 1. `LICENSE` (new)

Standard MIT license text, `Copyright (c) 2026 Zachary Cutlip`.

### 2. `pyproject.toml`

Bump the build-system floor to `setuptools>=77` (required for the SPDX `license = "MIT"` string form and `license-files`). Target `[project]` table:

```toml
[project]
name = "rag-mcp"
dynamic = ["version"]
description = "MCP server exposing RAG tools backed by Ollama embeddings and ChromaDB"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Zachary Cutlip", email = "uid000@inode.link" }]
keywords = ["mcp", "rag", "retrieval-augmented-generation", "ollama", "chromadb", "embeddings", "vector-store"]
dependencies = [
    "mcp>=2,<3",
    "ollama>=0.4",
    "chromadb>=1.5",
    "platformdirs>=4",
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: Text Processing",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pre-commit",
    "build",
]

[project.scripts]
rag-mcp = "rag_mcp.server:main"

[project.urls]
Homepage = "https://github.com/zcutlip/rag-mcp"
Repository = "https://github.com/zcutlip/rag-mcp"
Issues = "https://github.com/zcutlip/rag-mcp/issues"
```

Note: omit the `License :: OSI Approved :: MIT License` classifier — setuptools>=77 (PEP 639) rejects it when `license = "MIT"` is present (`InvalidConfigError`).

Add the version single-source wiring:

```toml
[tool.setuptools.dynamic]
version = { attr = "rag_mcp.__version__" }
```

Keep `[tool.setuptools.packages.find]` and `[tool.pytest.ini_options]` unchanged.

### 3. `src/rag_mcp/__init__.py`

Add the version and export it:

```python
"""RAG MCP server package."""

__version__ = "0.1.0"

__all__ = ["__version__"]
```

### 4. `src/rag_mcp/config.py` (new)

Environment-backed configuration, matching the repo's env-at-point-of-use style:

```python
"""Environment-backed configuration for the RAG MCP server."""
import os
from pathlib import Path

import platformdirs


def get_persist_dir() -> str:
    """Return the ChromaDB persistence directory.

    Honors CHROMA_PERSIST_DIR (with ``~`` expansion) if set; otherwise
    defaults to the platform user-data directory.
    """
    raw = os.environ.get("CHROMA_PERSIST_DIR")
    if raw:
        return str(Path(raw).expanduser())
    return str(Path(platformdirs.user_data_dir("rag-mcp", appauthor=False)) / "chroma_data")


def get_ingest_dir() -> str | None:
    """Return the startup auto-ingest directory, or None if unset."""
    raw = os.environ.get("RAG_INGEST_DIR")
    if not raw:
        return None
    return str(Path(raw).expanduser())
```

Default results per OS:

| OS | Default `get_persist_dir()` |
|---|---|
| macOS | `~/Library/Application Support/rag-mcp/chroma_data` |
| Linux | `~/.local/share/rag-mcp/chroma_data` |
| Windows | `%LOCALAPPDATA%\rag-mcp\chroma_data` |

### 5. `src/rag_mcp/server.py`

- Replace the module-level `store` construction:
  `store = VectorStore(persist_dir=get_persist_dir())`
- In `main()`, replace the inline env reads with `get_ingest_dir()` (still gated inside `main()` — no filesystem/Ollama side effects on import). `RAG_INGEST_COLLECTION` read stays inline (or move alongside if trivially clean).
- **`query_documents` hardening:** raise `ValueError("n_results must be >= 1")` when `n_results < 1`, before any embedding call.
- **`delete_collection` hardening:** raise `ValueError(f"Collection '{collection}' does not exist.")` when the collection is absent (guard via `store.list_collections()`), before calling `store.delete_collection`.

### 6. `README.md`

- Install section: primary path `pipx install git+https://github.com/zcutlip/rag-mcp.git` (and `pip install git+https://…` for non-pipx); note `pipx install rag-mcp` as "once published to PyPI".
- Add a License section (MIT) and MIT badge.
- Document the new default state location per OS, and that `CHROMA_PERSIST_DIR` overrides it.
- Add a CI status badge.

### 7. `.github/workflows/ci.yml` (new)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pre-commit run --all-files
      - run: pytest
      - run: python -m build
```

### 8. `.pre-commit-config.yaml` + `setup.cfg`

- Keep `pyupgrade --py312-plus` (now correct, since the floor is 3.12).
- Remove the `ci: autoupdate_branch: 'development'` block (that branch does not exist).
- Add `setup.cfg` setting `max-line-length = 100` under both `[flake8]` and `[pycodestyle]` — the repo ships no line-length config, so flake8's 79-char default trips on the existing code; 100 aligns flake8 and autopep8 with the existing style.

### 9. `.gitignore`

- Add `.opencode/` (whole directory), replacing the lone `.opencode/index` entry.

### 10. `CHANGELOG.md` (new)

`0.1.0` entry describing initial public release (RAG MCP server: `add_documents`, `query_documents`, `list_collections`, `delete_collection`, `sync_directory`; Ollama embeddings; ChromaDB persistence).

## Tests (TDD)

All testable changes are written **test-first** (red → green → refactor). No existing test is modified.

### New test files

**`tests/test_config.py`** — 4 tests:

- `test_get_persist_dir_default`: with `platformdirs.user_data_dir` mocked and `CHROMA_PERSIST_DIR` unset, returns `<user_data_dir>/chroma_data`.
- `test_get_persist_dir_env_override`: `CHROMA_PERSIST_DIR=~/my_db` returns the `~`-expanded path.
- `test_get_ingest_dir_unset`: unset → `None`.
- `test_get_ingest_dir_set`: `RAG_INGEST_DIR=~/notes` returns the expanded path.

Use `monkeypatch` for env isolation and `patch` for `platformdirs.user_data_dir`.

**`tests/test_version.py`** — 1 test:

- `test_version_is_semver`: `rag_mcp.__version__` is a non-empty string matching `^\d+\.\d+\.\d+$`.

### Added tests (existing file `tests/test_server.py`)

- `test_query_documents_validation`: `query_documents(query="x", n_results=0)` raises `ValueError`; `get_embeddings` and `store.query` are not called.
- `test_delete_collection_missing`: `delete_collection(collection="missing")` (with `mock_store.list_collections` returning `["default"]`) raises `ValueError`; `mock_store.delete_collection` not called.

### TDD ordering

1. Write `tests/test_config.py` + `tests/test_version.py` + the two server tests → all fail (missing module / missing attribute / behavior not yet present).
2. Implement `config.py`, `__version__`, and the two server guards → green.
3. Existing 21 tests must remain green throughout.

## Acceptance Criteria

- `pre-commit run --all-files` passes.
- `pytest` passes: 21 existing + 7 new = 28 tests.
- `python -m build` produces a wheel and sdist with the README and LICENSE included; metadata resolves `version` from `rag_mcp.__version__`.
- Fresh `pipx install git+https://github.com/zcutlip/rag-mcp.git` (or local equivalent) creates the ChromaDB under `~/Library/Application Support/rag-mcp/chroma_data` (macOS), not the CWD.

## Risks & Known Considerations

- **Import-time side effect:** `server.py` instantiates `store` at module import, so importing `rag_mcp.server` (which tests do) creates the ChromaDB dir. Today that is `./chroma_data`; after this change it becomes the user-data dir. Harmless (empty client, no collection), but noted. Optional non-required fix: mock `rag_mcp.server.VectorStore` in `tests/conftest.py` so import doesn't instantiate. Deferred; not part of this spec's core work.
- **`platformdirs` API:** `appauthor=False` is required so macOS yields `~/Library/Application Support/rag-mcp` (not a vendor-subdirectory variant).
- **Dependency floor `chromadb>=1.5`:** tested against installed 1.5.9 (Rust-bindings line). Older majors (pre-1.x) are not supported by these bounds.

## Execution Order

1. Tests (TDD, red).
2. `config.py`, `__version__`, `server.py` guards (green).
3. `LICENSE`, `pyproject.toml` metadata + dynamic version, `README.md`.
4. `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.gitignore`.
5. `CHANGELOG.md`.
6. Verify: pre-commit + pytest + build.
7. Tag `v0.1.0` and create the GitHub release (after owner pushes).
