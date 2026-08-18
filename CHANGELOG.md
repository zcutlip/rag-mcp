# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- TOML-based configuration file with `RAG_MCP_*` environment variable overrides and fail-fast validation.
- Project-local `.rag-mcp.toml` config, discovered by walking up from the current working directory. Relative paths resolve against the project root and are constrained to it.
- `rag-mcp-config` CLI utility with `init` subcommand that writes starter global and project config files. Idempotent: skips existing files with a note.
- `rag-mcp-config init` reports the path of each file it writes or skips.
- `rag-mcp readme` prints the installed project README for agents and users without starting the MCP server.
- Server metadata (title, description, version, instructions) helps agents discover and understand the server's purpose
- `rag://readme` resource exposes the project README for agents to read at runtime
- `query_documents` tool description explicitly identifies it as the primary tool for answering questions about the indexed corpus

### Changed

- **Breaking:** Replaced the `OLLAMA_HOST`, `OLLAMA_MODEL`, `CHROMA_PERSIST_DIR`, and `RAG_INGEST_DIR` environment variables with `RAG_MCP_*`-prefixed names (see the README).
- **Breaking:** `chroma.persist_dir` is now required; it no longer defaults to a platform user-data directory. Configure it in `.rag-mcp.toml` or via `RAG_MCP_CHROMA_PERSIST_DIR`.
- **Breaking:** Global `config.toml` reads only `[embeddings]` defaults; `[chroma]` and `[ingest]` keys there are ignored. Project-specific data belongs in `.rag-mcp.toml`.
- **Breaking:** Renamed the `[ollama]` config section to `[embeddings]` and the matching env vars `RAG_MCP_OLLAMA_HOST` / `RAG_MCP_OLLAMA_MODEL` to `RAG_MCP_EMBEDDINGS_HOST` / `RAG_MCP_EMBEDDINGS_MODEL`. The config-section rename is provider-neutral in preparation for supporting additional embedding providers; the env-var rename reflects the same.
- `rag-mcp --help` now prints usage without starting the server, and startup configuration errors are reported on stderr with initialization guidance instead of a traceback.
- Directory ingestion now receives the configured embedding host and model consistently for both MCP-triggered and startup auto-ingestion.

## [0.1.0] - 2026-08-15

### Added

- Initial public release.
- MCP server exposing RAG tools: `add_documents`, `query_documents`, `list_collections`, `delete_collection`, and `sync_directory`.
- Ollama-backed embeddings with configurable host (`OLLAMA_HOST`) and model (`OLLAMA_MODEL`).
- ChromaDB persistence with a platform-appropriate default state location (`platformdirs`).
- Incremental markdown directory sync, including `RAG_INGEST_DIR` startup auto-sync.
- MIT license, PyPI-ready package metadata, and GitHub Actions CI.

[0.1.0]: https://github.com/zcutlip/rag-mcp/releases/tag/v0.1.0
