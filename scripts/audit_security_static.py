#!/usr/bin/env python3
"""
Static security analysis for custom Odoo modules.
Checks compliance with V2 access rights principles without requiring Odoo runtime.

Usage:
    ./scripts/audit_security_static.py                    # Audit all modules
    ./scripts/audit_security_static.py trn_api       # Audit single module
    ./scripts/audit_security_static.py --json             # JSON output
    ./scripts/audit_security_static.py --check=acl        # Only ACL checks
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass
class Issue:
    severity: str  # ERROR or WARNING
    check: str  # Check category
    module: str
    file: str
    message: str
    line: int | None = None


@dataclass
class AuditResult:
    module: str
    errors: int = 0
    warnings: int = 0
    issues: list[Issue] = field(default_factory=list)


class StaticSecurityAuditor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.issues: list[Issue] = []

        # Technical group patterns that don't need privilege_id
        # These are tier-3 technical groups, not user-facing
        self.technical_group_patterns = [
            "_read",
            "_write",
            "_create",
            "_delete",  # CRUD permission groups
        ]

        # Groups that are external references (extending other modules)
        # These should not be flagged as missing privilege_id
        self.external_group_prefixes = [
            "trn_security.",  # References to trn_security module groups
            "base.",  # References to base module groups
        ]

    def audit_module(self, module_name: str, checks: set[str] | None = None) -> AuditResult:
        """Audit a single module."""
        module_path = self.root_dir / module_name
        if not module_path.exists():
            return AuditResult(module=module_name)

        result = AuditResult(module=module_name)

        # Run all checks or specific ones
        all_checks = checks is None

        if all_checks or "acl" in checks:
            self.check_acl_files(module_path, module_name, result)

        if all_checks or "rules" in checks:
            self.check_record_rules(module_path, module_name, result)

        if all_checks or "groups" in checks:
            self.check_security_groups(module_path, module_name, result)

        if all_checks or "legacy" in checks:
            self.check_legacy_patterns(module_path, module_name, result)

        if all_checks or "python" in checks:
            self.check_python_security(module_path, module_name, result)

        # Count errors and warnings
        result.errors = sum(1 for issue in result.issues if issue.severity == "ERROR")
        result.warnings = sum(1 for issue in result.issues if issue.severity == "WARNING")

        return result

    def check_acl_files(self, module_path: Path, module_name: str, result: AuditResult):
        """Check ACL files for compliance."""
        acl_file = module_path / "security" / "ir.model.access.csv"

        if not acl_file.exists():
            result.issues.append(
                Issue(
                    severity="WARNING",
                    check="ACL-MISSING",
                    module=module_name,
                    file="security/ir.model.access.csv",
                    message="ACL file not found",
                )
            )
            return

        # Parse defined models in Python files
        defined_models = self._get_defined_models(module_path, module_name)

        # Parse ACL entries
        acl_entries = []
        acl_models = set()

        try:
            with open(acl_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
                    acl_entries.append(row)
                    if "name" in row:
                        # Extract model from model_id:id field
                        model_id = row.get("model_id:id", "")
                        if model_id.startswith("model_"):
                            model_name = model_id[6:].replace("_", ".")
                            acl_models.add(model_name)

                    # Check naming convention (check 'id' column, not 'name')
                    acl_id = row.get("id", "")
                    if acl_id and not re.match(r"^access_[a-z0-9_]+_[a-z0-9_]+$", acl_id):
                        result.issues.append(
                            Issue(
                                severity="WARNING",
                                check="ACL-NAMING",
                                module=module_name,
                                file="security/ir.model.access.csv",
                                line=row_num,
                                message=f'ACL entry "{acl_id}" does not follow access_{{model}}_{{group}} pattern',
                            )
                        )

                    # Check permission consistency
                    perm_read = row.get("perm_read", "0") == "1"
                    perm_write = row.get("perm_write", "0") == "1"
                    perm_create = row.get("perm_create", "0") == "1"
                    perm_unlink = row.get("perm_unlink", "0") == "1"

                    if (perm_write or perm_create or perm_unlink) and not perm_read:
                        result.issues.append(
                            Issue(
                                severity="WARNING",
                                check="ACL-PERMISSIONS",
                                module=module_name,
                                file="security/ir.model.access.csv",
                                line=row_num,
                                message=f'ACL entry "{acl_id}" has write/create/unlink without read permission',
                            )
                        )
        except Exception as e:
            result.issues.append(
                Issue(
                    severity="ERROR",
                    check="ACL-PARSE",
                    module=module_name,
                    file="security/ir.model.access.csv",
                    message=f"Failed to parse ACL file: {str(e)}",
                )
            )
            return

        # Check if all defined models have ACL entries
        for model in defined_models:
            if model not in acl_models:
                result.issues.append(
                    Issue(
                        severity="WARNING",
                        check="ACL-MISSING-MODEL",
                        module=module_name,
                        file="security/ir.model.access.csv",
                        message=f'Model "{model}" defined but has no ACL entries',
                    )
                )

    def _get_defined_models(self, module_path: Path, module_name: str) -> set[str]:
        """Extract model definitions from Python files."""
        models = set()
        models_dir = module_path / "models"

        if not models_dir.exists():
            return models

        for py_file in models_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                # Look for _name = "trn.*" or _name = 'trn.*'
                matches = re.findall(r'_name\s*=\s*["\']([a-z0-9_.]+)["\']', content)
                for match in matches:
                    if match.startswith("trn."):
                        models.add(match)
            except Exception:
                pass

        return models

    def check_record_rules(self, module_path: Path, module_name: str, result: AuditResult):
        """Check record rules in XML files."""
        security_dir = module_path / "security"

        if not security_dir.exists():
            return

        for xml_file in security_dir.glob("*.xml"):
            try:
                # nosemgrep: odoo-xxe-stdlib - Script file parsing internal XML, not user-facing
                tree = ET.parse(xml_file)  # nosec B314
                root = tree.getroot()

                # Find all ir.rule records
                for record in root.findall('.//record[@model="ir.rule"]'):
                    rule_id = record.get("id", "unknown")

                    # Check if wrapped in noupdate
                    parent_data = record.find("..")
                    if parent_data is not None and parent_data.tag == "data":
                        noupdate = parent_data.get("noupdate", "0")
                        if noupdate != "1":
                            result.issues.append(
                                Issue(
                                    severity="WARNING",
                                    check="RULE-NOUPDATE",
                                    module=module_name,
                                    file=f"security/{xml_file.name}",
                                    message=f'Rule "{rule_id}" not wrapped in <data noupdate="1">',
                                )
                            )

                    # Check domain_force
                    domain_force = record.find('.//field[@name="domain_force"]')
                    perm_write = record.find('.//field[@name="perm_write"]')
                    perm_create = record.find('.//field[@name="perm_create"]')
                    perm_unlink = record.find('.//field[@name="perm_unlink"]')

                    has_write_perms = any(
                        field is not None and field.text and field.text.strip() in ("1", "True", "true")
                        for field in [perm_write, perm_create, perm_unlink]
                    )

                    if domain_force is not None and has_write_perms:
                        domain_text = domain_force.text or ""
                        if domain_text.strip() in ("[]", "", '[(1, "=", 1)]'):
                            result.issues.append(
                                Issue(
                                    severity="ERROR",
                                    check="RULE-EMPTY-DOMAIN",
                                    module=module_name,
                                    file=f"security/{xml_file.name}",
                                    message=f'Rule "{rule_id}" has write permissions but empty/trivial domain_force',
                                )
                            )

                    # Check groups or global
                    groups_field = record.find('.//field[@name="groups"]')
                    global_field = record.find('.//field[@name="global"]')

                    has_groups = groups_field is not None and groups_field.text and groups_field.text.strip()
                    is_global = (
                        global_field is not None
                        and global_field.text
                        and global_field.text.strip() in ("1", "True", "true")
                    )

                    if not has_groups and not is_global:
                        result.issues.append(
                            Issue(
                                severity="WARNING",
                                check="RULE-NO-GROUPS",
                                module=module_name,
                                file=f"security/{xml_file.name}",
                                message=f'Rule "{rule_id}" has no groups field and global is not True',
                            )
                        )
            except Exception as e:
                result.issues.append(
                    Issue(
                        severity="ERROR",
                        check="RULE-PARSE",
                        module=module_name,
                        file=f"security/{xml_file.name}",
                        message=f"Failed to parse XML: {str(e)}",
                    )
                )

    def check_security_groups(self, module_path: Path, module_name: str, result: AuditResult):
        """Check security groups definitions in XML files."""
        for xml_file in module_path.rglob("*.xml"):
            try:
                # nosemgrep: odoo-xxe-stdlib - Script file parsing internal XML, not user-facing
                tree = ET.parse(xml_file)  # nosec B314
                root = tree.getroot()

                # Check res.groups records
                for record in root.findall('.//record[@model="res.groups"]'):
                    group_id = record.get("id", "unknown")
                    rel_path = xml_file.relative_to(module_path)

                    # ERROR: category_id (Odoo 19 uses privilege_id)
                    if record.find('.//field[@name="category_id"]') is not None:
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="GROUP-CATEGORY-ID",
                                module=module_name,
                                file=str(rel_path),
                                message=f'Group "{group_id}" uses deprecated category_id (use privilege_id in Odoo 19)',
                            )
                        )

                    # ERROR: users field (should be user_ids)
                    if record.find('.//field[@name="users"]') is not None:
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="GROUP-USERS-FIELD",
                                module=module_name,
                                file=str(rel_path),
                                message=f'Group "{group_id}" uses deprecated users field (use user_ids)',
                            )
                        )

                    # WARN: user-facing group without privilege_id
                    # Skip technical groups (tier-3) and external references
                    privilege_id = record.find('.//field[@name="privilege_id"]')
                    is_technical = any(pattern in group_id for pattern in self.technical_group_patterns)
                    is_external = any(group_id.startswith(prefix) for prefix in self.external_group_prefixes)

                    if privilege_id is None and not is_technical and not is_external:
                        result.issues.append(
                            Issue(
                                severity="WARNING",
                                check="GROUP-NO-PRIVILEGE",
                                module=module_name,
                                file=str(rel_path),
                                message=f'Group "{group_id}" lacks privilege_id (required for user-facing groups)',
                            )
                        )

                # Check menuitem for groups_id
                for menuitem in root.findall(".//menuitem"):
                    menu_id = menuitem.get("id", "unknown")
                    rel_path = xml_file.relative_to(module_path)

                    # ERROR: groups_id (should be group_ids)
                    if menuitem.get("groups_id") is not None:
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="MENU-GROUPS-ID",
                                module=module_name,
                                file=str(rel_path),
                                message=f'Menu "{menu_id}" uses groups_id (should be group_ids)',
                            )
                        )

                # Check for tuple syntax (4, ref())
                xml_content = xml_file.read_text(encoding="utf-8")
                if re.search(r"\(4,\s*ref\(", xml_content):
                    rel_path = xml_file.relative_to(module_path)
                    result.issues.append(
                        Issue(
                            severity="ERROR",
                            check="GROUP-TUPLE-SYNTAX",
                            module=module_name,
                            file=str(rel_path),
                            message="Uses tuple syntax (4, ref()) - should use Command.link()",
                        )
                    )
            except Exception as e:
                rel_path = xml_file.relative_to(module_path)
                result.issues.append(
                    Issue(
                        severity="ERROR",
                        check="GROUP-PARSE",
                        module=module_name,
                        file=str(rel_path),
                        message=f"Failed to parse XML: {str(e)}",
                    )
                )

    def check_legacy_patterns(self, module_path: Path, module_name: str, result: AuditResult):
        """Check for legacy patterns."""
        pass

    def check_python_security(self, module_path: Path, module_name: str, result: AuditResult):
        """Check Python code for security issues."""
        for py_file in module_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue

            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
                rel_path = py_file.relative_to(module_path)

                for line_num, line in enumerate(lines, start=1):
                    # WARN: sudo() usage
                    if re.search(r"\.sudo\(\)", line):
                        result.issues.append(
                            Issue(
                                severity="WARNING",
                                check="PYTHON-SUDO",
                                module=module_name,
                                file=str(rel_path),
                                line=line_num,
                                message="sudo() usage detected (potential security bypass)",
                            )
                        )

                    # ERROR: SQL injection risk
                    if re.search(r"cr\.execute\([^)]*%[^)]*\)", line) and "params=" not in line:
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="PYTHON-SQL-INJECTION",
                                module=module_name,
                                file=str(rel_path),
                                line=line_num,
                                message="cr.execute() with % formatting (SQL injection risk)",
                            )
                        )

                    # ERROR: bare except
                    if re.search(r"except\s*:", line):
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="PYTHON-BARE-EXCEPT",
                                module=module_name,
                                file=str(rel_path),
                                line=line_num,
                                message="Bare except: clause (should catch specific exceptions)",
                            )
                        )

                    # ERROR: print() statements
                    if re.search(r"\bprint\s*\(", line) and not line.strip().startswith("#"):
                        result.issues.append(
                            Issue(
                                severity="ERROR",
                                check="PYTHON-PRINT",
                                module=module_name,
                                file=str(rel_path),
                                line=line_num,
                                message="print() statement found (use _logger instead)",
                            )
                        )

                    # WARN: PII in logs
                    if re.search(r"_logger\.(info|debug|warning|error)", line):
                        pii_patterns = ["name", "phone", "email", "national_id"]
                        for pattern in pii_patterns:
                            if re.search(rf"\b{pattern}\b", line, re.IGNORECASE):
                                result.issues.append(
                                    Issue(
                                        severity="WARNING",
                                        check="PYTHON-PII-LOG",
                                        module=module_name,
                                        file=str(rel_path),
                                        line=line_num,
                                        message=f"Potential PII in log message (detected: {pattern})",
                                    )
                                )
                                break
            except Exception:
                pass


def find_custom_modules(root_dir: Path) -> list[str]:
    """Find all custom modules in the root directory."""
    modules = []
    for item in root_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            manifest = item / "__manifest__.py"
            if manifest.exists():
                modules.append(item.name)
    return sorted(modules)


def print_results(results: list[AuditResult], json_output: bool = False):
    """Print audit results."""
    if json_output:
        output = {
            "modules": {r.module: {"errors": r.errors, "warnings": r.warnings} for r in results},
            "issues": [asdict(issue) for r in results for issue in r.issues],
        }
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("Odoo Static Security Audit")
        print("=" * 60)
        print(f"Modules to audit: {len(results)}\n")

        for result in results:
            print(f"[{result.module}] Auditing...")
            for issue in result.issues:
                severity_tag = f"[{issue.severity}]"
                check_tag = f"{issue.check}:"
                location = f"File: {issue.file}"
                if issue.line:
                    location += f":{issue.line}"

                print(f"  {severity_tag} {check_tag} {issue.message}")
                print(f"         {location}")

            if result.issues:
                print(f"[{result.module}] Errors: {result.errors}, Warnings: {result.warnings}\n")
            else:
                print(f"[{result.module}] No issues found\n")

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        total_errors = sum(r.errors for r in results)
        total_warnings = sum(r.warnings for r in results)
        print(f"Total errors: {total_errors}")
        print(f"Total warnings: {total_warnings}")


def main():
    parser = argparse.ArgumentParser(
        description="Static security analysis for custom Odoo modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Audit all modules
  %(prog)s trn_api             # Audit single module
  %(prog)s --json                   # JSON output
  %(prog)s --check=acl              # Only ACL checks
  %(prog)s --check=acl,rules        # Multiple specific checks
        """,
    )

    parser.add_argument("modules", nargs="*", help="Specific modules to audit (default: all custom modules)")

    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    parser.add_argument("--check", help="Comma-separated list of checks to run (acl, rules, groups, legacy, python)")

    args = parser.parse_args()

    # Determine root directory
    root_dir = Path.cwd()
    if not (root_dir / "scripts").exists():
        # Maybe we're in the scripts directory
        if root_dir.name == "scripts":
            root_dir = root_dir.parent

    # Determine which modules to audit
    if args.modules:
        modules_to_audit = args.modules
    else:
        modules_to_audit = find_custom_modules(root_dir)

    # Determine which checks to run
    checks = None
    if args.check:
        checks = set(args.check.split(","))

    # Run audit
    auditor = StaticSecurityAuditor(root_dir)
    results = []

    for module in modules_to_audit:
        result = auditor.audit_module(module, checks)
        results.append(result)

    # Print results
    print_results(results, args.json)

    # Exit with error code if any errors found
    total_errors = sum(r.errors for r in results)
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
