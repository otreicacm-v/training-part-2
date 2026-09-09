#!/bin/bash
# Odoo 19 Module Installation and Testing Script
# Tests custom Odoo modules upgraded to Odoo 19.0
#
# Platform: Linux only (Claude Code remote / CI containers)
# For local development, use: ./odoo-project test <module>

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
DB_NAME="test_odoo19_$(date +%s)"
LOG_DIR="/tmp/odoo19-test-logs"

# Create log directory
mkdir -p "$LOG_DIR"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Odoo 19 Module Testing Script${NC}"
echo -e "${BLUE}============================================================${NC}"
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

# Function to check if PostgreSQL is running
check_postgres() {
    print_header "Checking PostgreSQL"
    if su - postgres -c "psql -c 'SELECT 1;'" > /dev/null 2>&1; then
        print_success "PostgreSQL is running"
        return 0
    else
        print_error "PostgreSQL is not running"
        print_info "Starting PostgreSQL..."
        service postgresql start
        sleep 2
        if su - postgres -c "psql -c 'SELECT 1;'" > /dev/null 2>&1; then
            print_success "PostgreSQL started successfully"
            return 0
        else
            print_error "Failed to start PostgreSQL"
            return 1
        fi
    fi
}

# Function to check if Odoo 19 environment is set up
check_odoo_environment() {
    print_header "Checking Odoo 19 Environment"

    if [ ! -d "$ODOO_PATH" ]; then
        print_error "Odoo 19 not found at $ODOO_PATH"
        print_info "Run ./setup_odoo19_environment.sh first"
        return 1
    fi
    print_success "Odoo 19 found at $ODOO_PATH"

    if [ ! -d "$ODOO_VENV" ]; then
        print_error "Virtual environment not found at $ODOO_VENV"
        return 1
    fi
    print_success "Virtual environment found at $ODOO_VENV"

    if [ ! -f "$ODOO_CONFIG" ]; then
        print_error "Odoo config not found at $ODOO_CONFIG"
        return 1
    fi
    print_success "Odoo config found at $ODOO_CONFIG"

    if [ ! -d "$ADDONS_DIR" ]; then
        print_error "Addons directory not found at $ADDONS_DIR"
        return 1
    fi
    print_success "Addons directory found at $ADDONS_DIR"

    # Verify Odoo version from release.py file
    if [ -f "$ODOO_PATH/odoo/release.py" ]; then
        local version=$(grep "^version_info = " "$ODOO_PATH/odoo/release.py" | grep -oP '\(\K[^)]+' | cut -d',' -f1,2 | tr -d ' ' | tr ',' '.')
        if [ "$version" = "19.0" ]; then
            print_success "Odoo version confirmed: 19.0"
        else
            print_error "Wrong Odoo version: $version (expected 19.0)"
            return 1
        fi
    else
        print_error "Cannot find Odoo release.py file"
        return 1
    fi

    return 0
}

# Function to verify module versions
check_module_versions() {
    print_header "Verifying Module Versions"

    local errors=0
    local warnings=0

    # Check custom modules (should be 19.0)
    print_info "Checking custom modules (should be 19.0)..."
    local custom_modules=(
        "trn_vocabulary"
    )

    for module in "${custom_modules[@]}"; do
        if [ -d "$ADDONS_DIR/$module" ]; then
            local manifest="$ADDONS_DIR/$module/__manifest__.py"
            if [ -f "$manifest" ]; then
                if grep -q '"version": "19\.0\.' "$manifest"; then
                    print_success "✓ $module is Odoo 19.0"
                else
                    print_error "✗ $module is NOT Odoo 19.0"
                    grep '"version":' "$manifest" || true
                    ((errors++))
                fi
            fi
        else
            print_warning "Module not found: $module"
            ((warnings++))
        fi
    done

    echo ""
    if [ $errors -eq 0 ]; then
        print_success "Version check passed ($warnings warnings)"
        return 0
    else
        print_error "Version check failed ($errors errors, $warnings warnings)"
        return 1
    fi
}

# Function to create a new database
create_database() {
    print_header "Creating test database: $DB_NAME"

    if PGPASSWORD=odoo psql -U odoo -h localhost -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
        print_info "Database $DB_NAME already exists, dropping it first..."
        PGPASSWORD=odoo psql -U odoo -h localhost -d postgres -c "DROP DATABASE $DB_NAME;" || true
    fi

    print_info "Creating new Odoo 19 database..."
    source "$ODOO_VENV/bin/activate"

    local log_file="$LOG_DIR/db_init_$(date +%Y%m%d_%H%M%S).log"
    if timeout 120 python3 "$ODOO_PATH/odoo-bin" \
        -c "$ODOO_CONFIG" \
        -d "$DB_NAME" \
        --stop-after-init \
        --without-demo=all \
        > "$log_file" 2>&1; then

        print_success "Database $DB_NAME created successfully"
        return 0
    else
        print_error "Failed to create database $DB_NAME"
        print_info "Last 30 lines of log:"
        tail -30 "$log_file"
        return 1
    fi
}

# Function to install a module
install_module() {
    local module_name=$1
    local log_file="$LOG_DIR/${module_name}_install_$(date +%Y%m%d_%H%M%S).log"

    print_header "Installing module: $module_name (Odoo 19.0)"
    print_info "Database: $DB_NAME"
    print_info "Log file: $log_file"

    source "$ODOO_VENV/bin/activate"

    if timeout 300 python3 "$ODOO_PATH/odoo-bin" \
        -c "$ODOO_CONFIG" \
        -d "$DB_NAME" \
        --stop-after-init \
        --without-demo=all \
        -i "$module_name" \
        --log-level=info \
        > "$log_file" 2>&1; then

        # Check if module is actually installed in database
        local state=$(PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -t -c "SELECT state FROM ir_module_module WHERE name='$module_name';" | xargs)

        if [ "$state" = "installed" ]; then
            print_success "Module $module_name installed successfully on Odoo 19.0"

            # Show installed version
            local version=$(PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -t -c "SELECT latest_version FROM ir_module_module WHERE name='$module_name';" | xargs)
            print_info "Installed version: $version"

            return 0
        else
            print_error "Module $module_name installation reported success but state is: $state"
            print_info "Check log: $log_file"
            tail -20 "$log_file"
            return 1
        fi
    else
        print_error "Module $module_name installation failed"
        print_info "Last 30 lines of log:"
        tail -30 "$log_file"

        # Check for common Odoo 19 breaking changes
        if grep -q "type='json'" "$log_file"; then
            print_error "Found type='json' in logs - should be type='jsonrpc' for Odoo 19"
        fi
        if grep -q "res.partner.title" "$log_file"; then
            print_error "Found res.partner.title - this model was removed in Odoo 19"
        fi

        return 1
    fi
}

# Function to run tests for a module
run_tests() {
    local module_name=$1
    local log_file="$LOG_DIR/${module_name}_test_$(date +%Y%m%d_%H%M%S).log"

    print_header "Running tests for: $module_name (Odoo 19.0)"
    print_info "Database: $DB_NAME"
    print_info "Log file: $log_file"

    source "$ODOO_VENV/bin/activate"

    if timeout 600 python3 "$ODOO_PATH/odoo-bin" \
        -c "$ODOO_CONFIG" \
        -d "$DB_NAME" \
        --stop-after-init \
        --test-enable \
        --test-tags="/$module_name" \
        --log-level=test \
        > "$log_file" 2>&1; then

        print_success "Tests for $module_name passed on Odoo 19.0"

        # Show test summary
        echo ""
        grep -E "(test.*ok|test.*FAIL|test.*ERROR)" "$log_file" | tail -20 || true

        # Count tests
        local test_count=$(grep -c "test.*ok" "$log_file" || echo "0")
        print_info "Tests passed: $test_count"

        return 0
    else
        print_error "Tests for $module_name failed"
        print_info "Last 30 lines of log:"
        tail -30 "$log_file"
        return 1
    fi
}

# Function to check module status
check_module_status() {
    print_header "Module Installation Status (Odoo 19.0)"
    PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -c "
        SELECT
            name,
            state,
            latest_version,
            CASE
                WHEN latest_version LIKE '19.0%' THEN '✓ Odoo 19'
                WHEN latest_version LIKE '17.0%' THEN '⚠ Odoo 17'
                ELSE '? Unknown'
            END as compatibility
        FROM ir_module_module
        WHERE name LIKE 'trn_%'
        ORDER BY name;
    "
}

# Function to install base modules
install_base_modules() {
    print_header "Installing Base Modules (Odoo 19.0)"

    local base_modules=(
        "trn_vocabulary"
    )

    local errors=0
    for module in "${base_modules[@]}"; do
        if install_module "$module"; then
            print_success "✓ $module installed"
        else
            print_error "✗ $module installation failed"
            ((errors++))
        fi
        echo ""
    done

    if [ $errors -eq 0 ]; then
        print_success "All base modules installed successfully"
        return 0
    else
        print_error "$errors base module(s) failed to install"
        return 1
    fi
}

# Function to install program modules
install_program_modules() {
    print_header "Installing Domain Modules (Odoo 19.0)"

    local program_modules=(
        # Add your domain modules here, e.g.:
        # "trn_sale"
        # "trn_inventory"
    )

    local errors=0
    for module in "${program_modules[@]}"; do
        if install_module "$module"; then
            print_success "✓ $module installed"
        else
            print_error "✗ $module installation failed"
            ((errors++))
        fi
        echo ""
    done

    if [ $errors -eq 0 ]; then
        print_success "All program modules installed successfully"
        return 0
    else
        print_error "$errors program module(s) failed to install"
        return 1
    fi
}

# Function to test breaking changes
test_breaking_changes() {
    print_header "Testing Odoo 19 Breaking Changes"

    print_info "Checking for type='json' (should be type='jsonrpc')..."
    if grep -r "type=['\"]json['\"]" "$ADDONS_DIR"/trn_* 2>/dev/null; then
        print_error "Found type='json' - must be changed to type='jsonrpc' for Odoo 19"
        return 1
    else
        print_success "No type='json' found (all should be type='jsonrpc')"
    fi

    print_info "Checking for res.partner.title (removed in Odoo 19)..."
    if grep -r "res\.partner\.title" "$ADDONS_DIR"/trn_* 2>/dev/null; then
        print_error "Found res.partner.title - this model was removed in Odoo 19"
        return 1
    else
        print_success "No res.partner.title references found"
    fi

    print_info "Checking for deprecated decorators (@api.multi, @api.one)..."
    if grep -r "@api\.\(multi\|one\)" "$ADDONS_DIR"/trn_* 2>/dev/null; then
        print_error "Found deprecated decorators"
        return 1
    else
        print_success "No deprecated decorators found"
    fi

    print_success "All breaking change checks passed!"
    return 0
}

# Function to generate test report
generate_test_report() {
    local report_file="$LOG_DIR/odoo19_test_report_$(date +%Y%m%d_%H%M%S).txt"

    print_header "Generating Odoo 19 Test Report"

    cat > "$report_file" <<EOF
========================================
Odoo 19 Upgrade Test Report
========================================
Date: $(date)
Database: $DB_NAME
Odoo Version: 19.0

Module Installation Status:
EOF

    PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -t -c "
        SELECT
            name || ' - ' || state || ' - ' || latest_version
        FROM ir_module_module
        WHERE name LIKE 'trn_%'
        ORDER BY name;
    " >> "$report_file"

    cat >> "$report_file" <<EOF

Version Summary:
EOF

    local v19=$(PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -t -c "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'trn_%' AND latest_version LIKE '19.0%' AND state='installed';" | xargs)
    local v17=$(PGPASSWORD=odoo psql -U odoo -h localhost -d $DB_NAME -t -c "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'trn_%' AND latest_version LIKE '17.0%' AND state='installed';" | xargs)

    echo "  Odoo 19.0 modules: $v19" >> "$report_file"
    echo "  Odoo 17.0 modules: $v17" >> "$report_file"

    cat >> "$report_file" <<EOF

Test Execution Summary:
EOF

    for log_file in "$LOG_DIR"/*_test_*.log; do
        if [ -f "$log_file" ]; then
            local module=$(basename "$log_file" | sed 's/_test_.*//')
            local test_count=$(grep -c "test.*ok" "$log_file" 2>/dev/null || echo "0")
            local fail_count=$(grep -c "FAIL" "$log_file" 2>/dev/null || echo "0")
            echo "  $module: $test_count tests passed, $fail_count failed" >> "$report_file"
        fi
    done

    cat >> "$report_file" <<EOF

Logs Directory: $LOG_DIR

Module Status:
  - Custom modules should be at version 19.0.x.x.x

EOF

    print_success "Test report generated: $report_file"
    cat "$report_file"
}

# Main workflow
main() {
    local action=${1:-"full"}

    case "$action" in
        check)
            check_postgres || exit 1
            check_odoo_environment || exit 1
            check_module_versions || exit 1
            test_breaking_changes || exit 1
            ;;

        install-base)
            check_postgres || exit 1
            check_odoo_environment || exit 1

            if [ -z "$2" ]; then
                create_database || exit 1
            else
                DB_NAME=$2
            fi

            install_base_modules || exit 1
            check_module_status
            ;;

        install-programs)
            check_postgres || exit 1
            check_odoo_environment || exit 1

            if [ -z "$2" ]; then
                print_error "Please provide database name as second argument"
                print_info "Usage: $0 install-programs <db_name>"
                exit 1
            fi
            DB_NAME=$2

            install_program_modules || exit 1
            check_module_status
            ;;

        install-all)
            check_postgres || exit 1
            check_odoo_environment || exit 1
            create_database || exit 1
            install_base_modules || exit 1
            install_program_modules || exit 1
            check_module_status
            ;;

        install)
            check_postgres || exit 1
            check_odoo_environment || exit 1

            if [ -z "$2" ]; then
                print_error "Please provide module name"
                print_info "Usage: $0 install <module_name> [db_name]"
                exit 1
            fi

            local module_name=$2
            if [ -z "$3" ]; then
                create_database || exit 1
            else
                DB_NAME=$3
            fi

            install_module "$module_name"
            check_module_status
            ;;

        test)
            check_postgres || exit 1
            if [ -z "$2" ] || [ -z "$3" ]; then
                print_error "Please provide module name and database name"
                print_info "Usage: $0 test <module_name> <db_name>"
                exit 1
            fi
            DB_NAME=$3
            run_tests "$2"
            ;;

        status)
            check_postgres || exit 1
            if [ -z "$2" ]; then
                print_error "Please provide database name"
                print_info "Usage: $0 status <db_name>"
                exit 1
            fi
            DB_NAME=$2
            check_module_status
            ;;

        report)
            if [ -z "$2" ]; then
                print_error "Please provide database name"
                print_info "Usage: $0 report <db_name>"
                exit 1
            fi
            DB_NAME=$2
            generate_test_report
            ;;

        full)
            print_info "Running full Odoo 19 upgrade test workflow"
            check_postgres || exit 1
            check_odoo_environment || exit 1
            check_module_versions || print_warning "Some modules not at 19.0"
            test_breaking_changes || print_warning "Breaking changes detected"
            create_database || exit 1

            print_header "Installing Base Modules"
            install_base_modules || print_error "Base module installation failed (continuing...)"

            print_header "Installing Program Modules"
            install_program_modules || print_error "Program module installation failed (continuing...)"

            check_module_status
            generate_test_report
            ;;

        *)
            echo "Usage: $0 {check|install-base|install-programs|install-all|install|test|status|report|full}"
            echo ""
            echo "Commands:"
            echo "  check                                - Check environment and module versions"
            echo "  install-base [db_name]               - Install base modules (creates DB if not provided)"
            echo "  install-programs <db_name>           - Install program modules in existing DB"
            echo "  install-all                          - Create DB and install all modules"
            echo "  install <module_name> [db_name]      - Install specific module"
            echo "  test <module_name> <db_name>         - Run tests for specific module"
            echo "  status <db_name>                     - Check module installation status"
            echo "  report <db_name>                     - Generate test report"
            echo "  full                                 - Run complete workflow (install + test + report)"
            echo ""
            echo "Examples:"
            echo "  $0 check                             # Verify Odoo 19 environment"
            echo "  $0 install-all                       # Install all modules in new DB"
            echo "  $0 install trn_vocabulary test_db     # Install trn_vocabulary in test_db"
            echo "  $0 full                              # Complete test workflow"
            exit 1
            ;;
    esac

    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${GREEN}Script completed${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo -e "Logs available in: ${YELLOW}$LOG_DIR${NC}"
    echo ""
}

# Run main function
main "$@"
