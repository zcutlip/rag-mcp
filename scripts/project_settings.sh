# shellcheck disable=SC2034
# Project settings for repo management scripts (copied from the upstream
# example_project_settings.sh). Referenced by functions.sh next to the
# repo-mgmt-scripts symlinks in scripts/.

# version resolution prefers <package>/__about__.py (via stdlib ast),
# falling back to `python3 ./setup.py --version`.
# rag-mcp uses a src-layout, so the version file lives at
# src/rag_mcp/__about__.py — path, not just the package name
ROOT_PACKAGE_NAME="src/rag_mcp"

# Either don't set, or set to "1" to enable
# if set at all and not set to "1" twine upload will not happen
TWINE_UPLOAD_ENABLED="0"

# branch name template for issue branches; {issue} is the issue number, {slug} is the short slug
ISSUE_BRANCH_TEMPLATE="dev/{issue}-{slug}"
# branch issue branches are created from and finished back into
ISSUE_BRANCH_BASE="main"
# test command issue-branch finish/release runs to gate the release
ISSUE_BRANCH_TEST_COMMAND="scripts/run-tests.sh"
# changelog file whose [Unreleased] section is promoted to a versioned heading at release time
ISSUE_BRANCH_CHANGELOG="CHANGELOG.md"
