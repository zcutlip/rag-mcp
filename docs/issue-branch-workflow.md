# Issue Branch Workflow

## Overview

Issue work runs on dedicated branches managed by the shared
[repo-mgmt-scripts](https://github.com/zcutlip/repo-mgmt-scripts) suite,
consumed as a git submodule.

**IMPORTANT: Use the helper script `scripts/issue-branch` for all issue-related
operations.** Do not manually run git commands for creating issue branches,
bumping versions, or merging.

## Setup

The suite lives in `submodules/repo-mgmt-scripts/`, with symlinks in
`scripts/`. After a fresh clone:

```bash
git submodule update --init
```

The symlinks (created by `submodules/repo-mgmt-scripts/install scripts/`)
point into the submodule's `src/`. The only project-local files in
`scripts/` are:

- `project_settings.sh` — per-project configuration (see below)
- `run-tests.sh` — the test command referenced by the settings
- `git-rename-tag.sh` — tag utility, not part of the lifecycle

### `scripts/project_settings.sh`

```sh
ROOT_PACKAGE_NAME="src/rag_mcp"   # src-layout: version file path, not just package name
TWINE_UPLOAD_ENABLED="0"
ISSUE_BRANCH_TEMPLATE="dev/{issue}-{slug}"
ISSUE_BRANCH_BASE="main"
ISSUE_BRANCH_TEST_COMMAND="scripts/run-tests.sh"
ISSUE_BRANCH_CHANGELOG="CHANGELOG.md"
```

## Branch Naming

**Format:** `dev/<issue-number>-<short-slug>`

The branch name does not carry the change type — the type
(`feature|fix|docs|refactor|test|chore`) is an argument to `create` and
determines the version bump level. The color moment is the issue number,
not the branch prefix.

**Examples:**
- `dev/1-watch-mode`
- `dev/17-fix-toc-parsing`

## Version Management

Version truth lives in **`src/rag_mcp/__about__.py`** as `__version__`.
`pyproject.toml` contains no hardcoded version — it declares
`dynamic = ["version"]` with `version = { attr = "rag_mcp.__about__.__version__" }`
and reads the value at build time. `src/rag_mcp/__init__.py` re-exports
`__version__` from `__about__.py` so `rag_mcp.__version__` keeps working.
The workflow tooling reads and writes the version via stdlib `ast`
(`read_about_version.py` / `write_about_version.py`), without importing
the package. **Never bump the version in `pyproject.toml`.**

**Development versions:**
- Format: `X.Y.(Z+B).dev1+issue-N-short-slug` (PEP 440)
- Bump level `B` comes from the branch type: `feature` → minor, others → patch
- Example: on `main` at `2.1.0`, `create feature 1 watch-mode` writes
  `2.2.0.dev1+issue-1-watch-mode` to `src/rag_mcp/__about__.py` and commits it

**Release versions:**
- `finish` strips the dev suffix back to the reserved core version
- Example: `2.2.0.dev1+issue-1-watch-mode` releases as `2.2.0`

## Lifecycle

```bash
scripts/issue-branch create <type> <issue-number> <short-slug>  # feature|fix|docs|refactor|test|chore
scripts/issue-branch resume <type> <issue-number> <short-slug>
scripts/issue-branch status
scripts/issue-branch bump-version --major|--minor|--patch
scripts/issue-branch finish [--skip-tests|--skip-changelog]
scripts/issue-branch release [--skip-tests|--skip-changelog]
```

Agents may create and switch *local* branches only. Merge, push, pull, and
fetch are the user's — in practice by directing `scripts/issue-branch
finish`, which performs the merge itself. Branch from a current `main`; one
branch per issue, never batch unrelated issues onto one branch. Delete the
branch (local and origin) after merge — `scripts/deletebranch` does both in
one pass.

### `create`

Creates the branch from `main` (guards: on base branch, clean tree incl.
untracked files), then writes the dev version to `__about__.py` and commits
it. Refuses an existing branch.

### `finish`

The normal end-of-branch step. Runs the test command, rebases onto `main`
(`rebase.autostash=false`, so conflicts fail loudly), promotes the
CHANGELOG `[Unreleased]` section to a versioned heading, strips the dev
suffix, commits `release X.Y.Z`, checks out `main`, merges `--no-ff` with a
`(closes #N)` merge message, and tags `vX.Y.Z`. There is no separate manual
merge step and it takes no bump level — the dev version written by `create`
already encodes the intended bump.

If killed partway (after merging to `main`), re-running `finish` on `main`
is a recovery path: it completes the missing version normalization/tag
idempotently, keyed on the merge commit's latest `(closes #N)` message.

### `status`

Read-only. Reports the branch, issue number, current version, release
version, test command, changelog readiness, and tree state. Run it before
choosing a release command.

### `bump-version`

Adjusts the version on the issue branch (`--major` for an unexpected
breaking change), re-writing the dev version at the new level. A valve, not
a release step.

### `release`

For cutting a release directly on `main` without a branch or issue
(e.g., docs-only updates and small fixes committed straight to `main`).

- **Requires being on `main`** with a clean tree and passing tests.
- **Never mutates the version.** It reads the version, promotes
  `[Unreleased]`, commits, and tags.
- Refuses a dev/local-suffixed version (`use finish` or `bump-version`) and
  refuses an already-tagged version instead of creating a duplicate
  changelog heading.

## Version-Mutation Rules

- Only `create` and `finish` mutate versions on the normal path
  (start-bump + dev suffix; strip-to-core on finish). `resume` and
  `bump-version` are valves — they only restore or re-level a version the
  normal path would have produced, never invent one.
- The helper **never pushes** and **never creates a GitHub release**.

## Releases

Manual, once the helper has committed and tagged:

1. Push the branch and tags: `git push origin main --tags`
2. Create the GitHub release referencing the tag.

There is no PyPI publish step; the README installs from the git URL via
pipx.

## Utility Scripts

### `scripts/git-rename-tag.sh`

Renames a git tag while preserving annotations.

```bash
./scripts/git-rename-tag.sh <old-tag> <new-tag>
./scripts/git-rename-tag.sh <old-tag> <new-tag> --push
./scripts/git-rename-tag.sh <old-tag> <new-tag> --edit
```

### `scripts/run-tests.sh`

Runs pytest with automatic virtualenv initialization
(`~/.virtualenvs/rag-mcp`). Used internally by `finish` and `release` as
the test gate. Hard-fails if the virtualenv doesn't exist. The
`--skip-tests`/`--skip-changelog` flags on `finish`/`release` exist for
direct user invocation — agents must never pass them.

## History

Adopted from the forgejo-to-github project (plans in
`submodules/repo-mgmt-scripts` upstream). Supersedes the former bespoke
`scripts/issue-branch.sh`, which is removed by this change.
