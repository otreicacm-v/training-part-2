#!/bin/bash
# Build cached environment bundles for fast setup
#
# Creates two types of bundles:
# 1. Full bundle (Odoo + venv) - ~350MB for GitHub Releases
# 2. Venv-only bundle - ~150MB for Cloudflare/smaller hosts
#
# Usage:
#   ./scripts/build_env_cache.sh build       # Full bundle (Odoo + venv)
#   ./scripts/build_env_cache.sh build-venv  # Venv only (smaller, for Cloudflare)
#   ./scripts/build_env_cache.sh restore <url>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="/tmp/odoo-env-cache"
CACHE_VERSION="v1.0.0"
CACHE_FILE="odoo19-env-${CACHE_VERSION}.tar.gz"
VENV_CACHE_FILE="odoo19-venv-${CACHE_VERSION}.tar.gz"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }

#==============================================================================
# Build the cache bundle
#==============================================================================
build_cache() {
    log_info "Building environment cache bundle..."

    # Ensure environment is set up
    if [ ! -d "/tmp/odoo-19" ] || [ ! -d "/tmp/odoo19-venv" ]; then
        log_info "Environment not found, setting up first..."
        "$SCRIPT_DIR/setup_test_env.sh" --force
    fi

    # Create cache directory
    rm -rf "$CACHE_DIR"
    mkdir -p "$CACHE_DIR"

    # Copy Odoo (exclude .git and large unnecessary files)
    log_info "Copying Odoo 19 source..."
    cp -a /tmp/odoo-19 "$CACHE_DIR/"
    # Remove unnecessary files to reduce size
    find "$CACHE_DIR/odoo-19" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find "$CACHE_DIR/odoo-19" -name '*.pyc' -delete 2>/dev/null || true
    rm -rf "$CACHE_DIR/odoo-19/.git" 2>/dev/null || true

    # Copy virtualenv
    log_info "Copying Python virtualenv..."
    cp -a /tmp/odoo19-venv "$CACHE_DIR/"

    # Create metadata file
    cat > "$CACHE_DIR/CACHE_INFO.txt" <<EOF
Odoo Environment Cache
Version: $CACHE_VERSION
Created: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Odoo Version: 19.0
Python Version: $(python3.10 --version 2>&1)
Packages: $(ls "$CACHE_DIR/odoo19-venv/lib/python3.10/site-packages" | wc -l) site-packages
EOF

    # Create tarball
    log_info "Creating tarball..."
    cd /tmp
    tar -czf "$CACHE_FILE" -C "$CACHE_DIR" .

    # Report size
    local size=$(du -h "/tmp/$CACHE_FILE" | cut -f1)
    log_success "Cache bundle created: /tmp/$CACHE_FILE ($size)"

    # Cleanup
    rm -rf "$CACHE_DIR"
}

#==============================================================================
# Build venv-only cache (smaller, for Cloudflare)
#==============================================================================
build_venv_cache() {
    log_info "Building venv-only cache bundle (for Cloudflare)..."

    # Ensure environment is set up
    if [ ! -d "/tmp/odoo19-venv" ]; then
        log_info "Environment not found, setting up first..."
        "$SCRIPT_DIR/setup_test_env.sh" --force --no-cache
    fi

    # Create cache directory
    rm -rf "$CACHE_DIR"
    mkdir -p "$CACHE_DIR"

    # Copy virtualenv only
    log_info "Copying Python virtualenv..."
    cp -a /tmp/odoo19-venv "$CACHE_DIR/"

    # Remove unnecessary files to reduce size
    log_info "Optimizing venv size..."
    find "$CACHE_DIR/odoo19-venv" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find "$CACHE_DIR/odoo19-venv" -name '*.pyc' -delete 2>/dev/null || true
    find "$CACHE_DIR/odoo19-venv" -name '*.pyo' -delete 2>/dev/null || true
    # Remove test directories from packages
    find "$CACHE_DIR/odoo19-venv" -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true
    find "$CACHE_DIR/odoo19-venv" -type d -name 'test' -exec rm -rf {} + 2>/dev/null || true

    # Create metadata file
    cat > "$CACHE_DIR/CACHE_INFO.txt" <<EOF
Odoo Venv Cache (venv only - use with Odoo from GitHub)
Version: $CACHE_VERSION
Created: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Python Version: $(python3.10 --version 2>&1)
Packages: $(ls "$CACHE_DIR/odoo19-venv/lib/python3.10/site-packages" | wc -l) site-packages

Odoo 19 source: https://github.com/odoo/odoo/archive/refs/heads/19.0.zip
EOF

    # Create tarball
    log_info "Creating tarball..."
    cd /tmp
    tar -czf "$VENV_CACHE_FILE" -C "$CACHE_DIR" .

    # Report size
    local size=$(du -h "/tmp/$VENV_CACHE_FILE" | cut -f1)
    log_success "Venv cache created: /tmp/$VENV_CACHE_FILE ($size)"

    # Cleanup
    rm -rf "$CACHE_DIR"
}

#==============================================================================
# Download file (handles Google Drive large files)
#==============================================================================
download_file() {
    local url="$1"
    local output="$2"

    # Check if it's a Google Drive URL
    if [[ "$url" == *"drive.google.com"* ]]; then
        local file_id=""

        # Extract file ID from various Google Drive URL formats
        if [[ "$url" == *"/file/d/"* ]]; then
            # Format: https://drive.google.com/file/d/FILE_ID/view
            file_id=$(echo "$url" | sed -n 's/.*\/file\/d\/\([^/]*\).*/\1/p')
        elif [[ "$url" == *"id="* ]]; then
            # Format: https://drive.google.com/uc?id=FILE_ID
            file_id=$(echo "$url" | sed -n 's/.*id=\([^&]*\).*/\1/p')
        fi

        if [ -z "$file_id" ]; then
            log_info "Could not extract Google Drive file ID from URL"
            return 1
        fi

        log_info "Detected Google Drive URL, file ID: $file_id"

        # For large files, Google Drive requires confirmation
        # Use curl with cookie handling to bypass virus scan warning
        local confirm_url="https://drive.google.com/uc?export=download&id=${file_id}"

        # First request to get confirmation token
        local confirm=$(curl -sc /tmp/gdrive_cookie "$confirm_url" | \
            sed -n 's/.*confirm=\([^&]*\).*/\1/p')

        if [ -n "$confirm" ]; then
            # Large file - use confirmation token
            log_info "Large file detected, using confirmation token..."
            curl -Lb /tmp/gdrive_cookie \
                "https://drive.google.com/uc?export=download&confirm=${confirm}&id=${file_id}" \
                -o "$output" --progress-bar
        else
            # Small file or direct download works
            curl -L "$confirm_url" -o "$output" --progress-bar
        fi

        rm -f /tmp/gdrive_cookie
    else
        # Regular URL - use curl
        curl -L "$url" -o "$output" --progress-bar
    fi
}

#==============================================================================
# Restore from cache
#==============================================================================
restore_cache() {
    local cache_url="$1"

    if [ -z "$cache_url" ]; then
        log_info "Usage: $0 --restore <url-to-cache-tarball>"
        exit 1
    fi

    log_info "Downloading cache from: $cache_url"
    download_file "$cache_url" "/tmp/$CACHE_FILE"

    log_info "Extracting cache..."
    mkdir -p /tmp/odoo-env-cache
    tar -xzf "/tmp/$CACHE_FILE" -C /tmp/odoo-env-cache

    log_info "Moving to final locations..."
    rm -rf /tmp/odoo-19 /tmp/odoo19-venv
    mv /tmp/odoo-env-cache/odoo-19 /tmp/
    mv /tmp/odoo-env-cache/odoo19-venv /tmp/

    # Fix venv paths (they may have different /tmp structure)
    log_info "Fixing virtualenv paths..."
    # The venv should work as-is since we use /tmp consistently

    rm -rf /tmp/odoo-env-cache "/tmp/$CACHE_FILE"

    log_success "Cache restored! Now run: ./scripts/setup_test_env.sh --links-only"
}

#==============================================================================
# Upload to GitHub Release (requires gh CLI)
#==============================================================================
upload_release() {
    if ! command -v gh &> /dev/null; then
        log_info "GitHub CLI (gh) not available. Manual upload required."
        log_info "Upload /tmp/$CACHE_FILE to a GitHub Release"
        return 1
    fi

    log_info "Creating GitHub Release: $CACHE_VERSION"
    gh release create "$CACHE_VERSION" \
        --title "Environment Cache $CACHE_VERSION" \
        --notes "Pre-built Odoo 19 environment cache for fast setup" \
        "/tmp/$CACHE_FILE"

    log_success "Release created! Download URL:"
    gh release view "$CACHE_VERSION" --json assets -q '.assets[0].url'
}

#==============================================================================
# Main
#==============================================================================
case "${1:-build}" in
    build|--build)
        build_cache
        ;;
    build-venv|--build-venv)
        build_venv_cache
        ;;
    upload|--upload)
        build_cache
        upload_release
        ;;
    restore|--restore)
        restore_cache "$2"
        ;;
    *)
        echo "Usage: $0 {build|build-venv|upload|restore <url>}"
        echo ""
        echo "Commands:"
        echo "  build           Build full cache bundle (/tmp/$CACHE_FILE) ~350MB"
        echo "  build-venv      Build venv-only bundle (/tmp/$VENV_CACHE_FILE) ~150MB"
        echo "  upload          Build and upload to GitHub Release"
        echo "  restore <url>   Download and extract cache from URL"
        echo ""
        echo "For Cloudflare hosting, use 'build-venv' (smaller file)"
        exit 1
        ;;
esac
