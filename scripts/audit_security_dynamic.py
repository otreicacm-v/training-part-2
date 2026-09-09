#!/usr/bin/env python3
"""
Dynamic security analysis for Odoo projects in a running Odoo instance.
Requires database connection to analyze effective permissions.

Usage:
    # Using Odoo shell
    odoo shell -d your_database < scripts/audit_security_dynamic.py

    # Or with odoo-bin
    ./odoo-bin shell -d your_database -c odoo.conf < scripts/audit_security_dynamic.py

    # Interactive mode
    odoo shell -d your_database
    >>> exec(open('scripts/audit_security_dynamic.py').read())
"""

import sys
from collections import defaultdict


class DynamicSecurityAuditor:
    """Analyzes security configuration in a running Odoo instance."""

    def __init__(self, env):
        self.env = env
        self.issues = []
        self.stats = defaultdict(int)

    def add_issue(self, severity, code, context, message, remediation=None):
        """Add an issue to the report."""
        self.issues.append(
            {
                "severity": severity,
                "code": code,
                "context": context,
                "message": message,
                "remediation": remediation or "",
            }
        )
        self.stats[severity] += 1

    def check_model_acl_coverage(self):
        """Find trn.* models without ACL rules."""
        print("\n[MODEL ACL COVERAGE]")
        print("=" * 60)

        IrModel = self.env["ir.model"]
        IrModelAccess = self.env["ir.model.access"]

        # Get all trn.* models
        try:
            custom_models = IrModel.search([("model", "=like", "trn.%")])
            self.stats["models_total"] = len(custom_models)
        except Exception as e:
            print(f"  [ERROR] Could not query models: {e}")
            return

        models_without_acl = []

        for model in custom_models:
            acl_count = IrModelAccess.search_count([("model_id", "=", model.id)])
            if acl_count == 0:
                models_without_acl.append(model.model)
                self.add_issue(
                    "ERROR",
                    "MODEL-NO-ACL",
                    model.model,
                    "Model has no ACL rules defined - inaccessible to all users",
                    f"Add ir.model.access.csv entries for {model.model} in the module that defines it",
                )
                print(f"  [ERROR] {model.model}: No ACL rules defined")

        self.stats["models_without_acl"] = len(models_without_acl)

        print("\n  Summary:")
        print(f"    Models checked: {self.stats['models_total']}")
        print(f"    Models without ACL: {self.stats['models_without_acl']}")

        if self.stats["models_without_acl"] == 0:
            print("    [OK] All trn.* models have ACL rules")

    def check_group_usage(self):
        """Find unused security groups."""
        print("\n[GROUP USAGE ANALYSIS]")
        print("=" * 60)

        ResGroups = self.env["res.groups"]
        IrModelAccess = self.env["ir.model.access"]
        IrRule = self.env["ir.rule"]
        IrModuleModule = self.env["ir.module.module"]

        # Get all installed trn_* modules
        try:
            custom_modules = IrModuleModule.search([("name", "=like", "trn_%"), ("state", "=", "installed")])
            module_names = custom_modules.mapped("name")
        except Exception as e:
            print(f"  [ERROR] Could not query modules: {e}")
            return

        # Get all groups from custom modules
        try:
            custom_groups = ResGroups.search([("category_id.name", "in", ["Social Protection"])])

            # Fallback: get groups by XML ID pattern
            IrModelData = self.env["ir.model.data"]
            group_xmlids = IrModelData.search([("model", "=", "res.groups"), ("module", "in", module_names)])
            group_ids = group_xmlids.mapped("res_id")
            custom_groups |= ResGroups.browse(group_ids)

            custom_groups = custom_groups.sorted(key=lambda g: g.name)
            self.stats["groups_total"] = len(custom_groups)
        except Exception as e:
            print(f"  [ERROR] Could not query groups: {e}")
            return

        unused_groups = []

        for group in custom_groups:
            # Check if group is used anywhere
            used = False

            # Check 1: Users assigned to group
            if group.users:
                used = True

            # Check 2: Used in ACLs
            if not used:
                acl_count = IrModelAccess.search_count([("group_id", "=", group.id)])
                if acl_count > 0:
                    used = True

            # Check 3: Used in record rules
            if not used:
                rule_count = IrRule.search_count([("groups", "in", [group.id])])
                if rule_count > 0:
                    used = True

            # Check 4: Implied by other groups
            if not used:
                implied_count = ResGroups.search_count([("implied_ids", "in", [group.id])])
                if implied_count > 0:
                    used = True

            # Check 5: Has implied groups (parent group)
            if not used and group.implied_ids:
                used = True

            if not used:
                unused_groups.append(group.complete_name)
                self.add_issue(
                    "WARN",
                    "GROUP-UNUSED",
                    group.complete_name,
                    "Group is not used in ACLs, rules, or assigned to users",
                    "Remove unused group or document its purpose",
                )
                print(f"  [WARN] {group.complete_name}: Not used anywhere")

        self.stats["groups_unused"] = len(unused_groups)

        print("\n  Summary:")
        print(f"    Groups checked: {self.stats['groups_total']}")
        print(f"    Unused groups: {self.stats['groups_unused']}")

        if self.stats["groups_unused"] == 0:
            print("    [OK] All groups are used")

    def check_group_hierarchy(self):
        """Check group hierarchy and detect circular references."""
        print("\n[GROUP HIERARCHY]")
        print("=" * 60)

        ResGroups = self.env["res.groups"]

        try:
            custom_groups = ResGroups.search([("category_id.name", "in", ["Social Protection"])])

            # Also get by module
            IrModuleModule = self.env["ir.module.module"]
            custom_modules = IrModuleModule.search([("name", "=like", "trn_%"), ("state", "=", "installed")])
            module_names = custom_modules.mapped("name")

            IrModelData = self.env["ir.model.data"]
            group_xmlids = IrModelData.search([("model", "=", "res.groups"), ("module", "in", module_names)])
            group_ids = group_xmlids.mapped("res_id")
            custom_groups |= ResGroups.browse(group_ids)

            custom_groups = custom_groups.sorted(key=lambda g: g.name)
        except Exception as e:
            print(f"  [ERROR] Could not query groups: {e}")
            return

        # Check for circular references
        circular_groups = []

        def check_circular(group, visited=None):
            """Recursively check for circular group references."""
            if visited is None:
                visited = set()

            if group.id in visited:
                return True  # Circular reference detected

            visited.add(group.id)

            for implied_group in group.implied_ids:
                if check_circular(implied_group, visited.copy()):
                    return True

            return False

        for group in custom_groups:
            if group.implied_ids and check_circular(group):
                circular_groups.append(group.complete_name)
                self.add_issue(
                    "ERROR",
                    "GROUP-CIRCULAR",
                    group.complete_name,
                    "Circular group reference detected in implied_ids chain",
                    "Review and fix group hierarchy to remove circular references",
                )
                print(f"  [ERROR] {group.complete_name}: Circular reference detected")

        # Print group hierarchy
        root_groups = custom_groups.filtered(lambda g: not g.implied_ids)

        def print_hierarchy(group, indent=0):
            """Recursively print group hierarchy."""
            print(f"  {'  ' * indent}{group.name}")
            # Find groups that imply this one
            children = custom_groups.filtered(lambda g: group in g.implied_ids)
            for child in children:
                print_hierarchy(child, indent + 1)

        if root_groups:
            print("\n  Group Hierarchy:")
            for root in root_groups[:5]:  # Limit output
                print_hierarchy(root)
            if len(root_groups) > 5:
                print(f"  ... and {len(root_groups) - 5} more root groups")

        print("\n  Summary:")
        print(f"    Root groups (no implied_ids): {len(root_groups)}")
        print(f"    Circular references: {len(circular_groups)}")

        if len(circular_groups) == 0:
            print("    [OK] No circular references detected")

    def check_effective_permissions(self):
        """Report effective permissions for each security group."""
        print("\n[EFFECTIVE PERMISSIONS]")
        print("=" * 60)

        ResGroups = self.env["res.groups"]
        IrModelAccess = self.env["ir.model.access"]

        try:
            # Get key custom module groups
            IrModuleModule = self.env["ir.module.module"]
            custom_modules = IrModuleModule.search([("name", "=like", "trn_%"), ("state", "=", "installed")])
            module_names = custom_modules.mapped("name")

            IrModelData = self.env["ir.model.data"]
            group_xmlids = IrModelData.search([("model", "=", "res.groups"), ("module", "in", module_names)])
            group_ids = group_xmlids.mapped("res_id")
            custom_groups = ResGroups.browse(group_ids).sorted(key=lambda g: g.name)
        except Exception as e:
            print(f"  [ERROR] Could not query groups: {e}")
            return

        overly_permissive = []

        for group in custom_groups[:10]:  # Limit to first 10 for readability
            acls = IrModelAccess.search([("group_id", "=", group.id)])

            if not acls:
                continue

            # Count permissions
            read_count = sum(1 for acl in acls if acl.perm_read)
            write_count = sum(1 for acl in acls if acl.perm_write)
            create_count = sum(1 for acl in acls if acl.perm_create)
            delete_count = sum(1 for acl in acls if acl.perm_unlink)

            # Check for trn.* models
            custom_acls = acls.filtered(lambda a: a.model_id.model.startswith("trn."))
            custom_write_count = sum(1 for acl in custom_acls if acl.perm_write)

            print(f"\n  {group.complete_name}:")
            print(f"    Read: {read_count} models | Write: {write_count} models")
            print(f"    Create: {create_count} models | Delete: {delete_count} models")

            # Flag overly permissive groups
            if custom_write_count > 30:
                overly_permissive.append(group.complete_name)
                self.add_issue(
                    "WARN",
                    "GROUP-OVERLY-PERMISSIVE",
                    group.complete_name,
                    f"Group has write access to {custom_write_count} trn.* models",
                    "Review if this group needs write access to so many models",
                )
                print(f"    [WARN] Write access to {custom_write_count} trn.* models (high)")

        if len(custom_groups) > 10:
            print(f"\n  ... and {len(custom_groups) - 10} more groups")

        self.stats["overly_permissive"] = len(overly_permissive)

    def check_record_rules(self):
        """Validate record rules."""
        print("\n[RECORD RULE VALIDATION]")
        print("=" * 60)

        IrRule = self.env["ir.rule"]

        try:
            # Get all record rules for trn.* models
            custom_rules = IrRule.search([("model_id.model", "=like", "trn.%")])
            self.stats["rules_total"] = len(custom_rules)
        except Exception as e:
            print(f"  [ERROR] Could not query record rules: {e}")
            return

        invalid_domains = []

        for rule in custom_rules:
            # Check if domain is valid
            try:
                if rule.domain_force:
                    # Try to evaluate the domain
                    from ast import literal_eval

                    domain = literal_eval(rule.domain_force)
                    if not isinstance(domain, list):
                        raise ValueError("Domain must be a list")
            except Exception as e:
                invalid_domains.append(rule.name)
                self.add_issue(
                    "ERROR",
                    "RULE-INVALID-DOMAIN",
                    f"{rule.model_id.model}: {rule.name}",
                    f"Invalid domain syntax: {e}",
                    "Fix the domain_force field to use valid Odoo domain syntax",
                )
                print(f"  [ERROR] {rule.model_id.model} / {rule.name}: Invalid domain")

        # Check for rules without groups (global rules)
        global_write_rules = custom_rules.filtered(lambda r: not r.groups and r.perm_write)

        for rule in global_write_rules:
            self.add_issue(
                "WARN",
                "RULE-GLOBAL-WRITE",
                f"{rule.model_id.model}: {rule.name}",
                "Global write rule (no groups specified) - affects all users",
                "Consider restricting rule to specific groups",
            )
            print(f"  [WARN] {rule.model_id.model} / {rule.name}: Global write rule")

        print("\n  Summary:")
        print(f"    Record rules checked: {self.stats['rules_total']}")
        print(f"    Invalid domains: {len(invalid_domains)}")
        print(f"    Global write rules: {len(global_write_rules)}")

        if len(invalid_domains) == 0:
            print("    [OK] All record rule domains are valid")

    def check_privilege_coverage(self):
        """Check user-facing groups have privilege_id set."""
        print("\n[PRIVILEGE COVERAGE]")
        print("=" * 60)

        ResGroups = self.env["res.groups"]

        try:
            # Get all custom module groups
            IrModuleModule = self.env["ir.module.module"]
            custom_modules = IrModuleModule.search([("name", "=like", "trn_%"), ("state", "=", "installed")])
            module_names = custom_modules.mapped("name")

            IrModelData = self.env["ir.model.data"]
            group_xmlids = IrModelData.search([("model", "=", "res.groups"), ("module", "in", module_names)])
            group_ids = group_xmlids.mapped("res_id")
            custom_groups = ResGroups.browse(group_ids)

            # Check if privilege_id field exists
            has_privilege_field = "privilege_id" in custom_groups._fields

            if not has_privilege_field:
                print("  [INFO] privilege_id field not found on res.groups")
                print("  [INFO] This check requires privilege_id field on res.groups")
                return
        except Exception as e:
            print(f"  [ERROR] Could not query groups: {e}")
            return

        # Find user-facing groups (in Users menu/form)
        missing_privilege = []

        for group in custom_groups:
            # Check if group is user-facing (category is not hidden)
            if group.category_id and not group.category_id.xml_id:
                continue

            # Check if has privilege_id
            if not group.privilege_id:
                missing_privilege.append(group.complete_name)
                self.add_issue(
                    "WARN",
                    "GROUP-NO-PRIVILEGE",
                    group.complete_name,
                    "User-facing group without privilege_id set",
                    "Set privilege_id for groups visible in user form",
                )
                print(f"  [WARN] {group.complete_name}: No privilege_id set")

        print("\n  Summary:")
        print(f"    Groups checked: {len(custom_groups)}")
        print(f"    Missing privilege: {len(missing_privilege)}")

    def check_sensitive_model_access(self):
        """Check access to sensitive models."""
        print("\n[SENSITIVE MODEL ACCESS]")
        print("=" * 60)

        IrModelAccess = self.env["ir.model.access"]

        # Define sensitive models
        sensitive_models = [
            "res.users",
            "res.groups",
            "ir.model.access",
            "ir.rule",
            "ir.config_parameter",
        ]

        for model_name in sensitive_models:
            try:
                # Find ACLs that grant write access
                write_acls = IrModelAccess.search([("model_id.model", "=", model_name), ("perm_write", "=", True)])

                if not write_acls:
                    continue

                print(f"\n  {model_name}:")
                for acl in write_acls:
                    group_name = acl.group_id.complete_name if acl.group_id else "ALL USERS"
                    print(f"    Write access: {group_name}")

                    if not acl.group_id:
                        self.add_issue(
                            "ERROR",
                            "SENSITIVE-NO-GROUP",
                            model_name,
                            "Write access to sensitive model without group restriction",
                            f"Restrict write access to {model_name} to admin groups only",
                        )
            except Exception:
                # Model might not exist
                pass

    def generate_report(self):
        """Generate final audit report."""
        print("\n" + "=" * 60)
        print("AUDIT SUMMARY")
        print("=" * 60)

        error_count = sum(1 for i in self.issues if i["severity"] == "ERROR")
        warn_count = sum(1 for i in self.issues if i["severity"] == "WARN")
        info_count = sum(1 for i in self.issues if i["severity"] == "INFO")

        print(f"\nTotal issues found: {len(self.issues)}")
        print(f"  Errors: {error_count}")
        print(f"  Warnings: {warn_count}")
        print(f"  Info: {info_count}")

        print("\nStatistics:")
        print(f"  Total models: {self.stats.get('models_total', 0)}")
        print(f"  Models without ACL: {self.stats.get('models_without_acl', 0)}")
        print(f"  Total groups: {self.stats.get('groups_total', 0)}")
        print(f"  Unused groups: {self.stats.get('groups_unused', 0)}")
        print(f"  Record rules: {self.stats.get('rules_total', 0)}")

        if error_count == 0 and warn_count == 0:
            print("\n[OK] No critical security issues found!")
        elif error_count > 0:
            print(f"\n[CRITICAL] Found {error_count} errors that should be fixed")
        else:
            print(f"\n[ATTENTION] Found {warn_count} warnings to review")

        # Print top issues with remediation
        if self.issues:
            print("\n" + "=" * 60)
            print("TOP ISSUES TO ADDRESS")
            print("=" * 60)

            errors = [i for i in self.issues if i["severity"] == "ERROR"][:5]
            for issue in errors:
                print(f"\n[{issue['severity']}] {issue['context']}")
                print(f"  Problem: {issue['message']}")
                if issue["remediation"]:
                    print(f"  Fix: {issue['remediation']}")

        print("\n" + "=" * 60)

    def run_all_checks(self):
        """Run all security checks."""
        print("\n" + "=" * 60)
        print("ODOO DYNAMIC SECURITY AUDIT")
        print("=" * 60)
        print(f"Database: {self.env.cr.dbname}")

        try:
            # Run all checks
            self.check_model_acl_coverage()
            self.check_group_usage()
            self.check_group_hierarchy()
            self.check_effective_permissions()
            self.check_record_rules()
            self.check_privilege_coverage()
            self.check_sensitive_model_access()

            # Generate final report
            self.generate_report()

            return self.issues

        except Exception as e:
            print(f"\n[FATAL ERROR] Audit failed: {e}")
            import traceback

            traceback.print_exc()
            return []


def run_in_odoo_shell(env):
    """Run when executed inside Odoo shell context."""
    auditor = DynamicSecurityAuditor(env)
    return auditor.run_all_checks()


# Entry point for different execution modes
if __name__ == "__main__":
    # Try to detect if running in Odoo shell
    try:
        # If 'env' is available, we're in Odoo shell
        result = run_in_odoo_shell(env)  # noqa: F821

        # Exit with appropriate code
        error_count = sum(1 for i in result if i["severity"] == "ERROR")
        sys.exit(1 if error_count > 0 else 0)

    except NameError:
        print("=" * 60)
        print("ERROR: Not running in Odoo shell context")
        print("=" * 60)
        print("\nThis script must be run inside Odoo shell:")
        print("\n  Method 1 - Pipe script to shell:")
        print("    odoo shell -d DATABASE < scripts/audit_security_dynamic.py")
        print("")
        print("  Method 2 - Use odoo-bin:")
        print("    ./odoo-bin shell -d DATABASE -c odoo.conf < scripts/audit_security_dynamic.py")
        print("")
        print("  Method 3 - Interactive mode:")
        print("    odoo shell -d DATABASE")
        print("    >>> exec(open('scripts/audit_security_dynamic.py').read())")
        print("")
        sys.exit(1)
