"""Tests for the package version."""
from packaging.version import Version

import rag_mcp


def test_version_is_semver():
    """__version__ is a valid PEP 440 version."""
    assert isinstance(rag_mcp.__version__, str)
    Version(rag_mcp.__version__)
