#!/bin/bash
# Odoo 19 Environment Cleanup Script
# This script removes all temporary files and directories created during testing
#
# Platform: Linux only (Claude Code remote / CI containers)
# Cleans up the environment created by setup_odoo19_environment.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - matches setup script
ODOO_PATH="/tmp/odoo-19"
ODOO_VENV="/tmp/odoo19-venv"
ODOO_CONFIG="/tmp/odoo19-test.conf"
ADDONS_DIR="/tmp/odoo19-addons"
DEPS_DIR="/tmp/odoo19-deps"
LOG_DIR="/tmp/odoo19-test-logs"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Odoo 19 Environment Cleanup Script${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

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

# Function to get directory size
get_size() {
    if [ -d "$1" ]; then
        du -sh "$1" 2>/dev/null | cut -f1
    else
        echo "0"
    fi
}

# Calculate total space to be freed
print_info "Calculating disk space usage..."
total_size=0

if [ -d "$ODOO_PATH" ]; then
    odoo_size=$(get_size "$ODOO_PATH")
    print_info "Odoo 19:     $odoo_size ($ODOO_PATH)"
fi

if [ -d "$ODOO_VENV" ]; then
    venv_size=$(get_size "$ODOO_VENV")
    print_info "Virtual Env: $venv_size ($ODOO_VENV)"
fi

if [ -d "$ADDONS_DIR" ]; then
    addons_size=$(get_size "$ADDONS_DIR")
    print_info "Addons:      $addons_size ($ADDONS_DIR)"
fi

if [ -d "$DEPS_DIR" ]; then
    deps_size=$(get_size "$DEPS_DIR")
    print_info "Dependencies:$deps_size ($DEPS_DIR)"
fi

if [ -d "$LOG_DIR" ]; then
    logs_size=$(get_size "$LOG_DIR")
    print_info "Logs:        $logs_size ($LOG_DIR)"
fi

echo ""

# Confirm cleanup
if [ "$1" != "-f" ] && [ "$1" != "--force" ]; then
    echo -e "${YELLOW}This will remove all Odoo 19 test environment files.${NC}"
    echo -e "${YELLOW}Press Ctrl+C to cancel, or Enter to continue...${NC}"
    read -r
fi

echo ""
print_info "Starting cleanup..."
echo ""

# Remove Odoo 19 installation
if [ -d "$ODOO_PATH" ]; then
    print_info "Removing Odoo 19 installation..."
    rm -rf "$ODOO_PATH"
    print_success "Removed $ODOO_PATH"
else
    print_warning "$ODOO_PATH not found (already clean)"
fi

# Remove virtual environment
if [ -d "$ODOO_VENV" ]; then
    print_info "Removing virtual environment..."
    rm -rf "$ODOO_VENV"
    print_success "Removed $ODOO_VENV"
else
    print_warning "$ODOO_VENV not found (already clean)"
fi

# Remove addons directory
if [ -d "$ADDONS_DIR" ]; then
    print_info "Removing addons directory..."
    rm -rf "$ADDONS_DIR"
    print_success "Removed $ADDONS_DIR"
else
    print_warning "$ADDONS_DIR not found (already clean)"
fi

# Remove dependencies directory
if [ -d "$DEPS_DIR" ]; then
    print_info "Removing dependencies directory..."
    rm -rf "$DEPS_DIR"
    print_success "Removed $DEPS_DIR"
else
    print_warning "$DEPS_DIR not found (already clean)"
fi

# Remove config file
if [ -f "$ODOO_CONFIG" ]; then
    print_info "Removing Odoo configuration..."
    rm -f "$ODOO_CONFIG"
    print_success "Removed $ODOO_CONFIG"
else
    print_warning "$ODOO_CONFIG not found (already clean)"
fi

# Handle logs directory
if [ -d "$LOG_DIR" ]; then
    if [ "$2" == "--keep-logs" ]; then
        print_warning "Keeping logs at $LOG_DIR (--keep-logs specified)"
    else
        print_info "Removing test logs..."
        rm -rf "$LOG_DIR"
        print_success "Removed $LOG_DIR"
    fi
else
    print_warning "$LOG_DIR not found (already clean)"
fi

# Clean up any test databases (optional)
if command -v psql >/dev/null 2>&1; then
    print_info "Checking for test databases..."

    # List test databases
    test_dbs=$(PGPASSWORD=odoo psql -U odoo -h localhost -lqt 2>/dev/null | cut -d \| -f 1 | grep -E "test_odoo19_|test_contrib_" | xargs || echo "")

    if [ -n "$test_dbs" ]; then
        print_info "Found test databases: $test_dbs"

        if [ "$1" != "-f" ] && [ "$1" != "--force" ]; then
            echo -e "${YELLOW}Remove test databases? (y/N)${NC}"
            read -r response
            if [[ "$response" =~ ^[Yy]$ ]]; then
                for db in $test_dbs; do
                    PGPASSWORD=odoo psql -U odoo -h localhost -d postgres -c "DROP DATABASE IF EXISTS $db;" 2>/dev/null
                    print_success "Removed database: $db"
                done
            else
                print_warning "Keeping test databases"
            fi
        elif [ "$3" == "--remove-dbs" ]; then
            for db in $test_dbs; do
                PGPASSWORD=odoo psql -U odoo -h localhost -d postgres -c "DROP DATABASE IF EXISTS $db;" 2>/dev/null
                print_success "Removed database: $db"
            done
        fi
    else
        print_success "No test databases found"
    fi
fi

# Stop PostgreSQL if it was started by our script (optional)
if [ "$2" == "--stop-postgres" ]; then
    print_info "Stopping PostgreSQL..."
    service postgresql stop 2>/dev/null || print_warning "Failed to stop PostgreSQL (may not be running)"
    print_success "PostgreSQL stop attempted"
fi

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}Cleanup Completed!${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "${GREEN}The following has been cleaned up:${NC}"
echo -e "  ✓ Odoo 19 installation"
echo -e "  ✓ Python virtual environment"
echo -e "  ✓ Addons directory"
echo -e "  ✓ Dependencies directory"
echo -e "  ✓ Configuration files"

if [ "$2" != "--keep-logs" ]; then
    echo -e "  ✓ Test logs"
fi

echo ""
echo -e "${YELLOW}To run tests again:${NC}"
echo -e "  ./scripts/setup_odoo19_environment.sh"
echo ""
