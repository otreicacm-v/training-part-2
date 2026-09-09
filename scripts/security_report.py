#!/usr/bin/env python3
"""
Security visualization and reporting for Odoo projects.

This script runs in the Odoo shell and generates comprehensive visualizations
of the security model, including group hierarchies, permission matrices, and
record rules.

Usage (in Odoo shell):
    odoo shell -d your_database
    >>> exec(open('scripts/security_report.py').read())
    >>> report = SecurityReport(env)
    >>> report.print_hierarchy()
    >>> report.print_matrix()
    >>> report.generate_html('security_report.html')
    >>> report.generate_csv('permissions_matrix.csv')
    >>> report.generate_mermaid()

Or run specific filters:
    >>> report.print_hierarchy(filter_prefix='trn_')
    >>> report.print_matrix(filter_groups=['group_{domain}_manager'])
    >>> report.get_user_permissions('admin')
"""

import csv
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger(__name__)


class SecurityReport:
    """Generate comprehensive security reports for Odoo projects."""

    def __init__(self, env):
        """Initialize with Odoo environment."""
        self.env = env
        self._group_hierarchy = None
        self._permission_matrix = None
        self._record_rules = None

    def get_group_hierarchy(self, filter_prefix=None):
        """
        Build group inheritance tree.

        Args:
            filter_prefix: Only include groups starting with this prefix (e.g., 'trn_')

        Returns:
            dict: Nested structure of groups with their implied groups
        """
        if self._group_hierarchy is not None and filter_prefix is None:
            return self._group_hierarchy

        Groups = self.env["res.groups"]
        domain = []
        if filter_prefix:
            domain = [("name", "=like", f"{filter_prefix}%")]

        groups = Groups.search(domain, order="name")

        hierarchy = {}
        for group in groups:
            hierarchy[group.id] = {
                "id": group.id,
                "xml_id": self._get_xml_id(group),
                "name": group.name,
                "comment": group.comment or "",
                "implied_ids": [g.id for g in group.implied_ids],
                "implying_ids": [],  # Will be populated below
                "user_count": len(group.user_ids),
                "privilege": self._get_privilege_info(group),
            }

        # Build reverse mapping (who implies this group)
        for group_id, data in hierarchy.items():
            for implied_id in data["implied_ids"]:
                if implied_id in hierarchy:
                    hierarchy[implied_id]["implying_ids"].append(group_id)

        if filter_prefix is None:
            self._group_hierarchy = hierarchy

        return hierarchy

    def get_permission_matrix(self, filter_groups=None, filter_models=None):
        """
        Build groups × models permission matrix.

        Args:
            filter_groups: List of group XML IDs to include
            filter_models: List of model names to include (e.g., ['trn.{model}'])

        Returns:
            dict: {
                'groups': [group_data, ...],
                'models': [model_name, ...],
                'matrix': {(group_id, model): {'read': True, 'write': False, ...}}
            }
        """
        Access = self.env["ir.model.access"]
        Models = self.env["ir.model"]

        # Get all access rights
        access_domain = []
        if filter_models:
            model_ids = Models.search([("model", "in", filter_models)]).ids
            access_domain.append(("model_id", "in", model_ids))

        accesses = Access.search(access_domain)

        # Build matrix
        matrix = defaultdict(lambda: {"read": False, "write": False, "create": False, "delete": False})
        models_set = set()
        groups_dict = {}

        for access in accesses:
            model_name = access.model_id.model
            models_set.add(model_name)

            # Handle both group-specific and global (no group) access
            if access.group_id:
                group_id = access.group_id.id
                if group_id not in groups_dict:
                    groups_dict[group_id] = {
                        "id": group_id,
                        "xml_id": self._get_xml_id(access.group_id),
                        "name": access.group_id.name,
                    }

                key = (group_id, model_name)
                matrix[key]["read"] = matrix[key]["read"] or access.perm_read
                matrix[key]["write"] = matrix[key]["write"] or access.perm_write
                matrix[key]["create"] = matrix[key]["create"] or access.perm_create
                matrix[key]["delete"] = matrix[key]["delete"] or access.perm_unlink
            else:
                # Global access (no group required)
                key = (None, model_name)
                matrix[key]["read"] = matrix[key]["read"] or access.perm_read
                matrix[key]["write"] = matrix[key]["write"] or access.perm_write
                matrix[key]["create"] = matrix[key]["create"] or access.perm_create
                matrix[key]["delete"] = matrix[key]["delete"] or access.perm_unlink

        # Filter groups if requested
        if filter_groups:
            groups_dict = {
                gid: gdata
                for gid, gdata in groups_dict.items()
                if any(fg in gdata["xml_id"] or fg in gdata["name"] for fg in filter_groups)
            }

        # Sort models (trn.* first)
        models_sorted = sorted(models_set, key=lambda m: (not m.startswith("trn."), m))

        groups_sorted = sorted(groups_dict.values(), key=lambda g: g["name"])

        return {
            "groups": groups_sorted,
            "models": models_sorted,
            "matrix": dict(matrix),
        }

    def get_user_permissions(self, user_login_or_id):
        """
        Get effective permissions for a specific user.

        Args:
            user_login_or_id: User login or ID

        Returns:
            dict: User info with groups and effective permissions
        """
        Users = self.env["res.users"]

        # Find user
        if isinstance(user_login_or_id, int):
            user = Users.browse(user_login_or_id)
        else:
            user = Users.search([("login", "=", user_login_or_id)], limit=1)

        if not user:
            return {"error": f"User not found: {user_login_or_id}"}

        # Get all groups (direct and implied)
        all_groups = user.groups_id
        direct_groups = user.groups_id

        # Get implied groups
        implied_groups = self.env["res.groups"]
        for group in direct_groups:
            implied_groups |= group.trans_implied_ids

        # Build permission summary
        Access = self.env["ir.model.access"]
        permissions_by_model = defaultdict(lambda: {"read": False, "write": False, "create": False, "delete": False})

        # Check access for each group
        for group in all_groups:
            accesses = Access.search([("group_id", "=", group.id)])
            for access in accesses:
                model = access.model_id.model
                permissions_by_model[model]["read"] = permissions_by_model[model]["read"] or access.perm_read
                permissions_by_model[model]["write"] = permissions_by_model[model]["write"] or access.perm_write
                permissions_by_model[model]["create"] = permissions_by_model[model]["create"] or access.perm_create
                permissions_by_model[model]["delete"] = permissions_by_model[model]["delete"] or access.perm_unlink

        # Also check global access (no group)
        global_accesses = Access.search([("group_id", "=", False)])
        for access in global_accesses:
            model = access.model_id.model
            permissions_by_model[model]["read"] = permissions_by_model[model]["read"] or access.perm_read
            permissions_by_model[model]["write"] = permissions_by_model[model]["write"] or access.perm_write
            permissions_by_model[model]["create"] = permissions_by_model[model]["create"] or access.perm_create
            permissions_by_model[model]["delete"] = permissions_by_model[model]["delete"] or access.perm_unlink

        return {
            "user_id": user.id,
            "login": user.login,
            "name": user.name,
            "direct_groups": [{"id": g.id, "name": g.name, "xml_id": self._get_xml_id(g)} for g in direct_groups],
            "implied_groups": [{"id": g.id, "name": g.name, "xml_id": self._get_xml_id(g)} for g in implied_groups],
            "all_groups_count": len(all_groups),
            "permissions": dict(permissions_by_model),
        }

    def get_record_rules(self, filter_models=None):
        """
        Get all record rules organized by model.

        Args:
            filter_models: List of model names to filter (e.g., ['trn.{model}'])

        Returns:
            dict: {model_name: [rule_data, ...]}
        """
        if self._record_rules is not None and filter_models is None:
            return self._record_rules

        Rules = self.env["ir.rule"]
        domain = []
        if filter_models:
            domain = [("model_id.model", "in", filter_models)]

        rules = Rules.search(domain, order="model_id, name")

        rules_by_model = defaultdict(list)
        for rule in rules:
            model_name = rule.model_id.model
            rule_data = {
                "id": rule.id,
                "xml_id": self._get_xml_id(rule),
                "name": rule.name,
                "global": rule.global_rule,
                "groups": [{"id": g.id, "name": g.name, "xml_id": self._get_xml_id(g)} for g in rule.groups],
                "domain_force": rule.domain_force or "[]",
                "perm_read": rule.perm_read,
                "perm_write": rule.perm_write,
                "perm_create": rule.perm_create,
                "perm_unlink": rule.perm_unlink,
            }
            rules_by_model[model_name].append(rule_data)

        result = dict(rules_by_model)
        if filter_models is None:
            self._record_rules = result

        return result

    # ========================================================================
    # Text/ASCII Output Methods
    # ========================================================================

    def print_hierarchy(self, filter_prefix=None, root_groups=None):
        """
        Print ASCII tree of group hierarchy.

        Args:
            filter_prefix: Only show groups with names starting with this
            root_groups: List of root group XML IDs to start from
        """
        hierarchy = self.get_group_hierarchy(filter_prefix)

        print("\n" + "=" * 80)
        print("GROUP HIERARCHY (via implied_ids)")
        print("=" * 80)

        # Find root groups (not implied by anyone, or specified roots)
        if root_groups:
            roots = [gid for gid, data in hierarchy.items() if data["xml_id"] in root_groups]
        else:
            roots = [gid for gid, data in hierarchy.items() if not data["implying_ids"]]

        # Sort roots by name
        roots = sorted(roots, key=lambda gid: hierarchy[gid]["name"])

        printed = set()

        def print_tree(group_id, prefix="", is_last=True):
            """Recursively print tree structure."""
            if group_id in printed:
                return
            printed.add(group_id)

            data = hierarchy.get(group_id)
            if not data:
                return

            # Tree characters
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            # Format group info
            xml_id = data["xml_id"]
            name = data["name"]
            users = f"({data['user_count']} users)" if data["user_count"] else ""
            privilege = f"[{data['privilege']}]" if data["privilege"] else ""

            print(f"{prefix}{connector}{xml_id}")
            if name != xml_id:
                print(f"{prefix}{extension}  Name: {name}")
            if users:
                print(f"{prefix}{extension}  {users}")
            if privilege:
                print(f"{prefix}{extension}  Privilege: {privilege}")
            if data["comment"]:
                comment = data["comment"][:60] + "..." if len(data["comment"]) > 60 else data["comment"]
                print(f"{prefix}{extension}  Comment: {comment}")

            # Print implied groups
            implied = data["implied_ids"]
            for i, implied_id in enumerate(implied):
                is_last_child = i == len(implied) - 1
                print_tree(implied_id, prefix + extension, is_last_child)

        # Print each root
        for i, root_id in enumerate(roots):
            is_last_root = i == len(roots) - 1
            print_tree(root_id, "", is_last_root)
            if not is_last_root:
                print()

        print("\n" + "=" * 80)
        print(f"Total groups: {len(hierarchy)}")
        print("=" * 80 + "\n")

    def print_matrix(self, filter_groups=None, filter_models=None, limit_models=20):
        """
        Print ASCII permission matrix.

        Args:
            filter_groups: List of group patterns to include
            filter_models: List of model names to include
            limit_models: Maximum number of models to show
        """
        data = self.get_permission_matrix(filter_groups, filter_models)

        print("\n" + "=" * 120)
        print("PERMISSION MATRIX (Groups × Models)")
        print("=" * 120)
        print("Legend: R=Read, W=Write, C=Create, D=Delete")
        print("=" * 120 + "\n")

        groups = data["groups"]
        models = data["models"][:limit_models]
        matrix = data["matrix"]

        if not groups:
            print("No groups found matching filter criteria.")
            return

        if not models:
            print("No models found matching filter criteria.")
            return

        # Calculate column widths
        max_group_name = max(len(g["name"]) for g in groups) if groups else 20
        max_group_name = min(max_group_name, 40)  # Cap at 40
        model_col_width = 6  # "RWCD  "

        # Print header
        header = " " * max_group_name + " │ "
        for model in models:
            # Shorten model name if needed
            model_short = model.replace("trn.", "")[:10]
            header += f"{model_short:^{model_col_width}}│ "
        print(header)
        print("─" * len(header))

        # Print each group row
        for group in groups:
            group_name = group["name"][:max_group_name]
            row = f"{group_name:<{max_group_name}} │ "

            for model in models:
                perms = matrix.get((group["id"], model), {})
                perm_str = ""
                perm_str += "R" if perms.get("read") else "-"
                perm_str += "W" if perms.get("write") else "-"
                perm_str += "C" if perms.get("create") else "-"
                perm_str += "D" if perms.get("delete") else "-"
                row += f"{perm_str:^{model_col_width}}│ "

            print(row)

        print("\n" + "=" * 120)
        print(f"Groups: {len(groups)}, Models: {len(models)} (showing {limit_models} max)")
        if len(data["models"]) > limit_models:
            print(f"Note: {len(data['models']) - limit_models} more models not shown. Use HTML report for full view.")
        print("=" * 120 + "\n")

    def print_user_permissions(self, user_login_or_id):
        """Print effective permissions for a user."""
        data = self.get_user_permissions(user_login_or_id)

        if "error" in data:
            print(f"\nError: {data['error']}\n")
            return

        print("\n" + "=" * 80)
        print(f"USER PERMISSIONS: {data['name']} ({data['login']})")
        print("=" * 80)

        print(f"\nDirect Groups ({len(data['direct_groups'])}):")
        for group in data["direct_groups"]:
            print(f"  - {group['name']} ({group['xml_id']})")

        print(f"\nImplied Groups ({len(data['implied_groups'])}):")
        for group in data["implied_groups"]:
            print(f"  - {group['name']} ({group['xml_id']})")

        print(f"\nTotal Groups: {data['all_groups_count']}")

        # Show permissions for trn.* models
        print("\nEffective Permissions (trn.* models):")
        custom_perms = {k: v for k, v in data["permissions"].items() if k.startswith("trn.")}
        for model in sorted(custom_perms.keys())[:20]:
            perms = custom_perms[model]
            perm_str = ""
            perm_str += "R" if perms["read"] else "-"
            perm_str += "W" if perms["write"] else "-"
            perm_str += "C" if perms["create"] else "-"
            perm_str += "D" if perms["delete"] else "-"
            print(f"  {model:40s} [{perm_str}]")

        print("\n" + "=" * 80 + "\n")

    def print_record_rules(self, filter_models=None, limit=20):
        """Print record rules summary."""
        rules = self.get_record_rules(filter_models)

        print("\n" + "=" * 120)
        print("RECORD RULES (Row-Level Security)")
        print("=" * 120)

        total_rules = sum(len(rule_list) for rule_list in rules.values())
        print(f"Total rules: {total_rules} across {len(rules)} models\n")

        count = 0
        for model in sorted(rules.keys()):
            if count >= limit:
                remaining = total_rules - count
                print(f"\n... and {remaining} more rules. Use HTML report for full view.")
                break

            print(f"\n{model}:")
            print("-" * 120)

            for rule in rules[model]:
                count += 1
                global_str = "[GLOBAL]" if rule["global"] else ""
                groups_str = ", ".join(g["name"] for g in rule["groups"]) if rule["groups"] else "All users"

                perms = []
                if rule["perm_read"]:
                    perms.append("Read")
                if rule["perm_write"]:
                    perms.append("Write")
                if rule["perm_create"]:
                    perms.append("Create")
                if rule["perm_unlink"]:
                    perms.append("Delete")
                perm_str = ", ".join(perms) if perms else "None"

                print(f"  {rule['name']} {global_str}")
                print(f"    Groups: {groups_str}")
                print(f"    Perms: {perm_str}")
                print(f"    Domain: {rule['domain_force']}")
                print()

        print("=" * 120 + "\n")

    # ========================================================================
    # HTML Generation
    # ========================================================================

    def generate_html(self, filename="security_report.html"):
        """Generate interactive HTML report."""
        hierarchy = self.get_group_hierarchy()
        matrix_data = self.get_permission_matrix()
        rules = self.get_record_rules()

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Odoo Security Report</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin-bottom: 20px;
        }}
        .tabs {{
            display: flex;
            gap: 10px;
            border-bottom: 2px solid #ecf0f1;
            margin-bottom: 20px;
        }}
        .tab {{
            padding: 10px 20px;
            cursor: pointer;
            background: #ecf0f1;
            border: none;
            border-radius: 4px 4px 0 0;
            font-size: 14px;
            font-weight: 500;
        }}
        .tab.active {{
            background: #3498db;
            color: white;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        .filter {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .filter input {{
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            width: 300px;
            font-size: 14px;
        }}
        .tree {{
            font-family: "Courier New", monospace;
            line-height: 1.6;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 4px;
            overflow-x: auto;
        }}
        .tree-node {{
            margin: 4px 0;
        }}
        .tree-node .xml-id {{
            font-weight: bold;
            color: #2c3e50;
        }}
        .tree-node .detail {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin-left: 20px;
        }}
        .matrix-container {{
            overflow-x: auto;
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border: 1px solid #ddd;
        }}
        th {{
            background: #34495e;
            color: white;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        tr:hover {{
            background: #e8f4f8;
        }}
        .perm {{
            display: inline-block;
            width: 18px;
            height: 18px;
            text-align: center;
            border-radius: 3px;
            font-weight: bold;
            font-size: 11px;
            line-height: 18px;
        }}
        .perm.read {{ background: #27ae60; color: white; }}
        .perm.write {{ background: #f39c12; color: white; }}
        .perm.create {{ background: #3498db; color: white; }}
        .perm.delete {{ background: #e74c3c; color: white; }}
        .perm.none {{ background: #ecf0f1; color: #95a5a6; }}
        .rule-card {{
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 15px;
            background: #f8f9fa;
        }}
        .rule-card h4 {{
            margin: 0 0 10px 0;
            color: #2c3e50;
        }}
        .rule-card .label {{
            font-weight: 600;
            color: #7f8c8d;
            display: inline-block;
            width: 100px;
        }}
        .rule-card .domain {{
            font-family: "Courier New", monospace;
            background: white;
            padding: 8px;
            border-radius: 3px;
            margin-top: 5px;
            font-size: 12px;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 5px;
        }}
        .badge.global {{ background: #e74c3c; color: white; }}
        .badge.group {{ background: #3498db; color: white; }}
        .export-buttons {{
            margin: 20px 0;
            display: flex;
            gap: 10px;
        }}
        .btn {{
            padding: 10px 20px;
            background: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }}
        .btn:hover {{
            background: #2980b9;
        }}
        .collapsible {{
            cursor: pointer;
            user-select: none;
        }}
        .collapsible:before {{
            content: "▼ ";
            display: inline-block;
            transition: transform 0.2s;
        }}
        .collapsible.collapsed:before {{
            transform: rotate(-90deg);
        }}
        .collapsible-content {{
            margin-left: 20px;
        }}
        .collapsible-content.collapsed {{
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Odoo Security Report</h1>
        <div class="meta">
            Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            Total Groups: {len(hierarchy)} |
            Total Models: {len(matrix_data['models'])} |
            Total Rules: {sum(len(r) for r in rules.values())}
        </div>

        <div class="tabs">
            <button class="tab active" onclick="showTab('hierarchy')">Group Hierarchy</button>
            <button class="tab" onclick="showTab('matrix')">Permission Matrix</button>
            <button class="tab" onclick="showTab('rules')">Record Rules</button>
        </div>

        <!-- HIERARCHY TAB -->
        <div id="tab-hierarchy" class="tab-content active">
            <h2>Group Hierarchy</h2>
            <div class="filter">
                <input type="text" id="hierarchy-filter" placeholder="Filter groups..."
                       onkeyup="filterHierarchy()">
            </div>
            <div class="tree" id="hierarchy-tree">
                {self._generate_html_hierarchy(hierarchy)}
            </div>
        </div>

        <!-- MATRIX TAB -->
        <div id="tab-matrix" class="tab-content">
            <h2>Permission Matrix</h2>
            <div class="filter">
                <input type="text" id="matrix-group-filter" placeholder="Filter groups..."
                       onkeyup="filterMatrix()">
                <input type="text" id="matrix-model-filter" placeholder="Filter models..."
                       onkeyup="filterMatrix()" style="margin-left: 10px;">
            </div>
            <div class="export-buttons">
                <button class="btn" onclick="exportMatrixCSV()">Export as CSV</button>
            </div>
            <div class="matrix-container">
                {self._generate_html_matrix(matrix_data)}
            </div>
        </div>

        <!-- RULES TAB -->
        <div id="tab-rules" class="tab-content">
            <h2>Record Rules</h2>
            <div class="filter">
                <input type="text" id="rules-filter" placeholder="Filter by model or rule name..."
                       onkeyup="filterRules()">
            </div>
            {self._generate_html_rules(rules)}
        </div>
    </div>

    <script>
        function showTab(tabName) {{
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));

            // Show selected tab
            document.getElementById('tab-' + tabName).classList.add('active');
            event.target.classList.add('active');
        }}

        function filterHierarchy() {{
            const filter = document.getElementById('hierarchy-filter').value.toLowerCase();
            const nodes = document.querySelectorAll('.tree-node');

            nodes.forEach(node => {{
                const text = node.textContent.toLowerCase();
                node.style.display = text.includes(filter) ? '' : 'none';
            }});
        }}

        function filterMatrix() {{
            const groupFilter = document.getElementById('matrix-group-filter').value.toLowerCase();
            const modelFilter = document.getElementById('matrix-model-filter').value.toLowerCase();
            const table = document.querySelector('#tab-matrix table');
            const rows = table.querySelectorAll('tbody tr');

            rows.forEach(row => {{
                const groupText = row.cells[0].textContent.toLowerCase();
                let show = groupText.includes(groupFilter);

                if (show && modelFilter) {{
                    const cells = Array.from(row.cells).slice(1);
                    const hasMatch = cells.some(cell => {{
                        const modelName = table.querySelector('thead th:nth-child(' +
                            (Array.from(row.cells).indexOf(cell) + 1) + ')').textContent.toLowerCase();
                        return modelName.includes(modelFilter) &&
                               cell.textContent.trim() !== '----';
                    }});
                    show = hasMatch;
                }}

                row.style.display = show ? '' : 'none';
            }});
        }}

        function filterRules() {{
            const filter = document.getElementById('rules-filter').value.toLowerCase();
            const rules = document.querySelectorAll('.rule-card');

            rules.forEach(rule => {{
                const text = rule.textContent.toLowerCase();
                rule.style.display = text.includes(filter) ? '' : 'none';
            }});
        }}

        function exportMatrixCSV() {{
            const table = document.querySelector('#tab-matrix table');
            let csv = [];

            // Headers
            const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent);
            csv.push(headers.join(','));

            // Rows
            table.querySelectorAll('tbody tr').forEach(row => {{
                if (row.style.display !== 'none') {{
                    const cols = Array.from(row.cells).map(td => {{
                        return '"' + td.textContent.trim().replace(/"/g, '""') + '"';
                    }});
                    csv.push(cols.join(','));
                }}
            }});

            // Download
            const blob = new Blob([csv.join('\\n')], {{ type: 'text/csv' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'permissions_matrix.csv';
            a.click();
        }}

        function toggleCollapse(element) {{
            element.classList.toggle('collapsed');
            const content = element.nextElementSibling;
            if (content) {{
                content.classList.toggle('collapsed');
            }}
        }}
    </script>
</body>
</html>"""

        # Write to file
        output_path = Path(filename)
        output_path.write_text(html, encoding="utf-8")
        print(f"\n✓ HTML report generated: {output_path.absolute()}")
        return str(output_path.absolute())

    def _generate_html_hierarchy(self, hierarchy):
        """Generate HTML for group hierarchy tree."""
        # Find roots (groups not implied by others)
        roots = [gid for gid, data in hierarchy.items() if not data["implying_ids"]]
        roots = sorted(roots, key=lambda gid: hierarchy[gid]["name"])

        html_parts = []
        printed = set()

        def render_node(group_id, level=0):
            """Recursively render tree node."""
            if group_id in printed:
                return ""
            printed.add(group_id)

            data = hierarchy.get(group_id)
            if not data:
                return ""

            indent = "&nbsp;" * (level * 4)
            parts = []

            # Main line
            xml_id = data["xml_id"]
            name = data["name"] if data["name"] != xml_id else ""
            users = f"({data['user_count']} users)" if data["user_count"] else ""

            parts.append(f'<div class="tree-node" data-level="{level}">')
            parts.append(f'{indent}<span class="xml-id">{xml_id}</span>')
            if name:
                parts.append(f'<span class="detail"> - {name}</span>')
            if users:
                parts.append(f'<span class="detail"> {users}</span>')
            parts.append("</div>")

            # Details
            if data["privilege"]:
                parts.append(
                    f'<div class="tree-node"><span class="detail">{indent}  '
                    f'Privilege: {data["privilege"]}</span></div>'
                )
            if data["comment"]:
                comment = data["comment"][:80] + "..." if len(data["comment"]) > 80 else data["comment"]
                parts.append(
                    f'<div class="tree-node"><span class="detail">{indent}  ' f"Comment: {comment}</span></div>"
                )

            # Recurse to implied groups
            for implied_id in data["implied_ids"]:
                parts.append(render_node(implied_id, level + 1))

            return "".join(parts)

        for root_id in roots:
            html_parts.append(render_node(root_id))

        return "".join(html_parts) if html_parts else "<p>No groups found.</p>"

    def _generate_html_matrix(self, matrix_data):
        """Generate HTML table for permission matrix."""
        groups = matrix_data["groups"]
        models = matrix_data["models"]
        matrix = matrix_data["matrix"]

        if not groups or not models:
            return "<p>No data available.</p>"

        html_parts = ['<table id="permission-matrix">']

        # Header
        html_parts.append("<thead><tr><th>Group</th>")
        for model in models:
            model_short = model.replace("trn.", "")
            html_parts.append(f'<th title="{model}">{model_short}</th>')
        html_parts.append("</tr></thead>")

        # Body
        html_parts.append("<tbody>")
        for group in groups:
            html_parts.append(f'<tr><td title="{group["xml_id"]}">{group["name"]}</td>')

            for model in models:
                perms = matrix.get((group["id"], model), {})
                cell_html = []

                if perms.get("read"):
                    cell_html.append('<span class="perm read" title="Read">R</span>')
                else:
                    cell_html.append('<span class="perm none">-</span>')

                if perms.get("write"):
                    cell_html.append('<span class="perm write" title="Write">W</span>')
                else:
                    cell_html.append('<span class="perm none">-</span>')

                if perms.get("create"):
                    cell_html.append('<span class="perm create" title="Create">C</span>')
                else:
                    cell_html.append('<span class="perm none">-</span>')

                if perms.get("delete"):
                    cell_html.append('<span class="perm delete" title="Delete">D</span>')
                else:
                    cell_html.append('<span class="perm none">-</span>')

                html_parts.append(f'<td>{"".join(cell_html)}</td>')

            html_parts.append("</tr>")
        html_parts.append("</tbody>")
        html_parts.append("</table>")

        return "".join(html_parts)

    def _generate_html_rules(self, rules):
        """Generate HTML for record rules."""
        html_parts = []

        for model in sorted(rules.keys()):
            html_parts.append(f'<h3 class="collapsible" onclick="toggleCollapse(this)">{model}</h3>')
            html_parts.append('<div class="collapsible-content">')

            for rule in rules[model]:
                global_badge = '<span class="badge global">GLOBAL</span>' if rule["global"] else ""
                groups_str = ", ".join(g["name"] for g in rule["groups"]) if rule["groups"] else "All users"

                perms = []
                if rule["perm_read"]:
                    perms.append("Read")
                if rule["perm_write"]:
                    perms.append("Write")
                if rule["perm_create"]:
                    perms.append("Create")
                if rule["perm_unlink"]:
                    perms.append("Delete")
                perm_str = ", ".join(perms) if perms else "None"

                html_parts.append(f"""
                <div class="rule-card">
                    <h4>{rule["name"]} {global_badge}</h4>
                    <div><span class="label">XML ID:</span> {rule["xml_id"]}</div>
                    <div><span class="label">Groups:</span> {groups_str}</div>
                    <div><span class="label">Permissions:</span> {perm_str}</div>
                    <div><span class="label">Domain:</span></div>
                    <div class="domain">{rule["domain_force"]}</div>
                </div>
                """)

            html_parts.append("</div>")

        return "".join(html_parts) if html_parts else "<p>No record rules found.</p>"

    # ========================================================================
    # CSV Generation
    # ========================================================================

    def generate_csv(self, filename="permissions_matrix.csv", filter_groups=None, filter_models=None):
        """Generate CSV permission matrix."""
        data = self.get_permission_matrix(filter_groups, filter_models)

        groups = data["groups"]
        models = data["models"]
        matrix = data["matrix"]

        output_path = Path(filename)
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header row
            header = ["Group", "Group XML ID"]
            for model in models:
                header.extend([f"{model} (R)", f"{model} (W)", f"{model} (C)", f"{model} (D)"])
            writer.writerow(header)

            # Data rows
            for group in groups:
                row = [group["name"], group["xml_id"]]
                for model in models:
                    perms = matrix.get((group["id"], model), {})
                    row.append("✓" if perms.get("read") else "")
                    row.append("✓" if perms.get("write") else "")
                    row.append("✓" if perms.get("create") else "")
                    row.append("✓" if perms.get("delete") else "")
                writer.writerow(row)

        print(f"\n✓ CSV matrix generated: {output_path.absolute()}")
        return str(output_path.absolute())

    # ========================================================================
    # Mermaid Diagram Generation
    # ========================================================================

    def generate_mermaid(self, filter_prefix=None, filename=None):
        """
        Generate Mermaid diagram syntax for group hierarchy.

        Args:
            filter_prefix: Only include groups with names starting with this
            filename: If provided, write to file. Otherwise print to stdout.

        Returns:
            str: Mermaid diagram syntax
        """
        hierarchy = self.get_group_hierarchy(filter_prefix)

        lines = ["graph TD"]

        # Find roots
        roots = [gid for gid, data in hierarchy.items() if not data["implying_ids"]]

        # Create node definitions
        for _group_id, data in hierarchy.items():
            xml_id = data["xml_id"].replace(".", "_").replace("-", "_")
            label = data["xml_id"]
            if data["user_count"]:
                label += f"<br/>({data['user_count']} users)"
            lines.append(f'    {xml_id}["{label}"]')

        # Create edges (implied relationships)
        for _group_id, data in hierarchy.items():
            xml_id = data["xml_id"].replace(".", "_").replace("-", "_")
            for implied_id in data["implied_ids"]:
                if implied_id in hierarchy:
                    implied_xml = hierarchy[implied_id]["xml_id"].replace(".", "_").replace("-", "_")
                    lines.append(f"    {xml_id} --> {implied_xml}")

        # Style roots
        for root_id in roots:
            xml_id = hierarchy[root_id]["xml_id"].replace(".", "_").replace("-", "_")
            lines.append(f"    style {xml_id} fill:#3498db,stroke:#2980b9,color:#fff")

        diagram = "\n".join(lines)

        if filename:
            output_path = Path(filename)
            output_path.write_text(diagram, encoding="utf-8")
            print(f"\n✓ Mermaid diagram generated: {output_path.absolute()}")
            return str(output_path.absolute())
        else:
            print("\n" + "=" * 80)
            print("MERMAID DIAGRAM (Group Hierarchy)")
            print("=" * 80)
            print(diagram)
            print("\n" + "=" * 80)
            print("Copy this to https://mermaid.live/ to visualize")
            print("=" * 80 + "\n")
            return diagram

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_xml_id(self, record):
        """Get external ID for a record."""
        if not record:
            return ""
        IrModelData = self.env["ir.model.data"]
        data = IrModelData.search(
            [("model", "=", record._name), ("res_id", "=", record.id)], limit=1, order="module, name"
        )
        if data:
            return f"{data.module}.{data.name}"
        return f"[no_xml_id_{record.id}]"

    def _get_privilege_info(self, group):
        """Get privilege information for a group."""
        if hasattr(group, "privilege_id") and group.privilege_id:
            return self._get_xml_id(group.privilege_id)
        return ""


# =============================================================================
# Auto-run when loaded in Odoo shell
# =============================================================================

if "env" in dir():
    print("\n" + "=" * 80)
    print("SecurityReport loaded successfully!")
    print("=" * 80)
    print("\nQuick Start:")
    print("  report = SecurityReport(env)")
    print("  report.print_hierarchy()")
    print("  report.print_matrix()")
    print("  report.generate_html('security_report.html')")
    print("  report.generate_csv('permissions_matrix.csv')")
    print("  report.generate_mermaid()")
    print("\nFiltered examples:")
    print("  report.print_hierarchy(filter_prefix='trn_')")
    print("  report.print_matrix(filter_groups=['{domain}'], filter_models=['trn.{model}'])")
    print("  report.print_user_permissions('admin')")
    print("  report.print_record_rules(filter_models=['trn.{model}'])")
    print("\nFor documentation:")
    print("  report.generate_mermaid(filter_prefix='trn_', filename='security_diagram.md')")
    print("=" * 80 + "\n")
