#!/bin/bash
# Odoo 19 Test Environment Setup (Optimized for Claude Code on the web)
#
# This script sets up the Odoo 19 test environment with smart caching:
# - Tries pre-built cache bundle first (fastest: ~30s)
# - Falls back to downloading Odoo + uv pip install (~2min)
# - Skips setup entirely if environment is already ready (<1s)
# - Runs automatically via SessionStart hook
#
# Manual usage:
#   ./scripts/setup_test_env.sh              # Smart setup (cache first)
#   ./scripts/setup_test_env.sh --force      # Force full rebuild
#   ./scripts/setup_test_env.sh --no-cache   # Skip cache, build from scratch
#   ./scripts/setup_test_env.sh --links-only # Only refresh module symlinks

# Check if running in Claude Code remote environment
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
    echo "This script is designed for Claude Code remote environments."
    echo ""
    echo "For local development, use Docker:"
    echo "  invoke test-eh-deps --modules=<module_name> --skip=queue_job --mode=init --db-filter='^devel\$'"
    echo ""
    echo "Tip: Use --mode=update to re-run tests after code changes."
    exit 0
fi

set -e

# Configuration
ODOO_PATH="/tmp/odoo-19"
ODOO_VENV="/tmp/odoo19-venv"
ODOO_CONFIG="/tmp/odoo19-test.conf"
ADDONS_DIR="/tmp/odoo19-addons"
SETUP_MARKER="/tmp/.odoo_env_ready"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements-odoo19.txt"

# Pre-built cache URLs (fastest setup path)
# Venv cache (~150MB) - override with PROJECT_VENV_CACHE_URL environment variable
VENV_CACHE_URL="${PROJECT_VENV_CACHE_URL:-}"
# Odoo source - nightly builds (Odoo's CDN, faster than GitHub)
ODOO_NIGHTLY_URL="https://nightly.odoo.com/19.0/nightly/tgz/odoo_19.0.latest.tar.gz"
ODOO_GITHUB_URL="https://github.com/odoo/odoo/archive/refs/heads/19.0.zip"
VENV_CACHE_FILE="/tmp/odoo19-venv.tar.gz"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Check if uv is available (10-100x faster than pip)
if command -v uv &> /dev/null; then
    USE_UV=true
    log_info "Using uv for fast package installation"
else
    USE_UV=false
    log_warn "uv not found, falling back to pip (slower)"
fi

# Parse arguments
FORCE_REBUILD=false
LINKS_ONLY=false
USE_CACHE=true
while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f) FORCE_REBUILD=true; shift ;;
        --links-only|-l) LINKS_ONLY=true; shift ;;
        --no-cache) USE_CACHE=false; shift ;;
        *) shift ;;
    esac
done

#==============================================================================
# Quick check: Is environment already ready?
#==============================================================================
check_env_ready() {
    # Check marker file and key components
    [ -f "$SETUP_MARKER" ] && \
    [ -d "$ODOO_PATH" ] && \
    [ -f "$ODOO_PATH/odoo-bin" ] && \
    [ -d "$ODOO_VENV" ] && \
    [ -f "$ODOO_VENV/bin/python" ] && \
    [ -f "$ODOO_CONFIG" ]
}

#==============================================================================
# Refresh only module symlinks (fast operation)
#==============================================================================
refresh_module_links() {
    log_info "Refreshing module symlinks..."

    # Create addons dir if needed
    mkdir -p "$ADDONS_DIR"

    # Remove old symlinks (keep any real directories)
    find "$ADDONS_DIR" -maxdepth 1 -type l -delete 2>/dev/null || true

    # Link all custom modules (any directory with __manifest__.py)
    local linked=0
    for module_dir in "$REPO_DIR"/*/; do
        module_dir="${module_dir%/}"
        if [ -d "$module_dir" ] && [ -f "$module_dir/__manifest__.py" ]; then
            ln -sf "$module_dir" "$ADDONS_DIR/"
            linked=$((linked + 1))
        fi
    done

    # Link OCA modules
    for oca_module in "queue_job" "base_user_role"; do
        if [ -d "$REPO_DIR/$oca_module" ] && [ -f "$REPO_DIR/$oca_module/__manifest__.py" ]; then
            ln -sf "$REPO_DIR/$oca_module" "$ADDONS_DIR/"
            linked=$((linked + 1))
        fi
    done

    log_success "Linked $linked modules"
}

#==============================================================================
# Handle --links-only mode
#==============================================================================
if [ "$LINKS_ONLY" = true ]; then
    refresh_module_links
    exit 0
fi

#==============================================================================
# Check if we can skip setup entirely
#==============================================================================
if [ "$FORCE_REBUILD" = false ] && check_env_ready; then
    log_success "Environment already ready (marker: $SETUP_MARKER)"
    log_info "Refreshing module links only..."
    refresh_module_links
    log_success "Setup complete (fast path - skipped downloads)"
    exit 0
fi

log_info "Full environment setup required..."
START_TIME=$(date +%s)

#==============================================================================
# Stage 1: PostgreSQL (usually already running in Claude Code)
#==============================================================================
setup_postgresql() {
    log_info "Checking PostgreSQL..."

    # Check if already running
    if pg_isready -q 2>/dev/null; then
        log_success "PostgreSQL is running"
    else
        log_info "Starting PostgreSQL..."
        service postgresql start 2>/dev/null || true
        sleep 2
    fi

    # Configure SSL off (avoid cert issues in cloud env)
    sed -i "s/^ssl = on/ssl = off/" /etc/postgresql/*/main/postgresql.conf 2>/dev/null || true

    # Configure pg_hba.conf to use trust authentication for local connections
    # This is required for runuser and test database creation to work
    local pg_hba=$(ls /etc/postgresql/*/main/pg_hba.conf 2>/dev/null | head -1)
    if [ -n "$pg_hba" ]; then
        # Replace peer with trust for local connections
        sed -i 's/local\s\+all\s\+all\s\+peer/local   all             all                                     trust/' "$pg_hba" 2>/dev/null || true
        sed -i 's/local\s\+all\s\+postgres\s\+peer/local   all             postgres                                trust/' "$pg_hba" 2>/dev/null || true
        # Reload PostgreSQL to apply changes
        pg_ctlcluster "$(ls /etc/postgresql/ | head -1)" main reload 2>/dev/null || \
        service postgresql reload 2>/dev/null || true
        sleep 1
    fi

    # Create odoo user if needed
    if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_user WHERE usename='odoo'" 2>/dev/null | grep -q 1; then
        log_info "Creating odoo database user..."
        runuser -u postgres -- psql -c "CREATE USER odoo WITH PASSWORD 'odoo_password' SUPERUSER CREATEDB;" 2>/dev/null || \
        runuser -u postgres -- psql -c "ALTER USER odoo WITH PASSWORD 'odoo_password' SUPERUSER CREATEDB;" 2>/dev/null || true
    fi

    log_success "PostgreSQL ready"
}

#==============================================================================
# Stage 2: Python venv (reuse if valid)
#==============================================================================
setup_venv() {
    # Check if existing venv works AND has packages
    if [ -f "$ODOO_VENV/bin/python" ]; then
        if "$ODOO_VENV/bin/python" --version 2>/dev/null | grep -q "3.10\|3.11\|3.12"; then
            # Only reuse if packages are installed (babel is critical for Odoo)
            if "$ODOO_VENV/bin/python" -c "import babel" 2>/dev/null; then
                log_success "Reusing existing virtualenv at $ODOO_VENV"
                return 0
            fi
            # Venv exists but empty - will be reinstalled
        fi
    fi

    log_info "Creating Python virtualenv..."
    rm -rf "$ODOO_VENV"

    if [ "$USE_UV" = true ]; then
        # uv venv is faster and handles Python version selection
        uv venv "$ODOO_VENV" --python 3.10 2>/dev/null || uv venv "$ODOO_VENV"
    else
        python3.10 -m venv "$ODOO_VENV" 2>/dev/null || python3 -m venv "$ODOO_VENV"
        "$ODOO_VENV/bin/pip" install --quiet --upgrade pip
    fi
    log_success "Virtualenv created"
}

#==============================================================================
# Stage 3: Download Odoo 19 (reuse if exists)
#==============================================================================
download_odoo() {
    # Check if existing Odoo is valid
    if [ -f "$ODOO_PATH/odoo-bin" ] && [ -f "$ODOO_PATH/odoo/release.py" ]; then
        if grep -q "version_info = (19" "$ODOO_PATH/odoo/release.py" 2>/dev/null; then
            log_success "Reusing existing Odoo 19 at $ODOO_PATH"
            return 0
        fi
    fi

    log_info "Downloading Odoo 19.0 (~200MB)..."
    rm -rf "$ODOO_PATH"

    # Try nightly.odoo.com first (faster CDN), fall back to GitHub
    local tar_file="/tmp/odoo-19.0.tar.gz"
    local zip_file="/tmp/odoo-19.0.zip"

    # Check for cached files first (and validate them)
    if [ -f "$tar_file" ] && tar -tzf "$tar_file" &>/dev/null; then
        log_info "Reusing cached tarball"
        log_info "Extracting Odoo..."
        tar -xzf "$tar_file" -C /tmp/
        # Nightly tarball extracts to odoo-19.0-YYYYMMDD format
        mv /tmp/odoo-19.0* "$ODOO_PATH" 2>/dev/null || true
    elif [ -f "$zip_file" ] && unzip -t "$zip_file" &>/dev/null; then
        log_info "Reusing cached zip file"
        log_info "Extracting Odoo..."
        unzip -q "$zip_file" -d /tmp/
        mv /tmp/odoo-19.0 "$ODOO_PATH"
    else
        # Remove any corrupted cached files
        rm -f "$tar_file" "$zip_file" 2>/dev/null || true
        # Try nightly first (Odoo's CDN)
        log_info "Trying nightly.odoo.com (faster CDN)..."
        if wget -q -O "$tar_file" "$ODOO_NIGHTLY_URL" 2>/dev/null; then
            log_info "Extracting Odoo..."
            tar -xzf "$tar_file" -C /tmp/
            # Nightly tarball extracts to odoo-19.0-YYYYMMDD format
            mv /tmp/odoo-19.0* "$ODOO_PATH" 2>/dev/null || true
        else
            # Fall back to GitHub
            log_warn "Nightly download failed, trying GitHub..."
            rm -f "$tar_file"
            wget -q -O "$zip_file" "$ODOO_GITHUB_URL"
            log_info "Extracting Odoo..."
            unzip -q "$zip_file" -d /tmp/
            mv /tmp/odoo-19.0 "$ODOO_PATH"
        fi
    fi

    log_success "Odoo 19 ready"
}

#==============================================================================
# Stage 4: Install Python dependencies (use uv for speed)
#==============================================================================
install_dependencies() {
    log_info "Installing Python dependencies..."

    # Install system libraries required for Python packages that need compilation
    if command -v apt-get &> /dev/null; then
        log_info "Installing system libraries for Python packages..."
        apt-get update -qq > /dev/null 2>&1 || true
        apt-get install -y -qq libldap2-dev libsasl2-dev libpq-dev > /dev/null 2>&1 || true
    fi

    if [ "$USE_UV" = true ]; then
        # uv is 10-100x faster than pip
        if [ -f "$REQUIREMENTS_FILE" ]; then
            log_info "Installing with uv from requirements file (fast)..."
            uv pip install --quiet --python "$ODOO_VENV/bin/python" -r "$REQUIREMENTS_FILE"
        else
            log_info "Installing with uv (inline packages)..."
            uv pip install --quiet --python "$ODOO_VENV/bin/python" \
                'Babel>=2.9.1' 'chardet>=4.0.0' 'cryptography>=3.4.8' 'docutils>=0.17' \
                'freezegun>=1.1.0' 'geoip2>=2.9.0' 'greenlet>=1.1.2' 'gevent>=21.12.0' \
                'Jinja2>=3.0.3' 'libsass>=0.20.1' 'lxml>=4.8.0' 'lxml-html-clean' \
                'MarkupSafe>=2.0.1' 'num2words>=0.5.10' 'ofxparse>=0.21' 'openpyxl>=3.1.0' \
                'passlib>=1.7.4' 'Pillow>=9.0.1' 'polib>=1.1.1' 'psutil>=5.9.0' \
                'psycopg2-binary>=2.9.2' 'pyopenssl>=21.0.0' 'PyPDF2>=2.10.0,<3.0.0' \
                'python-dateutil>=2.8.1' 'python-ldap>=3.4.0' 'python-stdnum>=1.17' \
                'pytz' 'qrcode>=7.3.1' 'reportlab>=3.6.8' 'requests>=2.25.1' \
                'rjsmin>=1.1.0' 'rcssmin' 'Werkzeug>=2.0.2' 'xlrd>=1.2.0' \
                'XlsxWriter>=3.0.2' 'xlwt>=1.3.0' 'zeep>=4.1.0' \
                'asn1crypto>=1.5.1' 'python-barcode>=0.14.0' 'python-magic>=0.4.27' \
                'vobject>=0.9.6' 'pycountry>=22.3.5' 'ebaysdk>=2.2.0' 'decorator>=5.1.1' \
                'idna' 'urllib3' 'pypdf' faker phonenumbers pydot html2text websocket-client \
                'fastapi>=0.112.2' 'ujson>=5.4.0' 'jwcrypto>=1.5.6' \
                schwifty pandas numpy shapely pyproj geopandas
            # Additional Odoo 19 specific dependencies
            uv pip install --quiet --python "$ODOO_VENV/bin/python" \
                'beautifulsoup4' 'cbor2' 'asn1crypto' 'vobject' 'python-magic' 'pyusb'
        fi
    else
        # Fallback to pip
        source "$ODOO_VENV/bin/activate"

        if [ -f "$REQUIREMENTS_FILE" ]; then
            log_info "Installing with pip from requirements file..."
            pip install --quiet -r "$REQUIREMENTS_FILE"
        else
            log_info "Installing with pip from inline list (slower)..."
            pip install --quiet \
                'Babel>=2.9.1' 'chardet>=4.0.0' 'cryptography>=3.4.8' 'docutils>=0.17' \
                'freezegun>=1.1.0' 'geoip2>=2.9.0' 'greenlet>=1.1.2' 'gevent>=21.12.0' \
                'Jinja2>=3.0.3' 'libsass>=0.20.1' 'lxml>=4.8.0' 'lxml-html-clean' \
                'MarkupSafe>=2.0.1' 'num2words>=0.5.10' 'ofxparse>=0.21' 'openpyxl>=3.1.0' \
                'passlib>=1.7.4' 'Pillow>=9.0.1' 'polib>=1.1.1' 'psutil>=5.9.0' \
                'psycopg2-binary>=2.9.2' 'pyopenssl>=21.0.0' 'PyPDF2>=2.10.0,<3.0.0' \
                'python-dateutil>=2.8.1' 'python-ldap>=3.4.0' 'python-stdnum>=1.17' \
                'pytz' 'qrcode>=7.3.1' 'reportlab>=3.6.8' 'requests>=2.25.1' \
                'rjsmin>=1.1.0' 'rcssmin' 'Werkzeug>=2.0.2' 'xlrd>=1.2.0' \
                'XlsxWriter>=3.0.2' 'xlwt>=1.3.0' 'zeep>=4.1.0' \
                'asn1crypto>=1.5.1' 'python-barcode>=0.14.0' 'python-magic>=0.4.27' \
                'vobject>=0.9.6' 'pycountry>=22.3.5' 'ebaysdk>=2.2.0' 'decorator>=5.1.1'
            pip install --quiet faker phonenumbers pydot html2text websocket-client
            pip install --quiet 'fastapi>=0.112.2' 'ujson>=5.4.0' 'jwcrypto>=1.5.6'
            pip install --quiet schwifty pandas numpy shapely pyproj geopandas
            # Additional Odoo 19 specific dependencies
            pip install --quiet beautifulsoup4 cbor2 asn1crypto vobject python-magic pyusb \
                gevent decorator idna urllib3 pypdf xlwt
        fi
    fi

    log_success "Python dependencies installed"
}

#==============================================================================
# Stage 5: Create Odoo config
#==============================================================================
create_config() {
    log_info "Creating Odoo configuration..."

    cat > "$ODOO_CONFIG" <<EOF
[options]
addons_path = $ODOO_PATH/addons,$ODOO_PATH/odoo/addons,$ADDONS_DIR
db_host = localhost
db_port = 5432
db_user = odoo
db_password = odoo_password
admin_passwd = admin
db_template = template0
log_level = info
EOF

    log_success "Configuration created at $ODOO_CONFIG"
}

#==============================================================================
# Try restoring venv from cache (fastest path)
#==============================================================================
try_restore_venv_cache() {
    if [ "$USE_CACHE" = false ] || [ -z "$VENV_CACHE_URL" ]; then
        return 1
    fi

    # Skip if venv already exists AND has required packages installed
    if [ -f "$ODOO_VENV/bin/python" ]; then
        if "$ODOO_VENV/bin/python" --version 2>/dev/null | grep -q "3.10\|3.11\|3.12"; then
            # Verify critical packages are installed (babel is required for Odoo to start)
            if "$ODOO_VENV/bin/python" -c "import babel" 2>/dev/null; then
                log_success "Reusing existing virtualenv at $ODOO_VENV"
                return 0
            else
                log_warn "Venv exists but missing packages, will reinstall"
            fi
        fi
    fi

    log_info "Trying pre-built venv cache (fastest path)..."
    log_info "Downloading from: $VENV_CACHE_URL"

    # Download venv cache bundle
    if ! curl -fSL "$VENV_CACHE_URL" -o "$VENV_CACHE_FILE" --progress-bar 2>/dev/null; then
        log_warn "Venv cache download failed, falling back to manual setup"
        rm -f "$VENV_CACHE_FILE"
        return 1
    fi

    # Verify it's a valid tarball (not an error page)
    if ! tar -tzf "$VENV_CACHE_FILE" &>/dev/null; then
        log_warn "Invalid venv cache file, falling back to manual setup"
        rm -f "$VENV_CACHE_FILE"
        return 1
    fi

    log_info "Extracting venv cache..."
    rm -rf /tmp/odoo-env-cache
    mkdir -p /tmp/odoo-env-cache

    if ! tar -xzf "$VENV_CACHE_FILE" -C /tmp/odoo-env-cache; then
        log_warn "Venv cache extraction failed, falling back to manual setup"
        rm -rf /tmp/odoo-env-cache "$VENV_CACHE_FILE"
        return 1
    fi

    # Move venv to final location
    log_info "Installing cached venv..."
    rm -rf "$ODOO_VENV"
    mv /tmp/odoo-env-cache/odoo19-venv "$ODOO_VENV"

    # Cleanup
    rm -rf /tmp/odoo-env-cache "$VENV_CACHE_FILE"

    log_success "Venv cache restored successfully!"
    return 0
}

#==============================================================================
# Main execution
#==============================================================================
main() {
    setup_postgresql

    # Run Odoo download and venv setup in PARALLEL for faster setup
    # These are independent operations that can run concurrently

    log_info "Starting parallel setup (Odoo download + venv)..."

    # Start Odoo download in background
    download_odoo &
    local odoo_pid=$!

    # Start venv setup in background (try cache, fall back to manual)
    (
        if try_restore_venv_cache; then
            log_info "Using cached venv"
        else
            setup_venv
            install_dependencies
        fi
    ) &
    local venv_pid=$!

    # Wait for both to complete
    local odoo_status=0
    local venv_status=0

    wait $odoo_pid || odoo_status=$?
    wait $venv_pid || venv_status=$?

    # Check for failures
    if [ $odoo_status -ne 0 ]; then
        echo "ERROR: Odoo download failed"
        exit 1
    fi
    if [ $venv_status -ne 0 ]; then
        echo "ERROR: Venv setup failed"
        exit 1
    fi

    log_success "Parallel setup complete!"

    refresh_module_links
    create_config

    # Create marker file
    date > "$SETUP_MARKER"

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    log_success "=========================================="
    log_success "Environment ready! Setup took ${DURATION}s"
    log_success "=========================================="
    echo ""
    echo "Run tests with:"
    echo "  ./scripts/test_single_module.sh <module_name>"
    echo ""
}

main
