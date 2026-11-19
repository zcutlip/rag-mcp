"""Package version.

Single source of version truth. Read by:

- pyproject.toml ([tool.setuptools.dynamic].version, via setuptools attr)
- repo-mgmt-scripts workflow tooling (stdlib ast, no import)
"""

__version__ = "2.3.1.dev1+issue-5-writer-lock"
