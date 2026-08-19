#!/bin/sh
# Rename a git tag while preserving annotations
#
# Usage:
#   git-rename-tag <old-tag> <new-tag> [--push]
#
# Examples:
#   git-rename-tag v0.1.0 v0.1.0-beta
#   git-rename-tag 2026-01.001 2026-01.000 --push
#
# Options:
#   --push    Push the new tag and delete the old tag on remote
#   --edit    Open editor to modify the annotation before creating new tag

set -e

usage() {
    echo "Usage: $0 <old-tag> <new-tag> [--push] [--edit]"
    echo ""
    echo "Options:"
    echo "  --push    Push new tag and delete old tag on remote"
    echo "  --edit    Open editor to modify the annotation"
    exit 1
}

# Parse arguments
if [ $# -lt 2 ]; then
    usage
fi

OLD_TAG="$1"
NEW_TAG="$2"
shift 2

PUSH=0
EDIT=0

while [ $# -gt 0 ]; do
    case "$1" in
        --push)
            PUSH=1
            shift
            ;;
        --edit)
            EDIT=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Check if old tag exists
if ! git rev-parse "$OLD_TAG" >/dev/null 2>&1; then
    echo "Error: Tag '$OLD_TAG' does not exist"
    exit 1
fi

# Check if new tag already exists
if git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
    echo "Error: Tag '$NEW_TAG' already exists"
    exit 1
fi

# Check if tag is annotated
ANNOTATION=$(git tag -l --format='%(contents)' "$OLD_TAG")
IS_ANNOTATED=0
if [ -n "$ANNOTATION" ]; then
    IS_ANNOTATED=1
fi

# Create new tag
if [ $EDIT -eq 1 ] && [ $IS_ANNOTATED -eq 1 ]; then
    # Open editor for annotation
    git tag -a "$NEW_TAG" "${OLD_TAG}^{}"
else
    if [ $IS_ANNOTATED -eq 1 ]; then
        # Preserve annotation
        git tag -a "$NEW_TAG" "${OLD_TAG}^{}" -m "$ANNOTATION"
    else
        # Lightweight tag
        git tag "$NEW_TAG" "${OLD_TAG}^{}"
    fi
fi

echo "Created tag: $NEW_TAG"

# Delete old tag locally
git tag -d "$OLD_TAG"
echo "Deleted local tag: $OLD_TAG"

# Push to remote if requested
if [ $PUSH -eq 1 ]; then
    echo "Pushing to remote..."
    git push origin "$NEW_TAG" ":$OLD_TAG"
    echo "Pushed tag changes to remote"
else
    echo ""
    echo "To push changes to remote:"
    echo "  git push origin $NEW_TAG :$OLD_TAG"
fi
