#!/bin/bash
#
# Usage: ./scripts/release.sh <patch|minor|major|vX.Y.Z>
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

get_latest_tag() {
    git tag -l "v*.*.*" --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1
}

bump_version() {
    local version="${1#v}" bump_type="$2"
    local major minor patch
    IFS='.' read -r major minor patch <<< "$version"

    case "$bump_type" in
        major) echo "v$((major + 1)).0.0" ;;
        minor) echo "v${major}.$((minor + 1)).0" ;;
        patch) echo "v${major}.${minor}.$((patch + 1))" ;;
    esac
}

main() {
    if [ ! -f "pyproject.toml" ] || [ ! -d "src/new_seasons_reminder" ]; then
        log_error "Not in project root"
        exit 1
    fi

    if [ -z "$1" ]; then
        log_error "Usage: $0 <patch|minor|major|vX.Y.Z>"
        exit 1
    fi

    if [ -n "$(git status --porcelain)" ]; then
        log_warning "You have uncommitted changes."
        git status --short
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] || exit 1
    fi

    local VERSION
    if [[ "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        VERSION="$1"
    elif [[ "$1" =~ ^(patch|minor|major)$ ]]; then
        local latest_tag
        latest_tag=$(get_latest_tag)
        if [ -z "$latest_tag" ]; then
            log_error "No existing tags found. Use an explicit version: $0 v0.1.0"
            exit 1
        fi
        VERSION=$(bump_version "$latest_tag" "$1")
        log_info "$latest_tag -> $VERSION ($1)"
    else
        log_error "Usage: $0 <patch|minor|major|vX.Y.Z>"
        exit 1
    fi

    if git rev-parse "$VERSION" >/dev/null 2>&1; then
        log_error "Tag $VERSION already exists"
        exit 1
    fi

    git tag -a "$VERSION" -m "Release $VERSION"
    git push origin "$VERSION"

    log_success "Released $VERSION"
}

main "$@"
