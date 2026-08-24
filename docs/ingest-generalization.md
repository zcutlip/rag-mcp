# Ingest Generalization — Parked

> Date: 2026-08-20 — from corpus-change Q&A. Not building today, revisit when adding Bear.app / other non-filesystem sources.

## Current design

- Single entry: `src/rag_mcp/ingest.py:sync_directory` (95-201), invoked via MCP tool `sync_directory(directory)` (`server.py:193`) or startup auto-ingest (`server.py:250`) if `ingest.directory` / `RAG_MCP_INGEST_DIR` is set.
- Per file: `file_hash = sha256(stripped_body)` (90-92, frontmatter stripped first), stored per-chunk as `content_hash` alongside `source`, `chunk_index` (`ingest.py:169-173`).
- Next run: `store.get_all_metadata()` grouped by `source` (`ingest.py:111-116`), `prior_hash != digest` decides reindex (142). `unchanged` = zero Ollama calls. Deterministic IDs `f"{source}::{i}"` (167) → `VectorStore.upsert` (store.py:63) is idempotent. Deletes via `seen_sources` diff (185-188) + orphan shrink `chunk_index >= len(new)` (178-181).

## Key insight: stable > unique

`source = relative_to(root).as_posix()` (ingest.py:128) is *unique + stable + filesystem-bound* in one string. Used as lookup key, ID namespace, and delete-set. Renames = delete+add.

For Bear.app sqlite (or any DB) the key must be **stable across runs**, not just unique today. Don't key on `ZTITLE` / path — use the row UUID (`ZUNIQUEIDENTIFIER`) e.g. `bear://<uuid>`. Content change still detected by `sha256(body)` hash. Display fields (title/tags/dates) stay in metadata like frontmatter does now — not in the ID.

## What's reusable vs coupled

- **Pure / reusable:** `chunk_text` (77), `file_hash` (90), `parse_frontmatter`/`strip_frontmatter`/`_serialize_metadata` (17-62) — text-only. `store.py` (`upsert`/`delete_ids`/`get_all_metadata`) is already opaque to `source`.
- **Coupled firewall:** `iter_markdown_files` (70) + `Path(directory)` / `rglob` / `relative_to` / `read_text` (126-130) + `directory: str` param in `sync_directory` and `Config.ingest_dir` (`config.py:16`, `_resolve_path`). That's the seam.

## Planned seam when we revisit

Extract core:

```python
sync_items(store, items: list[{id: str, text: str, metadata: dict}], collection, *, embeddings_host, embeddings_model) -> {added, updated, deleted, unchanged}
```

Does hash compare / staging / single `get_embeddings` if needed / `upsert` / orphan + deleted cleanup. Then:

- `sync_directory` becomes one *provider* that yields that shape from disk
- Bear adapter yields same shape from sqlite (id = `bear://<uuid>`, text = note body, metadata = title/tags/created/etc.)

## Tool / config naming tradeoff

Today literally directory-coupled: `sync_directory(directory)` (`server.py:193`), `[ingest] directory/collection` in `.rag-mcp.toml`, `RAG_MCP_INGEST_DIR/COLLECTION`, `Config.ingest_dir`. Generic source needs either new verb (`sync_source`/`sync_bear`) or `source_type`/`source_uri` param + new config keys. No decision now.

## Not building

- Still markdown-only, no watcher, whole-file re-embed on any edit.
- This doc + memory #159 are the durable record. No code or test changes in this step — docs-only.

Refs: `ingest.py:128,137,142,167`, `store.py:58,63,84`, `server.py:193,250`, `config.py:159,164`.
