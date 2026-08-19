#!/usr/bin/env bash

set -euo pipefail

# Constants
SCRIPT_NAME=$(basename "$0")
PROJECT_ROOT=$(git rev-parse --show-toplevel)
VERSION_FILE="$PROJECT_ROOT/src/rag_mcp/__init__.py"

# Valid branch types
VALID_TYPES="feature fix docs refactor test chore"

# Functions

# Print usage
usage() {
    cat <<EOF
Usage: $SCRIPT_NAME <command> [options]

Commands:
  create <type> <issue-number> <short-desc>
    Create a new issue branch with proper naming and version bump

  resume <type> <issue-number> <short-desc>
    Resume work on an existing branch (after it was merged)

  bump-version [--major|--minor|--patch]
    Adjust version mid-work (default: based on branch type)

  finish [--skip-tests] [--skip-changelog]
    Rebase onto main, update version, merge back to main, and tag.
    Runs pre-flight checks (clean tree, tests, changelog) before merging.
    Promotes CHANGELOG.md [Unreleased] section to the release version.

  release [--major|--minor|--patch] [--no-bump] [--skip-tests] [--skip-changelog]
    Create a release directly on main (no branch, no GitHub issue required).
    Bumps version, promotes changelog, commits, and tags.
    Guards: must be on main, clean tree, tests pass, changelog has content.
    With --no-bump, tags at current version without bumping.

  status
    Show current issue branch status and version info

Options:
  --major    Bump major version (breaking changes)
  --minor    Bump minor version (new features)
  --patch    Bump patch version (bug fixes)

Examples:
  $SCRIPT_NAME create feature 42 add-image-downloading
  $SCRIPT_NAME create fix 17 fix-toc-parsing
  $SCRIPT_NAME resume fix 16 paren-escaping
  $SCRIPT_NAME bump-version --major
  $SCRIPT_NAME finish
  $SCRIPT_NAME release --minor
  $SCRIPT_NAME release --patch --skip-tests
  $SCRIPT_NAME release --no-bump

EOF
    exit 1
}

# Validate branch type
validate_type() {
    local type="$1"
    if ! echo "$VALID_TYPES" | grep -qw "$type"; then
        echo "ERROR: Invalid branch type '$type'" >&2
        echo "Valid types: $VALID_TYPES" >&2
        exit 1
    fi
}

# Get current version from __init__.py
get_current_version() {
    local venv_python="$HOME/.virtualenvs/rag-mcp/bin/python"
    if [[ -x "$venv_python" ]]; then
        "$venv_python" -c "from rag_mcp import __version__; print(__version__)"
    else
        python3 -c "from rag_mcp import __version__; print(__version__)"
    fi
}

# Parse version into components
parse_version() {
    local version="$1"
    local base_version="${version%%+*}"  # Remove local version identifier
    echo "$base_version" | tr '.' ' '
}

# Bump version based on type
bump_version() {
    local current_version="$1"
    local bump_type="$2"

    local major minor patch
    read -r major minor patch <<< "$(parse_version "$current_version")"

    case "$bump_type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "ERROR: Invalid bump type '$bump_type'" >&2
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

# Determine version bump type from branch type
get_bump_type_from_branch() {
    local branch_name="$1"
    local branch_type="${branch_name%%/*}"

    case "$branch_type" in
        feature)
            echo "minor"
            ;;
        fix|docs|refactor|test|chore)
            echo "patch"
            ;;
        *)
            echo "patch"
            ;;
    esac
}

# Create dev version string
create_dev_version() {
    local base_version="$1"
    local issue_number="$2"
    local short_desc="$3"
    local dev_number="${4:-1}"

    echo "${base_version}.dev${dev_number}+issue-${issue_number}-${short_desc}"
}

# Extract issue info from branch name
parse_branch_name() {
    local branch_name="$1"
    # Format: type/N-short-desc
    local issue_part="${branch_name#*/}"  # Remove type/
    local issue_number="${issue_part%%-*}"  # Get N
    local short_desc="${issue_part#*-}"  # Get short-desc

    echo "$issue_number $short_desc"
}

# Update version in __init__.py
update_version_file() {
    local new_version="$1"
    local temp_file
    temp_file=$(mktemp)

    sed "s/^__version__ = .*/__version__ = \"$new_version\"/" "$VERSION_FILE" > "$temp_file"
    mv "$temp_file" "$VERSION_FILE"
}

# Create command
cmd_create() {
    local type="$1"
    local issue_number="$2"
    local short_desc="$3"

    # Validate inputs
    validate_type "$type"

    if ! [[ "$issue_number" =~ ^[0-9]+$ ]]; then
        echo "ERROR: Issue number must be numeric" >&2
        exit 1
    fi

    # Create branch name
    local branch_name="${type}/${issue_number}-${short_desc}"

    # Check if branch already exists
    if git show-ref --verify --quiet "refs/heads/$branch_name"; then
        echo "ERROR: Branch '$branch_name' already exists" >&2
        exit 1
    fi

    # Get current version
    local current_version
    current_version=$(get_current_version)
    echo "[INFO] Current version: $current_version"

    # Determine bump type
    local bump_type
    bump_type=$(get_bump_type_from_branch "$branch_name")
    echo "[INFO] Bumping $bump_type version"

    # Calculate new version
    local new_base_version
    new_base_version=$(bump_version "$current_version" "$bump_type")
    local new_dev_version
    new_dev_version=$(create_dev_version "$new_base_version" "$issue_number" "$short_desc")

    echo "[INFO] New version: $new_dev_version"

    # Create branch
    echo "[INFO] Creating branch: $branch_name"
    git checkout -b "$branch_name"

    # Update version
    update_version_file "$new_dev_version"

    # Commit version bump
    git add src/rag_mcp/__init__.py
    git commit -m "Bump version to $new_dev_version"

    echo "[OK] Branch created and version bumped"
    echo "[INFO] You can now start working on the issue"
}

# Resume command
# Resumes work on an existing branch (after it was merged to main)
cmd_resume() {
    local type="$1"
    local issue_number="$2"
    local short_desc="$3"

    # Validate inputs
    validate_type "$type"

    if ! [[ "$issue_number" =~ ^[0-9]+$ ]]; then
        echo "ERROR: Issue number must be numeric" >&2
        exit 1
    fi

    # Create branch name
    local branch_name="${type}/${issue_number}-${short_desc}"

    # Guard: must be on main branch
    local current_branch
    current_branch=$(git branch --show-current)
    if [[ "$current_branch" != "main" ]]; then
        echo "ERROR: Must be on main branch to resume work" >&2
        echo "  Current branch: $current_branch" >&2
        echo "  Run: git checkout main" >&2
        exit 1
    fi

    # Check if branch exists (required for resume)
    if ! git show-ref --verify --quiet "refs/heads/$branch_name"; then
        echo "ERROR: Branch '$branch_name' does not exist" >&2
        echo "  Use 'create' to make a new branch" >&2
        exit 1
    fi

    echo "[INFO] Resuming work on existing branch: $branch_name"

    # Get current version from main
    local current_version
    current_version=$(get_current_version)
    echo "[INFO] Current version: $current_version"

    # Determine bump type
    local bump_type
    bump_type=$(get_bump_type_from_branch "$branch_name")
    echo "[INFO] Bumping $bump_type version"

    # Calculate new version
    local new_base_version
    new_base_version=$(bump_version "$current_version" "$bump_type")
    local new_dev_version
    new_dev_version=$(create_dev_version "$new_base_version" "$issue_number" "$short_desc")

    echo "[INFO] New version: $new_dev_version"

    # Checkout existing branch
    echo "[INFO] Checking out branch: $branch_name"
    git checkout "$branch_name"

    # Update version
    update_version_file "$new_dev_version"

    # Commit version bump
    git add src/rag_mcp/__init__.py
    git commit -m "Bump version to $new_dev_version"

    echo "[OK] Branch checked out and version bumped"
    echo "[INFO] You can now continue working on the issue"
}

# Bump version command
cmd_bump_version() {
    local bump_type=""

    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --major)
                bump_type="major"
                shift
                ;;
            --minor)
                bump_type="minor"
                shift
                ;;
            --patch)
                bump_type="patch"
                shift
                ;;
            *)
                echo "ERROR: Unknown option '$1'" >&2
                usage
                ;;
        esac
    done

    # Get current branch
    local current_branch
    current_branch=$(git branch --show-current)

    if [[ "$current_branch" == "main" ]]; then
        echo "ERROR: Cannot bump version on main branch" >&2
        exit 1
    fi

    # If no bump type specified, derive from branch type
    if [[ -z "$bump_type" ]]; then
        bump_type=$(get_bump_type_from_branch "$current_branch")
    fi

    # Get current version
    local current_version
    current_version=$(get_current_version)
    echo "[INFO] Current version: $current_version"

    # Parse issue info from branch
    local issue_info
    issue_info=$(parse_branch_name "$current_branch")
    local issue_number short_desc
    read -r issue_number short_desc <<< "$issue_info"

    # Calculate new version
    local new_base_version
    new_base_version=$(bump_version "$current_version" "$bump_type")
    local new_dev_version
    new_dev_version=$(create_dev_version "$new_base_version" "$issue_number" "$short_desc")

    echo "[INFO] New version: $new_dev_version"

    # Update version
    update_version_file "$new_dev_version"

    # Commit version bump
    git add src/rag_mcp/__init__.py
    git commit -m "Bump version to $new_dev_version"

    echo "[OK] Version updated"
}

# Finish command
cmd_finish() {
    local skip_tests="false"
    local skip_changelog="false"

    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-tests)
                skip_tests="true"
                shift
                ;;
            --skip-changelog)
                skip_changelog="true"
                shift
                ;;
            *)
                echo "ERROR: Unknown option '$1'" >&2
                usage
                ;;
        esac
    done

    # Get current branch
    local current_branch
    current_branch=$(git branch --show-current)

    # Guard: already on main
    if [[ "$current_branch" == "main" ]]; then
        local last_msg
        last_msg=$(git log -1 --pretty=%s main)

        if echo "$last_msg" | grep -qE '\(closes #[0-9]+\)'; then
            echo "[WARN] Already on main; last commit looks like an issue merge:"
            echo "  $last_msg"
            echo ""

            local current_version
            current_version=$(get_current_version)
            local base_version="${current_version%%.dev*}"
            local tag_name="v${base_version}"

            # Case 1: Tag already exists
            if git rev-parse "$tag_name" >/dev/null 2>&1; then
                echo "[INFO] Tag $tag_name already exists. Nothing to do."
                echo "  Push with: git push origin main --tags"
                exit 0
            fi

            # Case 2: Still on dev version — bump first, then tag
            if [[ "$base_version" != "$current_version" ]]; then
                echo "  Current version: $current_version (dev)"
                echo "  Need to bump to $base_version and create tag."
                read -r -p "Bump version and create tag ${tag_name}? [y/N] " confirm
                if [[ "$confirm" =~ ^[yY] ]]; then
                    update_version_file "$base_version"
                    git add src/rag_mcp/__init__.py
                    git commit -m "Release version $base_version"
                    git tag -a "$tag_name" -m "version $base_version"
                    echo "[OK] Version bumped and tag created: $tag_name"
                else
                    echo "Aborted."
                    exit 1
                fi
            # Case 3: Already at release version — just tag
            else
                echo "  Current version: $base_version (release)"
                read -r -p "Create tag ${tag_name}? [y/N] " confirm
                if [[ "$confirm" =~ ^[yY] ]]; then
                    git tag -a "$tag_name" -m "version $base_version"
                    echo "[OK] Tag created: $tag_name"
                else
                    echo "Aborted."
                    exit 1
                fi
            fi

            echo "[INFO] Push with: git push origin main --tags"
            exit 0
        else
            echo "ERROR: Already on main branch" >&2
            echo "  Switch to your issue branch first: git checkout <branch-name>" >&2
            exit 1
        fi
    fi

    # Guard: must be on an issue branch
    if ! echo "$current_branch" | grep -qE \
        '^(feature|fix|docs|refactor|test|chore)/[0-9]+-.+'; then
        echo "ERROR: Not on an issue branch (current: $current_branch)" >&2
        echo "  Create one with: $SCRIPT_NAME create <type> <issue> <desc>" >&2
        exit 1
    fi

    # Guard: clean working tree (hard block)
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "ERROR: Working tree has uncommitted changes" >&2
        echo "  Run 'git status' and 'git diff' to review." >&2
        exit 1
    fi

    # Warn about untracked files (soft block, interactive)
    local untracked
    untracked=$(git ls-files --others --exclude-standard | head -5)
    if [[ -n "$untracked" ]]; then
        echo "[WARN] Untracked files found (diagnostic artifacts?)"
        # shellcheck disable=SC2001
        echo "$untracked" | sed 's/^/  /'
        echo ""
        read -r -p "Continue anyway? [y/N] " confirm
        if [[ ! "$confirm" =~ ^[yY] ]]; then
            echo "Aborted."
            exit 1
        fi
    fi

    # Guard: tests passing
    if [[ "$skip_tests" != "true" ]]; then
        local test_script="$PROJECT_ROOT/scripts/run-tests.sh"
        if [[ -x "$test_script" ]]; then
            echo "[INFO] Running test suite..."
            if ! "$test_script"; then
                echo "ERROR: Tests failed. Fix before releasing." >&2
                echo "  Use --skip-tests to bypass (not recommended)." >&2
                exit 1
            fi
            echo "[OK] Tests passing"
        else
            echo "ERROR: Test script not found: $test_script" >&2
            echo "  Use --skip-tests to bypass." >&2
            exit 1
        fi
    fi

    # Guard + auto-promote: changelog
    if [[ "$skip_changelog" != "true" ]]; then
        local changelog="$PROJECT_ROOT/CHANGELOG.md"
        if [[ ! -f "$changelog" ]]; then
            echo "ERROR: CHANGELOG.md not found" >&2
            echo "  Create one with an [Unreleased] section." >&2
            exit 1
        fi
        if ! grep -q '^## \[Unreleased\]' "$changelog"; then
            echo "ERROR: CHANGELOG.md missing [Unreleased] section" >&2
            exit 1
        fi
        # Check section has content (not just a header)
        local section_lines
        section_lines=$(sed -n '/^## \[Unreleased\]/,/^## /p' \
            "$changelog" | grep -c '^-')
        if [[ "$section_lines" -eq 0 ]]; then
            echo "ERROR: CHANGELOG.md [Unreleased] section is empty" >&2
            exit 1
        fi
        echo "[OK] CHANGELOG.md has [Unreleased] content"
    fi

    # Parse issue info from branch
    local issue_info
    issue_info=$(parse_branch_name "$current_branch")
    local issue_number short_desc
    read -r issue_number short_desc <<< "$issue_info"

    # Get current version
    local current_version
    current_version=$(get_current_version)
    echo "[INFO] Current version: $current_version"

    # Extract base version (remove dev suffix)
    local base_version="${current_version%%.dev*}"

    echo "[INFO] Releasing version: $base_version"

    # Promote changelog [Unreleased] to version section (before rebase)
    if [[ "$skip_changelog" != "true" ]]; then
        local today
        today=$(date +%Y-%m-%d)
        # Step 1: Rename first [Unreleased] to version
        sed -i '' \
            "1,/^## \[Unreleased\]/s/^## \[Unreleased\]/## [$base_version] - $today/" \
            "$changelog"
        # Step 2: Insert empty [Unreleased] stub above promoted section
        sed -i '' "/^## \[$base_version\]/i\\
## [Unreleased]\\
\\
" "$changelog"
        git add "$changelog"
        git commit -m "CHANGELOG.md: Promote [Unreleased] to v${base_version}"
        echo "[OK] Changelog promoted to v${base_version}"
    fi

    # Rebase onto main
    echo "[INFO] Rebasing onto main..."
    git fetch origin
    git rebase origin/main

    # Update version (remove dev suffix)
    update_version_file "$base_version"

    # Commit version update (only if there are actual changes)
    git add src/rag_mcp/__init__.py
    if ! git diff --cached --quiet; then
        git commit -m "Release version $base_version"
    else
        echo "[INFO] Version already at $base_version, skipping commit"
    fi

    # Generate merge commit message from branch name
    # Convert short-desc to title case with spaces
    local merge_desc
    merge_desc=$(echo "$short_desc" | tr '-' ' ' | perl -pe 's/\b(.)/\u$1/g')
    local merge_message="${merge_desc} (closes #${issue_number})"

    echo "[INFO] Merge message: $merge_message"

    # Switch to main and merge
    git checkout main
    git merge --no-ff "$current_branch" -m "$merge_message"

    # Create tag for the release
    local tag_name="v${base_version}"
    echo "[INFO] Creating tag: $tag_name"
    git tag -a "$tag_name" -m "version $base_version"

    echo "[OK] Merged to main"
    echo "[OK] Tag created: $tag_name"
    echo "[INFO] Don't forget to push: git push origin main --tags"
}

# Release command - works directly on main, no branch required
cmd_release() {
    local bump_type="patch"
    local no_bump="false"
    local skip_tests="false"
    local skip_changelog="false"

    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --major)
                bump_type="major"
                shift
                ;;
            --minor)
                bump_type="minor"
                shift
                ;;
            --patch)
                bump_type="patch"
                shift
                ;;
            --no-bump)
                no_bump="true"
                shift
                ;;
            --skip-tests)
                skip_tests="true"
                shift
                ;;
            --skip-changelog)
                skip_changelog="true"
                shift
                ;;
            *)
                echo "ERROR: Unknown option '$1'" >&2
                usage
                ;;
        esac
    done

    # Guard: must be on main branch
    local current_branch
    current_branch=$(git branch --show-current)
    if [[ "$current_branch" != "main" ]]; then
        echo "ERROR: Must be on main branch to release" >&2
        echo "  Current branch: $current_branch" >&2
        echo "  Run: git checkout main" >&2
        exit 1
    fi

    # Guard: clean working tree (hard block)
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "ERROR: Working tree has uncommitted changes" >&2
        echo "  Run 'git status' and 'git diff' to review." >&2
        exit 1
    fi

    # Guard: tests passing
    if [[ "$skip_tests" != "true" ]]; then
        local test_script="$PROJECT_ROOT/scripts/run-tests.sh"
        if [[ -x "$test_script" ]]; then
            echo "[INFO] Running test suite..."
            if ! "$test_script"; then
                echo "ERROR: Tests failed. Fix before releasing." >&2
                echo "  Use --skip-tests to bypass (not recommended)." >&2
                exit 1
            fi
            echo "[OK] Tests passing"
        else
            echo "ERROR: Test script not found: $test_script" >&2
            echo "  Use --skip-tests to bypass." >&2
            exit 1
        fi
    fi

    # Guard: changelog has non-empty [Unreleased] section
    if [[ "$skip_changelog" != "true" ]]; then
        local changelog="$PROJECT_ROOT/CHANGELOG.md"
        if [[ ! -f "$changelog" ]]; then
            echo "ERROR: CHANGELOG.md not found" >&2
            echo "  Create one with an [Unreleased] section." >&2
            exit 1
        fi
        if ! grep -q '^## \[Unreleased\]' "$changelog"; then
            echo "ERROR: CHANGELOG.md missing [Unreleased] section" >&2
            exit 1
        fi
        # Check section has content (not just a header)
        local section_lines
        section_lines=$(sed -n '/^## \[Unreleased\]/,/^## /p' \
            "$changelog" | grep -c '^-')
        if [[ "$section_lines" -eq 0 ]]; then
            echo "ERROR: CHANGELOG.md [Unreleased] section is empty" >&2
            exit 1
        fi
        echo "[OK] CHANGELOG.md has [Unreleased] content"
    fi

    # Get current version and strip dev suffix
    local current_version
    current_version=$(get_current_version)
    echo "[INFO] Current version: $current_version"
    local base_version="${current_version%%.dev*}"

    # Determine release version
    local new_version
    if [[ "$no_bump" == "true" ]]; then
        new_version="$base_version"
        echo "[INFO] Releasing at current version: $new_version (--no-bump)"
    else
        new_version=$(bump_version "$base_version" "$bump_type")
        echo "[INFO] Bumping $bump_type version: $base_version -> $new_version"
    fi

    # Promote changelog [Unreleased] to version section
    if [[ "$skip_changelog" != "true" ]]; then
        local changelog="$PROJECT_ROOT/CHANGELOG.md"
        local today
        today=$(date +%Y-%m-%d)
        # Step 1: Rename first [Unreleased] to version
        sed -i '' \
            "1,/^## \[Unreleased\]/s/^## \[Unreleased\]/## [$new_version] - $today/" \
            "$changelog"
        # Step 2: Insert empty [Unreleased] stub above promoted section
        sed -i '' "/^## \[$new_version\]/i\\
## [Unreleased]\\
\\
" "$changelog"
        git add "$changelog"
        git commit -m "CHANGELOG.md: Promote [Unreleased] to v${new_version}"
        echo "[OK] Changelog promoted to v${new_version}"
    fi

    # Bump version in __init__.py
    update_version_file "$new_version"
    git add src/rag_mcp/__init__.py
    if ! git diff --cached --quiet; then
        git commit -m "Release version $new_version"
        echo "[OK] Version bumped to $new_version"
    else
        echo "[INFO] Version already at $new_version, skipping commit"
    fi

    # Create annotated tag
    local tag_name="v${new_version}"
    echo "[INFO] Creating tag: $tag_name"
    git tag -a "$tag_name" -m "version $new_version"
    echo "[OK] Tag created: $tag_name"

    echo "[INFO] Push with: git push origin main --tags"
}

# Show current issue branch status
cmd_status() {
    # Get current branch name
    local branch_name
    branch_name=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [[ -z "$branch_name" ]]; then
        echo "ERROR: Not in a git repository" >&2
        exit 1
    fi

    # Validate it's an issue branch (type/N-short-desc)
    if ! echo "$branch_name" | grep -qE '^(feature|fix|docs|refactor|test|chore)/[0-9]+-.+'; then
        echo "ERROR: Not on an issue branch (current: $branch_name)" >&2
        echo "Create one with: $SCRIPT_NAME create <type> <issue> <desc>" >&2
        exit 1
    fi

    local branch_type="${branch_name%%/*}"
    local parsed
    parsed=$(parse_branch_name "$branch_name")
    local issue_number="${parsed%% *}"
    local short_desc="${parsed#* }"

    local bump_type
    bump_type=$(get_bump_type_from_branch "$branch_name")
    local bump_desc
    case "$bump_type" in
        major) bump_desc="major version bump" ;;
        minor) bump_desc="minor version bump" ;;
        patch) bump_desc="patch version bump" ;;
    esac

    # Version info
    local current_version
    current_version=$(get_current_version)
    local release_version="${current_version%%.dev*}"
    if [[ "$release_version" == "$current_version" ]]; then
        release_version="N/A (not a dev version)"
    fi

    # Fetch from remote (non-fatal)
    echo "Fetching from remote..."
    git fetch origin 2>/dev/null || true

    # Check ahead/behind
    local ahead="0"
    local behind="0"
    local has_origin_main=false
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        has_origin_main=true
        behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
        ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
    fi

    # Check working tree - separate tracked changes from untracked files
    local tracked_changes
    tracked_changes=$(git status --porcelain 2>/dev/null | grep -v '^??' || true)
    local untracked_files
    untracked_files=$(git status --porcelain 2>/dev/null | grep '^??' | sed 's/^?? //' || true)
    local untracked_count
    untracked_count=$(echo "$untracked_files" | grep -c . || true)

    local tree_status="clean"
    if [[ -n "$tracked_changes" ]]; then
        tree_status="dirty (uncommitted changes)"
    elif [[ "$untracked_count" -gt 0 ]]; then
        tree_status="clean ($untracked_count untracked file(s))"
    fi

    # Print status
    echo ""
    echo "Branch: $branch_name"
    echo "Type:   $branch_type ($bump_desc)"
    echo "Issue:  #$issue_number"
    echo "Description: $short_desc"
    echo ""
    echo "Current version: $current_version"
    echo "Release version: $release_version"
    echo ""
    if $has_origin_main; then
        echo "Commits ahead of main: $ahead"
        echo "Commits behind main: $behind"
    else
        echo "Commits ahead/behind: origin/main not available"
    fi
    echo "Working tree: $tree_status"

    # Show untracked files if only those are present (up to 5)
    if [[ -z "$tracked_changes" && "$untracked_count" -gt 0 ]]; then
        echo ""
        echo "Untracked files:"
        local shown=0
        while IFS= read -r file; do
            echo "  $file"
            shown=$((shown + 1))
            if [[ $shown -ge 5 ]]; then
                local remaining=$((untracked_count - shown))
                if [[ $remaining -gt 0 ]]; then
                    echo "  ... and $remaining more"
                fi
                break
            fi
        done <<< "$untracked_files"
    fi

    # Next steps
    echo ""
    echo "Next steps:"
    local has_steps=false
    if [[ -n "$tracked_changes" ]]; then
        echo "  - Commit your changes first"
        has_steps=true
    fi
    if $has_origin_main && [[ "$behind" != "0" ]]; then
        echo "  - Run: git rebase origin/main"
        has_steps=true
    fi
    if [[ "$ahead" != "0" ]]; then
        echo "  - Run: $SCRIPT_NAME finish"
        has_steps=true
    fi
    if ! $has_steps; then
        echo "  - No pending changes"
    fi
}

# Main
main() {
    if [[ $# -lt 1 ]]; then
        usage
    fi

    local command="$1"
    shift

    case "$command" in
        create)
            if [[ $# -lt 3 ]]; then
                echo "ERROR: create requires <type> <issue-number> <short-desc>" >&2
                usage
            fi
            cmd_create "$@"
            ;;
        resume)
            if [[ $# -lt 3 ]]; then
                echo "ERROR: resume requires <type> <issue-number> <short-desc>" >&2
                usage
            fi
            cmd_resume "$@"
            ;;
        bump-version)
            cmd_bump_version "$@"
            ;;
        finish)
            cmd_finish "$@"
            ;;
        release)
            cmd_release "$@"
            ;;
        status)
            cmd_status
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "ERROR: Unknown command '$command'" >&2
            usage
            ;;
    esac
}

main "$@"
