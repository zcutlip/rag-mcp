# Issue Branch Workflow

## Overview

When working on issues from the GitHub issue tracker, use dedicated
branches with specific naming and version management conventions.

**IMPORTANT: Use the helper script `scripts/issue-branch.sh` for all issue-related operations.**
Do not manually run git commands for creating issue branches, bumping versions, or merging.

## Critical Rules

1. **Use the helper script for issue work** - When working on GitHub issues, always use `scripts/issue-branch.sh` for:
   - Creating issue branches
   - Bumping versions
   - Finishing and merging

2. **Test before committing** - Never commit changes without testing them first

3. **Wait for user approval** - Only commit when explicitly asked

## Branch Naming Convention

**Format:** `type/N-short-desc`

**Standard types:**
- `feature` - New functionality
- `fix` - Bug fixes
- `docs` - Documentation changes
- `refactor` - Code refactoring
- `test` - Test improvements
- `chore` - Maintenance tasks

**Examples:**
- `feature/42-add-image-downloading`
- `fix/17-fix-toc-parsing`
- `docs/8-update-readme`

## Version Management

Version is stored in `src/rag_mcp/__init__.py` as `__version__`.
`pyproject.toml` does not contain a hardcoded version — it declares
`dynamic = ["version"]` with `version = { attr = "rag_mcp.__version__" }`
and reads the value from `src/rag_mcp/__init__.py` at build time.
All version bumps below edit `src/rag_mcp/__init__.py`.

**Development versions:**
- Format: `x.y.z.devN+issue-N-short-desc` (PEP 440 compliant)
- Example: `0.2.1` -> `0.3.0.dev1+issue-42-add-image-downloading`

**Version bumping rules:**
- **Fix branches**: Bump patch version (0.2.1 -> 0.2.2.dev1+...)
- **Feature branches**: Bump minor version (0.2.1 -> 0.3.0.dev1+...)
- **Other types**: Bump patch version (0.2.1 -> 0.2.2.dev1+...)
- **Breaking changes**: Bump major version (0.2.1 -> 1.0.0.dev1+...)

**Release versions:**
- Remove dev suffix when merging to main
- Example: `0.3.0.dev1+issue-42-add-image-downloading` -> `0.3.0`

## Workflow

### Creating an Issue Branch

1. Create branch from main:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b type/N-short-desc
   ```

2. Bump version in `src/rag_mcp/__init__.py`:
   ```bash
   # For a feature (minor bump)
   # Change: __version__ = "0.2.1"
   # To:     __version__ = "0.3.0.dev1+issue-42-add-image-downloading"
   ```

3. Commit version bump:
   ```bash
   git add src/rag_mcp/__init__.py
   git commit -m "Bump version to 0.3.0.dev1+issue-42-add-image-downloading"
   ```

4. Start work on the issue

### Working on the Branch

**Regular rebasing:**
```bash
git fetch origin
git rebase origin/main
```

**If main has moved forward:**
- Rebase onto main first
- Then update version if needed (based on new main version)
- Example: If main is now 0.3.0, update to 0.4.0.dev1+issue-42-...

**Adjusting version mid-work:**
- If you realize the change is breaking: bump major version
- If you realize it's smaller than expected: adjust accordingly
- Just update `src/rag_mcp/__init__.py` and commit the change

### Merging Back to Main

1. Rebase onto main:
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. Update version (remove dev suffix):
   ```bash
   # Change: __version__ = "0.3.0.dev1+issue-42-add-image-downloading"
   # To:     __version__ = "0.3.0"
   ```

3. Commit version update:
   ```bash
   git add src/rag_mcp/__init__.py
   git commit -m "Release version 0.3.0"
   ```

4. Merge to main:
   ```bash
   git checkout main
   git merge --no-ff type/N-short-desc
   ```

5. Use merge commit message derived from branch name:
   ```
   Add image downloading support (closes #42)
   ```

6. Create annotated tag for the release:
   ```bash
   git tag -a v0.3.0 -m "version 0.3.0"
   ```

## Helper Script

A helper script `scripts/issue-branch.sh` automates this workflow.

**Features:**
- Creates branches with proper naming
- Bumps versions automatically
- Creates annotated tags on merge (format: `vX.Y.Z`)
- Shows branch status, version info, and next steps
- Does NOT push to remote (user must push manually)

**Usage:**
```bash
# Create a new issue branch
./scripts/issue-branch.sh create <type> <issue-number> <short-description>

# Resume work on an existing branch (after it was merged)
./scripts/issue-branch.sh resume <type> <issue-number> <short-description>

# Adjust version mid-work
./scripts/issue-branch.sh bump-version --major  # Bump to major version
./scripts/issue-branch.sh bump-version --minor  # Bump to minor version
./scripts/issue-branch.sh bump-version --patch  # Bump to patch version

# Finish and merge back to main
./scripts/issue-branch.sh finish

# Cut a release directly from main (no branch or issue)
./scripts/issue-branch.sh release [--major|--minor|--patch] [--no-bump]

# Check current issue/branch status
./scripts/issue-branch.sh status
```

**Examples:**
```bash
# Create feature branch for issue #42
./scripts/issue-branch.sh create feature 42 add-image-downloading

# Create fix branch for issue #17
./scripts/issue-branch.sh create fix 17 fix-toc-parsing

# Resume work on merged branch (issue reopened)
./scripts/issue-branch.sh resume fix 16 paren-escaping

# Realize mid-work it's a breaking change
./scripts/issue-branch.sh bump-version --major

# Check status mid-work
./scripts/issue-branch.sh status

# Finish and merge
./scripts/issue-branch.sh finish

# Cut a patch release from main
./scripts/issue-branch.sh release

# Cut a minor release from main
./scripts/issue-branch.sh release --minor

# Release at current version without bumping (e.g., first release)
./scripts/issue-branch.sh release --no-bump
```

### `release` Subcommand

For cutting a release without a branch or GitHub issue.

```bash
./scripts/issue-branch.sh release [--major|--minor|--patch] [--no-bump]
```

- Use when the changes are already on `main` and you just need to publish a release (e.g., docs-only updates, small fixes committed directly, or manual release cadence).
- No branch is created and no GitHub issue is required.
- **Preconditions** (enforced by the script):
  - Must be on `main`
  - Working tree must be clean (no uncommitted changes)
  - Tests must pass (`scripts/run-tests.sh` is invoked by `finish`/`release`)
  - Changelog must have content to promote (unreleased section is non-empty)
- **What it does:**
  - Promotes the changelog (moves unreleased notes into a new versioned section)
  - Bumps `__version__` in `src/rag_mcp/__init__.py`
  - Commits the changelog and version bump
  - Creates an annotated tag `vX.Y.Z`
- **Bump level:** Default is `patch` (e.g., `0.1.0` -> `0.1.1`). Pass `--minor` or `--major` to override; `--patch` is explicit patch.
- **`--no-bump`:** Releases at the current version without bumping. Use for first releases or when the version is already correct.

## Edge Cases

**Multiple dev versions:**
- If you need to create a new dev version on the same branch
- Increment `.devN` (e.g., `.dev1` -> `.dev2`)
- Rare, but possible if you reset and restart work

**Version conflicts:**
- If main has moved forward significantly, rebase first
- Then update version to be higher than new main version
- Example: main is 0.4.0, your branch is 0.3.0.dev1 -> update to 0.5.0.dev1

**Abandoned branches:**
- If you abandon a branch, just delete it
- No need to clean up version numbers
- Next branch will use appropriate version based on current main

## Best Practices

- Always work on a dedicated branch for issues
- Commit version bump separately before starting work
- Rebase regularly to stay up-to-date with main
- Use the helper script to avoid manual errors
- Keep branch names short but descriptive
- Use lowercase with hyphens for branch names
- Include issue number in branch name for traceability

## Utility Scripts

### `scripts/issue-branch.sh`

Manages issue branch lifecycle: creation, version bumping, and merge.

```bash
# Create issue branch
./scripts/issue-branch.sh create <type> <issue-number> <short-desc>

# Resume work on existing branch (after it was merged)
./scripts/issue-branch.sh resume <type> <issue-number> <short-desc>

# Check branch status
./scripts/issue-branch.sh status

# Adjust version mid-work
./scripts/issue-branch.sh bump-version --major

# Finish and merge to main
./scripts/issue-branch.sh finish

# Cut a release from main without a branch or issue
./scripts/issue-branch.sh release [--major|--minor|--patch]
```

`finish` invokes `scripts/run-tests.sh` to verify tests pass before merging.

### `scripts/git-rename-tag.sh`

Renames a git tag while preserving annotations.

```bash
# Rename tag locally
./scripts/git-rename-tag.sh <old-tag> <new-tag>

# Rename and push to remote
./scripts/git-rename-tag.sh <old-tag> <new-tag> --push

# Rename with edited annotation
./scripts/git-rename-tag.sh <old-tag> <new-tag> --edit
```

Preserves annotated tag messages automatically. Use `--edit` to modify the annotation in your editor before creating the new tag.

### `scripts/run-tests.sh`

Runs pytest with automatic virtualenv initialization.

```bash
# Run all tests
./scripts/run-tests.sh

# Run with verbose output
./scripts/run-tests.sh -v

# Run specific test file
./scripts/run-tests.sh tests/test_server.py

# Run tests matching pattern
./scripts/run-tests.sh -k test_query
```

Sources `~/.virtualenvs/rag-mcp` and invokes `pytest` with argument passthrough. Used internally by `finish` and `release` as the test gate. Hard-fails if the virtualenv doesn't exist (use `--skip-tests` to bypass).
