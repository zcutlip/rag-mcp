# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-15

### Added

- Initial public release.
- MCP server exposing RAG tools: `add_documents`, `query_documents`, `list_collections`, `delete_collection`, and `sync_directory`.
- Ollama-backed embeddings with configurable host (`OLLAMA_HOST`) and model (`OLLAMA_MODEL`).
- ChromaDB persistence with a platform-appropriate default state location (`platformdirs`).
- Incremental markdown directory sync, including `RAG_INGEST_DIR` startup auto-sync.
- MIT license, PyPI-ready package metadata, and GitHub Actions CI.

[0.1.0]: https://github.com/zcutlip/rag-mcp/releases/tag/v0.1.0