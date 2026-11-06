"""MCP server exposing RAG tools backed by Ollama embeddings and ChromaDB."""

import argparse
import os
import signal
import sys
import threading
import time
from importlib.metadata import PackageNotFoundError, metadata
from typing import Any

from mcp.server.mcpserver import MCPServer

from rag_mcp import ingest
from rag_mcp._cli import add_version_argument
from rag_mcp.config import get_config
from rag_mcp.embeddings import get_embeddings
from rag_mcp.store import VectorStore

mcp = MCPServer(
    "rag-mcp",
    title="RAG MCP",
    description="Retrieval-Augmented Generation server for document corpus queries",
    version="0.1.0",
    instructions=(
        "This server provides access to an indexed document corpus. "
        "Use query_documents to answer questions about the corpus content. "
        "Use list_collections to see available indexes. "
        "The rag://readme resource provides full documentation."
    ),
)
store: VectorStore | None = None


def _read_readme() -> str | None:
    """Return the README embedded in the installed distribution metadata."""
    try:
        package_metadata = metadata("rag-mcp")
    except PackageNotFoundError:
        return None

    readme = package_metadata.get("Description")
    return readme if isinstance(readme, str) and readme.strip() else None


@mcp.resource(
    "rag://readme",
    name="README",
    description="Project README with setup and usage instructions",
    mime_type="text/markdown",
)
def readme_resource() -> str:
    """Return the project README."""
    readme = _read_readme()
    if readme is None:
        return "README not available in this installation."
    return readme


def get_store() -> VectorStore:
    """Return the initialized store, raising if ``main()`` has not run yet."""
    if store is None:
        raise RuntimeError("store not initialized")
    return store


@mcp.tool()
def add_documents(
    documents: list[str],
    ids: list[str] | None = None,
    metadatas: list[dict[str, Any]] | None = None,
    collection: str = "default",
) -> str:
    """Add document chunks to a collection. Markdown text is accepted as-is."""
    if not documents:
        return f"Added 0 document(s) to collection '{collection}'."

    if ids is not None and len(ids) != len(documents):
        raise ValueError("ids must have the same length as documents")
    if metadatas is not None and len(metadatas) != len(documents):
        raise ValueError("metadatas must have the same length as documents")

    cfg = get_config()
    embeddings = get_embeddings(documents, cfg.embeddings_host, cfg.embeddings_model)
    get_store().add(
        collection=collection,
        documents=documents,
        embeddings=embeddings,
        ids=ids,
        metadatas=metadatas,
    )
    return f"Added {len(documents)} document(s) to collection '{collection}'."


@mcp.tool()
def query_documents(
    query: str,
    n_results: int = 5,
    collection: str = "default",
    compact: bool = True,
) -> dict[str, Any]:
    """Answer questions about the indexed corpus by retrieving relevant document chunks.

    Args:
        query: The search query
        n_results: Number of results to return (default 5)
        collection: Collection to search (default "default")
        compact: If True, return minimal metadata per hit. If False, include full metadata.

    Returns:
        A dict with 'results' (list of hits) and 'sources' (deduplicated source metadata).
        Each result has: rank, content, distance, metadata.
        Sources are keyed by source path and contain title, url, tags, created, updated.
    """
    if n_results < 1:
        raise ValueError("n_results must be >= 1")

    cfg = get_config()
    query_embedding = get_embeddings(
        [query], cfg.embeddings_host, cfg.embeddings_model
    )[0]
    results = get_store().query(
        collection=collection,
        query_embedding=query_embedding,
        n_results=n_results,
    )

    documents = results.get("documents", [[]])[0]
    if not documents:
        return {"results": [], "sources": {}}

    ids = results["ids"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]

    # Combine and sort by distance (ascending)
    combined = list(zip(ids, distances, documents, metadatas))
    combined.sort(key=lambda x: x[1])

    # Build results list
    results_list = []
    sources = {}

    for i, (doc_id, distance, document, meta) in enumerate(combined):
        # Round distance to 3 decimal places
        rounded_distance = round(distance, 3)

        # Build per-hit metadata
        hit_metadata = {
            "source": meta.get("source", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "content_hash": meta.get("content_hash", ""),
        }

        # If not compact, include full metadata
        if not compact:
            # Add all frontmatter fields
            for key in ["title", "url", "tags", "created", "updated"]:
                if key in meta:
                    hit_metadata[key] = meta[key]

        result = {
            "rank": i + 1,
            "content": document,
            "distance": rounded_distance,
            "metadata": hit_metadata,
        }
        results_list.append(result)

        # Build deduplicated sources dict
        source_path = meta.get("source", "")
        if source_path and source_path not in sources:
            source_meta = {}
            for key in ["title", "url", "tags", "created", "updated"]:
                if key in meta:
                    source_meta[key] = meta[key]
            if source_meta:
                sources[source_path] = source_meta

    return {"results": results_list, "sources": sources}


@mcp.tool()
def list_collections() -> list[str]:
    """List all collection names in the vector store."""
    return get_store().list_collections()


@mcp.tool()
def delete_collection(collection: str = "default") -> str:
    """Delete a collection from the vector store."""
    s = get_store()
    if collection not in s.list_collections():
        raise ValueError(f"Collection '{collection}' does not exist.")
    s.delete_collection(collection)
    return f"Deleted collection '{collection}'."


@mcp.tool()
def sync() -> str:
    """Sync the configured corpus into its collection.

    Re-syncs the ingest directory configured in .rag-mcp.toml ([ingest] directory)
    into [ingest] collection. Adds new/changed files, removes deleted ones.
    """
    config = get_config()
    if not config.ingest_dir:
        raise ValueError(
            "No ingest directory configured: set [ingest] directory in .rag-mcp.toml "
            "or via RAG_MCP_INGEST_DIR"
        )
    result = ingest.sync_directory(
        get_store(),
        config.ingest_dir,
        collection=config.ingest_collection,
        embeddings_host=config.embeddings_host,
        embeddings_model=config.embeddings_model,
        patterns=config.ingest_patterns,
    )
    return (
        f"Synced '{config.ingest_dir}' into collection '{config.ingest_collection}': "
        f"{result['added']} added, {result['updated']} updated, "
        f"{result['deleted']} deleted, {result['unchanged']} unchanged."
    )


def _format_sync_counts(result: dict[str, int]) -> str:
    """Render a sync result dict as ``added=A updated=U deleted=D unchanged=N``."""
    return (
        f"added={result.get('added', 0)} "
        f"updated={result.get('updated', 0)} "
        f"deleted={result.get('deleted', 0)} "
        f"unchanged={result.get('unchanged', 0)}"
    )


def _instance_tag(config) -> str:
    """Scaffold placeholder for the per-process log tag (no rendering yet)."""
    return ""


def _display_path(path: str, project_root: str) -> str:
    """Scaffold placeholder for root-relative path rendering (no rendering yet)."""
    return path


LOG_FILE_CAP_BYTES = 1_000_000
LOG_FILE_BACKUP_SUFFIX = ".1"


class _LogSink:
    """Dual stderr+file sink for lifecycle lines.

    Every line goes to stderr and is also appended to the configured log
    file (created with parents as needed). The file is size-capped: once
    it reaches ``LOG_FILE_CAP_BYTES`` it rotates to ``path + ".1"``
    (single backup, overwritten). Writes from the server and watcher
    threads serialize on a lock; concurrent *processes* share the file via
    O_APPEND granularity — a torn or duplicated diagnostic line under
    multi-writer contention is acceptable.

    The sink never raises: if the file cannot be opened or a write fails,
    it warns once on stderr and degrades to stderr-only, so logging can
    never fail server boot.
    """

    def __init__(self, path: str | None, tag: str) -> None:
        self._lock = threading.Lock()
        self._file = None
        self._path = path
        self._tag = tag
        self._warned = False
        if path:
            try:
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                self._file = open(path, "a", encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 — logging must never fail boot
                self._warn(
                    f"rag-mcp log file unavailable: {exc!r} "
                    "(continuing stderr-only)"
                )

    def _warn(self, text: str) -> None:
        if not self._warned:
            self._warned = True
            print(text, file=sys.stderr)

    def emit(self, text: str) -> None:
        """Write one line to stderr and append it to the log file."""
        print(text, file=sys.stderr)
        with self._lock:
            if self._file is None:
                return
            try:
                if os.fstat(self._file.fileno()).st_size >= LOG_FILE_CAP_BYTES:
                    self._file.close()
                    os.replace(self._path, self._path + LOG_FILE_BACKUP_SUFFIX)
                    self._file = open(self._path, "a", encoding="utf-8")
                self._file.write(text + "\n")
                self._file.flush()
            except Exception as exc:  # noqa: BLE001 — logging must never fail syncs
                try:
                    self._file.close()
                except Exception:  # noqa: BLE001 — best-effort close on a dead file
                    pass
                self._file = None
                self._warn(
                    f"rag-mcp log file write failed: {exc!r} "
                    "(continuing stderr-only)"
                )

    def close(self) -> None:
        """Close the log file, if open. Never raises."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None


def _emit(sink: _LogSink | None, text: str) -> None:
    """Emit one lifecycle line via ``sink``, or plain stderr when ``None``."""
    if sink is None:
        print(text, file=sys.stderr)
    else:
        sink.emit(text)


def _install_sigterm_handler(state: dict[str, str]) -> None:
    """Log-and-exit on SIGTERM so the shutdown line always fires.

    The handler records the reason and re-raises as ``SystemExit`` with the
    conventional 128+signum status, so a SIGTERM death never masquerades
    as a clean exit. The ``try/finally`` around ``mcp.run()`` in
    :func:`main` prints the line. Only SIGKILL stays silent — nothing can
    catch it. Installed from ``main()`` only, never at module import.
    """

    def _on_sigterm(signum: int, frame: object) -> None:
        state["reason"] = "SIGTERM"
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_sigterm)


def _make_sync_fn(store: VectorStore, config: Any):
    """Build the per-tick sync callable for the watcher.

    The returned callable invokes :func:`rag_mcp.ingest.sync_directory` with
    the same arguments the startup auto-ingest passes, and returns its
    result dict so the watch loop can log changing ticks.
    """

    def _sync() -> dict[str, int]:
        return ingest.sync_directory(
            store,
            config.ingest_dir,
            collection=config.ingest_collection,
            embeddings_host=config.embeddings_host,
            embeddings_model=config.embeddings_model,
            patterns=config.ingest_patterns,
        )

    return _sync


def _watch_loop(
    sync, interval: int, sleep_fn, cancel: threading.Event, sink=None
) -> None:
    """Poll ``sync`` every ``interval`` seconds until ``cancel`` is set.

    Each tick sleeps ``interval`` seconds first, then calls ``sync`` when
    the cancel event is not set — so the first sync lands one interval
    after the loop starts. A tick that changed anything (added, updated,
    or deleted) is logged with its counts; fully-idle ticks stay silent so
    short intervals don't spam. A failed sync (the callable raising
    anything) is logged and the loop continues — the next sleep retries.
    The cancel event ends the loop cleanly, including mid-sleep. Lines go
    through ``sink`` when given, else plain stderr.
    """
    while not cancel.is_set():
        sleep_fn(interval)
        if cancel.is_set():
            return
        try:
            result = sync()
        except Exception as exc:  # noqa: BLE001 — any sync failure is retried
            _emit(sink, f"watch sync failed: {exc!r}")
            continue
        if isinstance(result, dict) and (
            result.get("added", 0)
            + result.get("updated", 0)
            + result.get("deleted", 0)
            > 0
        ):
            _emit(sink, f"rag-mcp watch sync: {_format_sync_counts(result)}")


def _start_watcher(sync, interval: int, sink=None) -> None:
    """Start the daemon thread running :func:`_watch_loop`."""
    cancel = threading.Event()
    thread = threading.Thread(
        target=_watch_loop,
        args=(sync, interval, time.sleep, cancel, sink),
        daemon=True,
    )
    thread.start()


def main(argv: list[str] | None = None) -> None:
    """Run the MCP server using stdio transport."""
    global store
    parser = argparse.ArgumentParser(
        prog="rag-mcp",
        description="Run the rag-mcp MCP server.",
    )
    add_version_argument(parser)
    parser.add_argument(
        "command",
        nargs="?",
        choices=["readme"],
        help="Print the project README and exit",
    )
    args = parser.parse_args(argv)
    if args.command == "readme":
        readme = _read_readme()
        if readme is None:
            print(
                "Error: the rag-mcp README is unavailable in this installation.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(readme, end="")
        sys.exit(0)

    try:
        config = get_config()
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        print(
            "Run 'rag-mcp-config init' to create starter config files.",
            file=sys.stderr,
        )
        sys.exit(1)
    store = VectorStore(persist_dir=config.chroma_persist_dir)
    sink = _LogSink(config.logging_path, _instance_tag(config))
    _emit(
        sink,
        f"rag-mcp start: persist_dir='{config.chroma_persist_dir}' "
        f"ingest_dir='{config.ingest_dir}' "
        f"collection='{config.ingest_collection}' "
        f"watch={config.ingest_watch} "
        f"watch_interval={config.ingest_watch_interval}",
    )
    shutdown_state = {"reason": "exit"}
    _install_sigterm_handler(shutdown_state)
    if config.ingest_dir:
        result = ingest.sync_directory(
            store,
            config.ingest_dir,
            collection=config.ingest_collection,
            embeddings_host=config.embeddings_host,
            embeddings_model=config.embeddings_model,
            patterns=config.ingest_patterns,
        )
        _emit(sink, f"rag-mcp startup sync: {_format_sync_counts(result)}")
        if config.ingest_watch:
            _start_watcher(
                _make_sync_fn(store, config),
                config.ingest_watch_interval,
                sink,
            )
    try:
        mcp.run()
    finally:
        _emit(sink, f"rag-mcp shutdown: reason={shutdown_state['reason']}")
        sink.close()


if __name__ == "__main__":
    main()
