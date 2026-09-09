#!/bin/bash
# Odoo 19 Environment Setup Script
# This script sets up the complete environment for testing Odoo modules on Odoo 19
#
# Usage:
#   ./setup_odoo19_environment.sh           # Full setup (rebuilds everything)
#   ./setup_odoo19_environment.sh --fast    # Fast mode (reuses existing downloads/venv)
#
# Fast mode optimizations:
#   - Reuses existing Python virtualenv if valid
#   - Reuses existing Odoo 19 download if valid
#   - Uses cached zip file if available
#   - Uses consolidated requirements file (faster pip resolution)
#
# For Claude Code on the web, use the SessionStart hook instead:
#   See .claude/settings.json and scripts/setup_test_env.sh
#
# Platform: Linux only (Claude Code remote / CI containers)
# For local development on macOS/Windows, use Docker: ./odoo-project start

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ODOO_PATH="/tmp/odoo-19"
ODOO_VENV="/tmp/odoo19-venv"
ODOO_CONFIG="/tmp/odoo19-test.conf"
ADDONS_DIR="/tmp/odoo19-addons"
REQUIREMENTS_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/requirements-odoo19.txt"
# Use current directory as repo dir (script should be run from repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PG_VERSION="16"

# Parse arguments for fast mode
FAST_MODE=false
for arg in "$@"; do
    case $arg in
        --fast|--reuse|-f) FAST_MODE=true ;;
    esac
done

# Check if uv is available (10-100x faster than pip)
if command -v uv &> /dev/null; then
    USE_UV=true
else
    USE_UV=false
fi

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Odoo 19 Environment Setup Script${NC}"
echo -e "${BLUE}============================================================${NC}"
if [ "$USE_UV" = true ]; then
    echo -e "${GREEN}Using uv for fast package installation${NC}"
fi
echo ""

# Function to print section headers
print_header() {
    echo -e "\n${BLUE}==>${NC} ${GREEN}$1${NC}\n"
}

# Function to print errors
print_error() {
    echo -e "${RED}ERROR:${NC} $1"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print info
print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

#==============================================================================
# STAGE 1: PostgreSQL Configuration
#==============================================================================

setup_postgresql() {
    print_header "Stage 1: Configuring PostgreSQL"

    # Fix SSL certificate permissions issue (common in cloud environments)
    print_info "Configuring PostgreSQL SSL settings..."
    sed -i "s/^ssl = on/ssl = off/" /etc/postgresql/${PG_VERSION}/main/postgresql.conf 2>/dev/null || true
    print_success "SSL configured for development environment"

    # Start PostgreSQL service
    print_info "Starting PostgreSQL ${PG_VERSION}..."
    if service postgresql start 2>/dev/null; then
        print_success "PostgreSQL started successfully"
    else
        print_warning "PostgreSQL might already be running"
    fi

    # Wait for PostgreSQL to be ready
    sleep 3

    # Configure trust authentication for local scripts
    print_info "Configuring trust authentication..."
    echo "local all postgres trust" > /tmp/pg_hba_new.conf
    cat /etc/postgresql/${PG_VERSION}/main/pg_hba.conf >> /tmp/pg_hba_new.conf
    cp /tmp/pg_hba_new.conf /etc/postgresql/${PG_VERSION}/main/pg_hba.conf
    print_success "Trust authentication configured"

    # Configure password authentication for Odoo
    print_info "Configuring password authentication for Odoo..."
    echo "host all odoo 127.0.0.1/32 md5" >> /etc/postgresql/${PG_VERSION}/main/pg_hba.conf
    print_success "Password authentication configured"

    # Reload PostgreSQL configuration
    print_info "Reloading PostgreSQL configuration..."
    pg_ctlcluster ${PG_VERSION} main reload
    print_success "PostgreSQL configuration reloaded"

    # Create Odoo superuser
    print_info "Creating Odoo database user..."
    if runuser -u postgres -- psql -c "SELECT 1 FROM pg_user WHERE usename='odoo';" | grep -q 1; then
        print_warning "User 'odoo' already exists, updating password..."
        runuser -u postgres -- psql -c "ALTER USER odoo WITH PASSWORD 'odoo' SUPERUSER;"
    else
        runuser -u postgres -- psql -c "CREATE USER odoo WITH PASSWORD 'odoo' SUPERUSER;"
    fi
    print_success "Odoo database user configured"

    # Verify PostgreSQL is working
    if runuser -u postgres -- psql -c "SELECT 1;" > /dev/null 2>&1; then
        print_success "PostgreSQL is running and accessible"
    else
        print_error "PostgreSQL verification failed"
        return 1
    fi
}

#==============================================================================
# STAGE 2: System & Python Dependencies
#==============================================================================

setup_dependencies() {
    print_header "Stage 2: Installing System & Python Dependencies"

    # Install system packages
    print_info "Installing system packages (this may take a moment)..."
    apt-get update -qq
    apt-get install -y -qq libpq-dev libldap2-dev libsasl2-dev python3.10 python3.10-venv python3.10-dev
    print_success "System packages installed"

    # Create Python virtual environment
    if [ -d "$ODOO_VENV" ]; then
        if [ "$FAST_MODE" = true ] && [ -f "$ODOO_VENV/bin/python" ]; then
            # In fast mode, reuse existing venv if it works
            if "$ODOO_VENV/bin/python" --version 2>/dev/null | grep -q "3.10\|3.11\|3.12"; then
                print_success "Reusing existing virtual environment at $ODOO_VENV (fast mode)"
                source "$ODOO_VENV/bin/activate"
                return 0
            fi
        fi
        print_warning "Virtual environment already exists at $ODOO_VENV"
        print_info "Removing existing virtual environment..."
        rm -rf "$ODOO_VENV"
    fi

    print_info "Creating Python 3.10 virtual environment..."
    if [ "$USE_UV" = true ]; then
        uv venv "$ODOO_VENV" --python 3.10 2>/dev/null || uv venv "$ODOO_VENV"
    else
        python3.10 -m venv "$ODOO_VENV"
        # Activate and upgrade pip for non-uv installs
        source "$ODOO_VENV/bin/activate"
        print_info "Upgrading pip..."
        pip install --quiet --upgrade pip
        print_success "pip upgraded"
    fi
    print_success "Virtual environment created at $ODOO_VENV"

    print_success "Python virtual environment ready"
}

#==============================================================================
# STAGE 3: Download Odoo 19 & Install Python Dependencies
#==============================================================================

clone_repositories() {
    print_header "Stage 3: Downloading Odoo 19 & Installing Python Dependencies"

    # Create directories
    mkdir -p "$ADDONS_DIR"

    # Download Odoo 19.0 as zip (much faster than git clone)
    if [ -d "$ODOO_PATH" ]; then
        if [ "$FAST_MODE" = true ] && [ -f "$ODOO_PATH/odoo-bin" ]; then
            # In fast mode, check if existing Odoo is version 19
            if grep -q "version_info = (19" "$ODOO_PATH/odoo/release.py" 2>/dev/null; then
                print_success "Reusing existing Odoo 19 at $ODOO_PATH (fast mode)"
            else
                print_warning "Existing Odoo is not version 19, downloading fresh..."
                rm -rf "$ODOO_PATH"
            fi
        else
            print_warning "Odoo already exists at $ODOO_PATH"
            print_info "Removing existing Odoo installation..."
            rm -rf "$ODOO_PATH"
        fi
    fi

    # Download if needed
    if [ ! -d "$ODOO_PATH" ]; then
        print_info "Downloading Odoo 19.0 as zip (faster than git clone)..."
        # Reuse cached zip if available
        if [ -f "/tmp/odoo-19.0.zip" ]; then
            print_info "Using cached zip file..."
        else
            wget -q -O /tmp/odoo-19.0.zip https://github.com/odoo/odoo/archive/refs/heads/19.0.zip
        fi
        print_info "Extracting Odoo 19.0..."
        unzip -q /tmp/odoo-19.0.zip -d /tmp/
        mv /tmp/odoo-19.0 "$ODOO_PATH"
        print_success "Odoo 19.0 downloaded and extracted successfully"
    fi

    # Install Odoo Python requirements
    print_info "Installing Odoo 19 Python dependencies..."

    if [ "$USE_UV" = true ]; then
        # Use uv (10-100x faster than pip)
        if [ -f "$REQUIREMENTS_FILE" ]; then
            print_info "Installing with uv from requirements file (fast)..."
            uv pip install --python "$ODOO_VENV/bin/python" -r "$REQUIREMENTS_FILE"
        else
            print_info "Installing with uv (fast)..."
            uv pip install --python "$ODOO_VENV/bin/python" \
                'asn1crypto==1.4.0' 'Babel==2.9.1' 'cbor2==5.4.2' 'chardet==4.0.0' \
                'cryptography==3.4.8' 'docutils==0.17' 'freezegun==1.1.0' 'geoip2==2.9.0' \
                'greenlet==1.1.2' 'idna==2.10' 'Jinja2==3.0.3' 'libsass==0.20.1' \
                'lxml==4.8.0' 'lxml-html-clean' 'MarkupSafe==2.0.1' 'num2words==0.5.10' \
                'ofxparse==0.21' 'openpyxl==3.0.9' 'passlib==1.7.4' 'Pillow==9.0.1' \
                'polib==1.1.1' 'psutil==5.9.0' 'psycopg2-binary==2.9.2' 'pyopenssl==21.0.0' \
                'PyPDF2==1.26.0' 'pyserial==3.5' 'python-dateutil==2.8.1' 'python-ldap==3.4.0' \
                'python-magic==0.4.24' 'python-stdnum==1.17' 'pytz' 'pyusb==1.2.1' \
                'qrcode==7.3.1' 'reportlab==3.6.8' 'requests==2.25.1' 'rjsmin==1.1.0' \
                'rcssmin' 'urllib3==1.26.5' 'vobject==0.9.6.1' 'Werkzeug==2.0.2' \
                'xlrd==1.2.0' 'XlsxWriter==3.0.2' 'xlwt==1.3.0' 'zeep==4.1.0' \
                faker phonenumbers pydot html2text websocket-client ebaysdk \
                'fastapi>=0.112.2' 'ujson>=5.4.0' 'jwcrypto>=1.5.6' \
                schwifty pandas numpy shapely Fiona matplotlib pyproj geopandas
        fi
        print_success "All Python packages installed (via uv)"
    else
        # Fallback to pip
        source "$ODOO_VENV/bin/activate"

        if [ -f "$REQUIREMENTS_FILE" ]; then
            print_info "Using consolidated requirements file..."
            pip install --quiet -r "$REQUIREMENTS_FILE"
            print_success "All Python packages installed"
        else
            # Install core Odoo dependencies
            # Note: Skipping gevent due to compilation issues on Python 3.10
            print_info "Installing core Odoo packages..."
            pip install --quiet \
                'asn1crypto==1.4.0' 'Babel==2.9.1' 'cbor2==5.4.2' 'chardet==4.0.0' \
                'cryptography==3.4.8' 'docutils==0.17' 'freezegun==1.1.0' 'geoip2==2.9.0' \
                'greenlet==1.1.2' 'idna==2.10' 'Jinja2==3.0.3' 'libsass==0.20.1' \
                'lxml==4.8.0' 'lxml-html-clean' 'MarkupSafe==2.0.1' 'num2words==0.5.10' \
                'ofxparse==0.21' 'openpyxl==3.0.9' 'passlib==1.7.4' 'Pillow==9.0.1' \
                'polib==1.1.1' 'psutil==5.9.0' 'psycopg2-binary==2.9.2' 'pyopenssl==21.0.0' \
                'PyPDF2==1.26.0' 'pyserial==3.5' 'python-dateutil==2.8.1' 'python-ldap==3.4.0' \
                'python-magic==0.4.24' 'python-stdnum==1.17' 'pytz' 'pyusb==1.2.1' \
                'qrcode==7.3.1' 'reportlab==3.6.8' 'requests==2.25.1' 'rjsmin==1.1.0' \
                'rcssmin' 'urllib3==1.26.5' 'vobject==0.9.6.1' 'Werkzeug==2.0.2' \
                'xlrd==1.2.0' 'XlsxWriter==3.0.2' 'xlwt==1.3.0' 'zeep==4.1.0'
            print_success "Core Odoo packages installed"

            print_info "Installing additional Python packages..."
            pip install --quiet faker phonenumbers pydot html2text websocket-client ebaysdk
            pip install --quiet 'fastapi>=0.112.2' 'ujson>=5.4.0' 'jwcrypto>=1.5.6'
            print_success "Additional packages installed"

            print_info "Installing additional dependencies..."
            pip install --quiet schwifty pandas numpy shapely Fiona matplotlib pyproj geopandas
            print_success "Additional packages installed"
        fi
    fi

    print_warning "Note: gevent skipped (compilation issues) - not needed for testing"
    print_success "All external dependencies are included in this repository"
}

#==============================================================================
# STAGE 4: Link Custom Modules
#==============================================================================

link_addons() {
    print_header "Stage 4: Linking Custom Modules"

    print_info "Repository directory: $REPO_DIR"

    cd "$REPO_DIR"
    local current=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    print_success "Using branch: $current"

    # Link all custom modules from the repository
    print_info "Scanning for custom Odoo modules (any directory with __manifest__.py)..."

    local linked_count=0
    for module_dir in "$REPO_DIR"/*/; do
        module_dir="${module_dir%/}"
        if [ -d "$module_dir" ] && [ -f "$module_dir/__manifest__.py" ]; then
            local module_name=$(basename "$module_dir")
            ln -sf "$module_dir" "$ADDONS_DIR/"
            ((linked_count++))
        fi
    done
    print_success "Linked $linked_count custom modules"

    # Link OCA modules from the repository (already included)
    print_info "Linking OCA modules (included in repository)..."

    # Link queue_job
    if [ -d "$REPO_DIR/queue_job" ] && [ -f "$REPO_DIR/queue_job/__manifest__.py" ]; then
        ln -sf "$REPO_DIR/queue_job" "$ADDONS_DIR/"
        print_success "Linked queue_job"
    else
        print_warning "queue_job not found in repository"
    fi

    # Link base_user_role
    if [ -d "$REPO_DIR/base_user_role" ] && [ -f "$REPO_DIR/base_user_role/__manifest__.py" ]; then
        ln -sf "$REPO_DIR/base_user_role" "$ADDONS_DIR/"
        print_success "Linked base_user_role"
    else
        print_warning "base_user_role not found in repository"
    fi

    # Count total modules
    local total_modules=$(find "$ADDONS_DIR" -maxdepth 1 \( -type l -o -type d \) ! -name "." | wc -l)
    print_success "Total modules in addons directory: $total_modules"

    echo ""
    print_success "════════════════════════════════════════════════════════════"
    print_success "✓  All modules linked from local repository"
    print_success "════════════════════════════════════════════════════════════"
    echo ""
}

#==============================================================================
# STAGE 5: Create Odoo 19 Configuration
#==============================================================================

create_odoo_config() {
    print_header "Stage 5: Creating Odoo 19 Configuration"

    print_info "Creating Odoo 19 configuration file at $ODOO_CONFIG..."

    cat > "$ODOO_CONFIG" <<EOF
[options]
addons_path = $ODOO_PATH/addons,$ODOO_PATH/odoo/addons,$ADDONS_DIR
db_host = localhost
db_port = 5432
db_user = odoo
db_password = odoo
admin_passwd = admin
db_template = template0
log_level = info
EOF

    print_success "Odoo 19 configuration file created"

    # Display configuration
    print_info "Configuration details:"
    echo -e "  ${YELLOW}Odoo Version:${NC} 19.0"
    echo -e "  ${YELLOW}Odoo Path:${NC} $ODOO_PATH"
    echo -e "  ${YELLOW}Virtual Env:${NC} $ODOO_VENV"
    echo -e "  ${YELLOW}Config File:${NC} $ODOO_CONFIG"
    echo -e "  ${YELLOW}Addons Dir:${NC} $ADDONS_DIR"
    echo -e "  ${YELLOW}Python:${NC} $(python3.10 --version)"
}

#==============================================================================
# STAGE 6: Verify Environment
#==============================================================================

verify_environment() {
    print_header "Stage 6: Verifying Odoo 19 Environment"

    local errors=0
    local warnings=0

    # Check PostgreSQL
    if runuser -u postgres -- psql -c "SELECT 1;" > /dev/null 2>&1; then
        print_success "PostgreSQL is accessible"
    else
        print_error "PostgreSQL is not accessible"
        ((errors++))
    fi

    # Check Odoo user
    if runuser -u postgres -- psql -c "SELECT 1 FROM pg_user WHERE usename='odoo';" | grep -q 1; then
        print_success "Odoo database user exists"
    else
        print_error "Odoo database user does not exist"
        ((errors++))
    fi

    # Check Odoo installation
    if [ -d "$ODOO_PATH" ] && [ -f "$ODOO_PATH/odoo-bin" ]; then
        print_success "Odoo 19 is installed at $ODOO_PATH"

        # Verify it's actually version 19
        local version=$("$ODOO_VENV/bin/python" "$ODOO_PATH/odoo-bin" --version 2>&1 | head -1)
        if echo "$version" | grep -q "19"; then
            print_success "Confirmed Odoo version: $version"
        else
            print_warning "Odoo version mismatch: $version"
            ((warnings++))
        fi
    else
        print_error "Odoo installation not found"
        ((errors++))
    fi

    # Check virtual environment
    if [ -d "$ODOO_VENV" ] && [ -f "$ODOO_VENV/bin/activate" ]; then
        print_success "Virtual environment exists at $ODOO_VENV"

        # Check Python version
        source "$ODOO_VENV/bin/activate"
        local py_version=$(python --version)
        if echo "$py_version" | grep -q "3.10"; then
            print_success "Python version: $py_version"
        else
            print_warning "Python version: $py_version (3.10+ recommended for Odoo 19)"
            ((warnings++))
        fi
    else
        print_error "Virtual environment not found"
        ((errors++))
    fi

    # Check configuration file
    if [ -f "$ODOO_CONFIG" ]; then
        print_success "Odoo configuration file exists"
    else
        print_error "Odoo configuration file not found"
        ((errors++))
    fi

    # Check addons directory
    if [ -d "$ADDONS_DIR" ]; then
        local addon_count=$(find "$ADDONS_DIR" -maxdepth 1 \( -type l -o -type d \) | wc -l)
        print_success "Addons directory exists with $addon_count modules"
    else
        print_error "Addons directory not found"
        ((errors++))
    fi

    # Check critical modules
    print_info "Checking critical modules..."
    local critical_modules=(
        "queue_job"
        "base_user_role"
    )
    for module in "${critical_modules[@]}"; do
        if [ -L "$ADDONS_DIR/$module" ] || [ -d "$ADDONS_DIR/$module" ]; then
            print_success "Module linked: $module"
        else
            print_error "Module missing: $module"
            ((errors++))
        fi
    done

    echo ""
    if [ $errors -eq 0 ] && [ $warnings -eq 0 ]; then
        print_success "Environment verification passed!"
        return 0
    elif [ $errors -eq 0 ]; then
        print_warning "Environment verification passed with $warnings warning(s)"
        return 0
    else
        print_error "Environment verification failed with $errors error(s)"
        return 1
    fi
}

#==============================================================================
# Main Execution
#==============================================================================

main() {
    local start_time=$(date +%s)

    print_info "Starting Odoo 19 environment setup..."
    print_info "This process may take 5-10 minutes depending on network speed"
    echo ""

    # Run all setup stages
    setup_postgresql || { print_error "PostgreSQL setup failed"; exit 1; }
    setup_dependencies || { print_error "Dependencies setup failed"; exit 1; }
    clone_repositories || { print_error "Repository cloning failed"; exit 1; }
    link_addons || { print_error "Addon linking failed"; exit 1; }
    create_odoo_config || { print_error "Configuration creation failed"; exit 1; }
    verify_environment || { print_error "Environment verification failed"; exit 1; }

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${GREEN}Odoo 19 Environment Setup Completed!${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""
    echo -e "${GREEN}Setup completed in $duration seconds${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo -e "  Run tests: ${GREEN}./scripts/test_single_module.sh <module_name>${NC}"
    echo -e "  Example:   ${GREEN}./scripts/test_single_module.sh trn_vocabulary${NC}"
    echo ""
    echo -e "${YELLOW}Important Paths:${NC}"
    echo -e "  Odoo 19:     ${GREEN}$ODOO_PATH${NC}"
    echo -e "  Config:      ${GREEN}$ODOO_CONFIG${NC}"
    echo -e "  Addons:      ${GREEN}$ADDONS_DIR${NC}"
    echo -e "  Virtual Env: ${GREEN}$ODOO_VENV${NC}"
    echo -e "  Repository:  ${GREEN}$REPO_DIR${NC}"
    echo ""
}

# Run main function
main "$@"
