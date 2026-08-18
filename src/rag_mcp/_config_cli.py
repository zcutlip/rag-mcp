"""CLI for ``rag-mcp-config`` — writes starter config files."""
import argparse
import os
import sys
from pathlib import Path

import platformdirs

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


def _write_config(path: Path, template: str) -> None:
    """Write template to path, creating parents if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template)


def _init() -> int:
    """Write global and project config files if they don't exist."""
    global_dir = Path(platformdirs.user_config_dir("rag-mcp", appauthor=False))
    global_path = global_dir / "config.toml"

    project_path = Path(os.getcwd()) / ".rag-mcp.toml"

    if global_path.exists():
        print(f"skip: {global_path} already exists")
    else:
        _write_config(global_path, GLOBAL_TEMPLATE)
        print(f"wrote: {global_path}")

    if project_path.exists():
        print(f"skip: {project_path} already exists")
    else:
        _write_config(project_path, PROJECT_TEMPLATE)
        print(f"wrote: {project_path}")

    return 0


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``rag-mcp-config``."""
    parser = argparse.ArgumentParser(
        prog="rag-mcp-config",
        description="Write starter config files for rag-mcp.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["init"],
        help="Command to run (currently only 'init')",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_usage(sys.stderr)
        sys.exit(2)

    if args.command == "init":
        sys.exit(_init())

    # Should not reach here due to choices= constraint
    parser.print_usage(sys.stderr)
    sys.exit(2)
