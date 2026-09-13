"""Shared CLI helpers for rag-mcp entry points."""
import argparse

from rag_mcp import __version__


def add_version_argument(parser: argparse.ArgumentParser) -> None:
    """Add bare `--version` (package `__version__`, exit 0, no side effects)."""
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Show version and exit",
    )
