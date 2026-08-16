"""Tests for the package version."""
import re

import rag_mcp


def test_version_is_semver():
    """__version__ is a non-empty semver-style string."""
    assert isinstance(rag_mcp.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", rag_mcp.__version__)
