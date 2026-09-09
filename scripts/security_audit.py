#!/usr/bin/env python3
"""
Security Audit Script for Odoo Access Rights Migration

This script audits custom Odoo modules for compliance with the new access rights
architecture defined in ADR-004.

Usage:
    python scripts/security_audit.py [module_path]
    python scripts/security_audit.py --all
    python scripts/security_audit.py --report

Examples:
    python scripts/security_audit.py trn_vocabulary
    python scripts/security_audit.py --all
    python scripts/security_audit.py --report > audit_report.md
"""

import argparse
import ast
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

# Naming convention patterns from ADR-004
# More flexible to allow special roles and backward compatibility
NAMING_PATTERNS = {
    "category": re.compile(r"^category_trn_[a-z_]+$"),
    "privilege": re.compile(r"^privilege_[a-z_]+_[a-z_]+$"),
    # User groups: group_{domain}_{level} where level can be viewer/officer/manager/admin
    # or special roles like approver, finance_validator, etc.
    "group_user": re.compile(
        r"^group_[a-z_]+_(viewer|officer|manager|admin|approver|validator|finance_validator|restrict_self)$"
    ),
    # Technical groups: group_{domain}_{action}
    "group_technical": re.compile(r"^group_[a-z_]+_(read|write|create|delete)$"),
    # Backward compat groups (deprecated) - any group with old naming
    "group_compat": re.compile(r"^(trn_|group_trn_)"),
    "role": re.compile(r"^role_trn_[a-z_]+$"),
    "access_csv": re.compile(r"^access_[a-z0-9_]+$"),
    "rule": re.compile(r"^rule_[a-z_]+$"),
}

# CUSTOMIZE: Update this list with your project's domain names.
# These are used to validate security group naming conventions.
# Add entries matching the {domain} part of your module names (trn_{domain}).
VALID_DOMAINS = [
    "vocabulary",
    "contact",
    "order",
    "area",
    "api",
    "admin",
]


@dataclass
class Issue:
    """Represents a single audit issue."""

    severity: str  # ERROR, WARNING, INFO
    category: str
    message: str
    file_path: str
    line_number: int | None = None
    suggestion: str | None = None


@dataclass
class ModuleAudit:
    """Audit results for a single module."""

    module_name: str
    module_path: Path
    issues: list = field(default_factory=list)
    groups_found: list = field(default_factory=list)
    rules_found: list = field(default_factory=list)
    access_entries: list = field(default_factory=list)
    privileges_found: list = field(default_factory=list)
    has_security_dir: bool = False
    has_privileges_xml: bool = False
    has_groups_xml: bool = False
    has_access_csv: bool = False
    has_security_module_dep: bool = False
    has_admin_link: bool = False
    odoo19_compliant: bool = True
    naming_compliant: bool = True


def find_modules(base_path: Path) -> list[Path]:
    """Find all custom Odoo modules in the given path."""
    modules = []
    for item in base_path.iterdir():
        if item.is_dir() and (item / "__manifest__.py").exists():
            modules.append(item)
    return sorted(modules)


def parse_manifest(module_path: Path) -> dict:
    """Parse __manifest__.py and return as dict."""
    manifest_file = module_path / "__manifest__.py"
    if not manifest_file.exists():
        return {}
    try:
        content = manifest_file.read_text(encoding="utf-8")
        # Remove the leading comment if present
        content = re.sub(r"^#.*\n", "", content)
        return ast.literal_eval(content)
    except Exception:
        return {}


def parse_xml_safe(file_path: Path) -> ET.Element | None:
    """Safely parse an XML file, handling errors gracefully."""
    try:
        content = file_path.read_text(encoding="utf-8")
        if not content.strip().startswith("<?xml"):
            content = '<?xml version="1.0" encoding="utf-8"?>\n' + content
        return ET.fromstring(content)  # nosec B314
    except ET.ParseError:
        return None
    except Exception:
        return None


def is_deprecated_group(xml_id: str, record: ET.Element) -> bool:
    """Check if a group is marked as deprecated (backward compatibility)."""
    # Check ID patterns
    if xml_id.startswith("trn_"):
        return True
    # Check if name contains "Deprecated"
    for field_elem in record.findall("field"):
        if field_elem.get("name") == "name":
            name_text = field_elem.text or ""
            if "deprecated" in name_text.lower():
                return True
        if field_elem.get("name") == "comment":
            comment_text = field_elem.text or ""
            if "deprecated" in comment_text.lower():
                return True
    return False


def is_extending_external_group(xml_id: str) -> bool:
    """Check if record is extending an external group (i.e., the XML ID contains a dot)."""
    return "." in xml_id


def check_group_naming(xml_id: str, is_deprecated: bool = False) -> tuple[bool, str]:
    """Check if a group ID follows naming conventions."""
    # Skip check for deprecated/compat groups
    if is_deprecated:
        return True, ""

    # Skip external group extensions
    if is_extending_external_group(xml_id):
        return True, ""

    # Check user-facing pattern
    if NAMING_PATTERNS["group_user"].match(xml_id):
        return True, ""

    # Check technical pattern
    if NAMING_PATTERNS["group_technical"].match(xml_id):
        return True, ""

    # Allow any group_{domain}_* pattern for flexibility with special roles
    if re.match(r"^group_[a-z]+_[a-z_]+$", xml_id):
        return True, ""

    return False, f"Group '{xml_id}' doesn't follow naming convention group_{{domain}}_{{role}}"


def audit_security_xml(file_path: Path, audit: ModuleAudit) -> None:
    """Audit a security XML file for compliance."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(file_path.relative_to(audit.module_path))
    lines = content.split("\n")

    # Track context for smarter detection
    current_model = None

    # Line-by-line checks with context awareness
    for i, line in enumerate(lines, 1):
        # Track current record model
        model_match = re.search(r'<record[^>]+model=["\']([^"\']+)["\']', line)
        if model_match:
            current_model = model_match.group(1)
        if "</record>" in line:
            current_model = None

        # Check category_id - ERROR only for res.groups, valid for res.groups.privilege
        if re.search(r'<field\s+name=["\']category_id["\']', line):
            if current_model == "res.groups":
                audit.issues.append(
                    Issue(
                        severity="ERROR",
                        category="ODOO19",
                        message="category_id field removed from res.groups in Odoo 19",
                        file_path=rel_path,
                        line_number=i,
                        suggestion="Remove category_id, use privilege_id instead",
                    )
                )
                audit.odoo19_compliant = False
            # Note: category_id is VALID for res.groups.privilege - no error

        # Check old 'users' field
        if re.search(r'<field\s+name=["\']users["\']', line):
            audit.issues.append(
                Issue(
                    severity="ERROR",
                    category="ODOO19",
                    message="'users' field renamed to 'user_ids' in Odoo 19",
                    file_path=rel_path,
                    line_number=i,
                    suggestion="Change 'users' to 'user_ids'",
                )
            )
            audit.odoo19_compliant = False

        # Check old tuple syntax (4, ref())
        if re.search(r"\[\s*\(\s*4\s*,", line):
            audit.issues.append(
                Issue(
                    severity="ERROR",
                    category="ODOO19",
                    message="Old tuple syntax (4, ref()) is deprecated",
                    file_path=rel_path,
                    line_number=i,
                    suggestion="Use Command.link(ref()) instead",
                )
            )
            audit.odoo19_compliant = False

    # Parse XML for structural analysis
    root = parse_xml_safe(file_path)
    if root is None:
        audit.issues.append(
            Issue(severity="WARNING", category="PARSE", message="Could not parse XML file", file_path=rel_path)
        )
        return

    # Analyze each record
    for record in root.iter("record"):
        model = record.get("model", "")
        xml_id = record.get("id", "")

        if model == "res.groups":
            # Skip if extending external group
            if is_extending_external_group(xml_id):
                # Check if this is the admin link
                if "group_" in xml_id and "admin" in xml_id:
                    audit.has_admin_link = True
                continue

            audit.groups_found.append(xml_id)
            is_deprecated = is_deprecated_group(xml_id, record)

            # Check naming convention (skip deprecated)
            valid, msg = check_group_naming(xml_id, is_deprecated)
            if not valid:
                audit.issues.append(
                    Issue(
                        severity="WARNING",
                        category="NAMING",
                        message=msg,
                        file_path=rel_path,
                        suggestion="Use pattern: group_{domain}_{level} (e.g., group_entity_officer)",
                    )
                )
                audit.naming_compliant = False

            # Check for comment field (skip deprecated - they should have it explaining deprecation)
            has_comment = any(f.get("name") == "comment" for f in record.findall("field"))
            if not has_comment and not is_deprecated:
                audit.issues.append(
                    Issue(
                        severity="INFO",
                        category="DOCS",
                        message=f"Group '{xml_id}' missing comment field",
                        file_path=rel_path,
                        suggestion='Add <field name="comment">Description</field>',
                    )
                )

            # Check for privilege_id on user-facing groups (skip technical/deprecated)
            has_privilege = any(f.get("name") == "privilege_id" for f in record.findall("field"))
            is_technical = any(x in xml_id for x in ["_read", "_write", "_create", "_delete"])
            if not has_privilege and not is_technical and not is_deprecated:
                audit.issues.append(
                    Issue(
                        severity="INFO",
                        category="ODOO19",
                        message=f"User-facing group '{xml_id}' should have privilege_id",
                        file_path=rel_path,
                        suggestion="Add privilege_id reference for Odoo 19 user settings UI",
                    )
                )

        elif model == "res.groups.privilege":
            audit.privileges_found.append(xml_id)
            # Mark that we found privileges
            if "privileges" in rel_path:
                audit.has_privileges_xml = True

        elif model == "ir.rule":
            audit.rules_found.append(xml_id)

        elif model == "ir.module.category":
            # Categories should only be in trn_security
            if audit.module_name != "trn_security":
                audit.issues.append(
                    Issue(
                        severity="ERROR",
                        category="ARCHITECTURE",
                        message="Module category defined outside trn_security",
                        file_path=rel_path,
                        suggestion="Categories must be defined in trn_security module only",
                    )
                )


def audit_access_csv(file_path: Path, audit: ModuleAudit) -> None:
    """Audit ir.model.access.csv file."""
    rel_path = str(file_path.relative_to(audit.module_path))
    audit.has_access_csv = True

    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for _i, row in enumerate(reader, 2):
                entry_id = row.get("id", "")
                if not entry_id:
                    continue
                audit.access_entries.append(entry_id)

    except Exception as e:
        audit.issues.append(
            Issue(severity="ERROR", category="PARSE", message=f"Could not parse CSV: {e}", file_path=rel_path)
        )


def audit_views(module_path: Path, audit: ModuleAudit) -> None:
    """Audit view files for deprecated patterns."""
    views_dir = module_path / "views"
    if not views_dir.exists():
        return

    for xml_file in views_dir.glob("*.xml"):
        content = xml_file.read_text(encoding="utf-8", errors="replace")
        rel_path = str(xml_file.relative_to(module_path))

        # Check for old groups_id on records (not the groups= attribute on menus)
        for i, line in enumerate(content.split("\n"), 1):
            # groups_id as a field is deprecated, but groups= attribute is fine
            if re.search(r'<field\s+name=["\']groups_id["\']', line):
                audit.issues.append(
                    Issue(
                        severity="ERROR",
                        category="ODOO19",
                        message="'groups_id' field renamed to 'group_ids' in Odoo 19",
                        file_path=rel_path,
                        line_number=i,
                        suggestion="Use group_ids with Command.set()",
                    )
                )
                audit.odoo19_compliant = False


def audit_module(module_path: Path) -> ModuleAudit:
    """Perform a complete audit of a module."""
    audit = ModuleAudit(module_name=module_path.name, module_path=module_path)

    # Check manifest for trn_security dependency
    manifest = parse_manifest(module_path)
    depends = manifest.get("depends", [])
    audit.has_security_module_dep = "trn_security" in depends

    # trn_security itself doesn't need the dependency check
    if audit.module_name == "trn_security":
        audit.has_security_module_dep = True

    if not audit.has_security_module_dep and audit.module_name not in ["base", "trn_security"]:
        audit.issues.append(
            Issue(
                severity="WARNING",
                category="ARCHITECTURE",
                message="Module should depend on trn_security",
                file_path="__manifest__.py",
                suggestion="Add 'trn_security' to depends list",
            )
        )

    # Check for security directory
    security_dir = module_path / "security"
    if security_dir.exists():
        audit.has_security_dir = True

        # Check for expected files
        if (security_dir / "privileges.xml").exists():
            audit.has_privileges_xml = True
        if (security_dir / "groups.xml").exists():
            audit.has_groups_xml = True

        # Audit all XML files in security directory
        for xml_file in security_dir.glob("*.xml"):
            audit_security_xml(xml_file, audit)

        # Audit access CSV
        access_csv = security_dir / "ir.model.access.csv"
        if access_csv.exists():
            audit_access_csv(access_csv, audit)

    # Audit views
    audit_views(module_path, audit)

    # Check for admin link if module has groups
    if audit.groups_found and not audit.has_admin_link and audit.module_name != "trn_security":
        # Only warn if there are manager-level groups
        has_manager = any("manager" in g for g in audit.groups_found)
        if has_manager:
            audit.issues.append(
                Issue(
                    severity="INFO",
                    category="ARCHITECTURE",
                    message="Module should link manager group to trn_security.group_trn_admin",
                    file_path="security/groups.xml",
                    suggestion=(
                        'Add: <record id="trn_security.group_trn_admin">'
                        '<field name="implied_ids" eval="[Command.link(ref(\'group_*_manager\'))]"/>'
                        "</record>"
                    ),
                )
            )

    # Summarize compliance
    error_count = sum(1 for i in audit.issues if i.severity == "ERROR")
    if error_count > 0:
        audit.odoo19_compliant = False

    return audit


def generate_report(audits: list[ModuleAudit], output_format: str = "markdown") -> str:
    """Generate a full audit report."""
    if output_format == "markdown":
        return generate_markdown_report(audits)
    elif output_format == "json":
        return generate_json_report(audits)
    else:
        return generate_text_report(audits)


def generate_markdown_report(audits: list[ModuleAudit]) -> str:
    """Generate a markdown audit report."""
    lines = [
        "# Security Audit Report",
        "",
        f"**Generated:** {__import__('datetime').datetime.now().isoformat()}",
        f"**Modules Audited:** {len(audits)}",
        "",
        "## Summary",
        "",
        "| Module | Privileges | Groups | Rules | Odoo 19 | Errors | Warnings |",
        "|--------|------------|--------|-------|---------|--------|----------|",
    ]

    total_errors = 0
    total_warnings = 0
    compliant_count = 0

    for audit in audits:
        errors = sum(1 for i in audit.issues if i.severity == "ERROR")
        warnings = sum(1 for i in audit.issues if i.severity == "WARNING")
        total_errors += errors
        total_warnings += warnings
        if errors == 0:
            compliant_count += 1

        odoo19 = "✅" if audit.odoo19_compliant else "❌"

        lines.append(
            f"| {audit.module_name} | {len(audit.privileges_found)} | "
            f"{len(audit.groups_found)} | {len(audit.rules_found)} | "
            f"{odoo19} | {errors} | {warnings} |"
        )

    lines.extend(
        [
            "",
            f"**Compliant Modules:** {compliant_count}/{len(audits)}",
            f"**Total Errors:** {total_errors}",
            f"**Total Warnings:** {total_warnings}",
            "",
        ]
    )

    # Only show detailed issues if there are any
    modules_with_issues = [a for a in audits if a.issues]
    if modules_with_issues:
        lines.extend(
            [
                "## Detailed Issues",
                "",
            ]
        )

        for audit in modules_with_issues:
            lines.extend(
                [
                    f"### {audit.module_name}",
                    "",
                ]
            )

            # Group by severity
            for severity in ["ERROR", "WARNING", "INFO"]:
                issues = [i for i in audit.issues if i.severity == severity]
                if not issues:
                    continue

                severity_label = {"ERROR": "Errors", "WARNING": "Warnings", "INFO": "Info"}[severity]
                lines.append(f"**{severity_label}:**")
                lines.append("")

                for issue in issues:
                    loc = f"`{issue.file_path}`"
                    if issue.line_number:
                        loc += f" (line {issue.line_number})"
                    lines.append(f"- **[{issue.category}]** {issue.message}")
                    lines.append(f"  - {loc}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 {issue.suggestion}")

                lines.append("")

    # Add quick reference
    lines.extend(
        [
            "---",
            "",
            "## Quick Reference",
            "",
            "### Error Types",
            "- **ODOO19**: Breaking changes for Odoo 19 compatibility",
            "- **ARCHITECTURE**: Violations of ADR-004 architecture",
            "- **PARSE**: File parsing errors",
            "",
            "### Warning Types",
            "- **NAMING**: Naming convention suggestions",
            "- **NAMESPACE**: Legacy namespace references",
            "",
            "### Naming Conventions",
            "- Privileges: `privilege_{domain}_{level}` (e.g., `privilege_entity_officer`)",
            "- Groups: `group_{domain}_{level}` (e.g., `group_entity_officer`)",
            "- Technical: `group_{domain}_{action}` (e.g., `group_entity_read`)",
            "- Rules: `rule_{model}_{purpose}` (e.g., `rule_contact_company`)",
            "",
        ]
    )

    return "\n".join(lines)


def generate_json_report(audits: list[ModuleAudit]) -> str:
    """Generate a JSON audit report."""
    data = {
        "generated": __import__("datetime").datetime.now().isoformat(),
        "modules_audited": len(audits),
        "total_errors": sum(1 for a in audits for i in a.issues if i.severity == "ERROR"),
        "total_warnings": sum(1 for a in audits for i in a.issues if i.severity == "WARNING"),
        "modules": [],
    }

    for audit in audits:
        module_data = {
            "name": audit.module_name,
            "privileges": audit.privileges_found,
            "groups": audit.groups_found,
            "rules": audit.rules_found,
            "access_entries": len(audit.access_entries),
            "has_security_module_dep": audit.has_security_module_dep,
            "has_admin_link": audit.has_admin_link,
            "odoo19_compliant": audit.odoo19_compliant,
            "naming_compliant": audit.naming_compliant,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "file": i.file_path,
                    "line": i.line_number,
                    "suggestion": i.suggestion,
                }
                for i in audit.issues
            ],
        }
        data["modules"].append(module_data)

    return json.dumps(data, indent=2)


def generate_text_report(audits: list[ModuleAudit]) -> str:
    """Generate a plain text audit report."""
    lines = []

    for audit in audits:
        errors = sum(1 for i in audit.issues if i.severity == "ERROR")
        warnings = sum(1 for i in audit.issues if i.severity == "WARNING")
        status = "✅" if errors == 0 else "❌"

        lines.append(f"{status} {audit.module_name}")
        lines.append(
            f"   Privileges: {len(audit.privileges_found)},"
            f" Groups: {len(audit.groups_found)},"
            f" Rules: {len(audit.rules_found)}"
        )
        lines.append(f"   Errors: {errors}, Warnings: {warnings}")

        if audit.issues:
            for issue in audit.issues:
                icon = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}[issue.severity]
                lines.append(f"   {icon} [{issue.category}] {issue.message}")

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit custom Odoo modules for access rights compliance (ADR-004)")
    parser.add_argument("module", nargs="?", help="Module name to audit (e.g., trn_vocabulary)")
    parser.add_argument("--all", "-a", action="store_true", help="Audit all custom Odoo modules")
    parser.add_argument("--report", "-r", action="store_true", help="Generate full detailed report")
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json", "text"],
        default="markdown",
        help="Report format (default: markdown)",
    )
    parser.add_argument("--errors-only", "-e", action="store_true", help="Only show modules with errors")
    parser.add_argument("--base-path", type=Path, default=Path("."), help="Base path to search for modules")

    args = parser.parse_args()
    base_path = args.base_path.resolve()

    if args.all or args.report:
        modules = find_modules(base_path)
        if not modules:
            print(f"No custom Odoo modules found in {base_path}", file=sys.stderr)
            sys.exit(1)

        audits = [audit_module(m) for m in modules]

        if args.errors_only:
            audits = [a for a in audits if any(i.severity == "ERROR" for i in a.issues)]

        if args.report:
            print(generate_report(audits, args.format))
        else:
            # Print compact summary
            for audit in audits:
                errors = sum(1 for i in audit.issues if i.severity == "ERROR")
                warnings = sum(1 for i in audit.issues if i.severity == "WARNING")
                status = "✅" if errors == 0 else "❌"
                print(f"{status} {audit.module_name}: {errors} errors, {warnings} warnings")

            # Print totals
            total_errors = sum(1 for a in audits for i in a.issues if i.severity == "ERROR")
            total_warnings = sum(1 for a in audits for i in a.issues if i.severity == "WARNING")
            compliant = sum(1 for a in audits if all(i.severity != "ERROR" for i in a.issues))
            print(f"\nTotal: {compliant}/{len(audits)} compliant, {total_errors} errors, {total_warnings} warnings")

    elif args.module:
        module_path = base_path / args.module
        if not module_path.exists():
            print(f"Module not found: {module_path}", file=sys.stderr)
            sys.exit(1)

        audit = audit_module(module_path)
        print(generate_report([audit], args.format))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
