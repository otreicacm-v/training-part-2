#!/usr/bin/env python3
"""
Create OpenProject tasks for each Odoo module under a specified epic.

This script:
1. Parses all module manifests to build a dependency graph
2. Creates tasks in OpenProject under the specified epic

Usage:
    export OPENPROJECT_API_TOKEN="your-api-token"
    python create_epic_tasks.py [--dry-run] [--epic-id 484]

Environment variables:
    OPENPROJECT_API_TOKEN: API token for OpenProject authentication
    OPENPROJECT_URL: Base URL for OpenProject (default: https://projects.acn.fr)
"""

import argparse
import ast
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_OPENPROJECT_URL = "https://projects.acn.fr"
DEFAULT_EPIC_ID = 484
DEFAULT_PROJECT_SLUG = "odoo-project"

# Priority mapping for OpenProject
# OpenProject priorities: typically 1=Low, 2=Normal, 3=High, 4=Urgent, 5=Immediate
# IDs may need adjustment based on actual OpenProject config
PRIORITY_NORMAL = 7


class ModuleAnalyzer:
    """Analyzes Odoo modules and their dependencies."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.modules: dict[str, dict] = {}
        self.dependency_graph: dict[str, set[str]] = defaultdict(set)
        self.reverse_dependencies: dict[str, set[str]] = defaultdict(set)

    def parse_manifest(self, manifest_path: Path) -> dict | None:
        """Parse a module's __manifest__.py file."""
        try:
            with open(manifest_path, encoding="utf-8") as f:
                content = f.read()
                # Use regex to find the dictionary literal within the file content
                match = re.search(r"\{[\s\S]*\}", content)
                if not match:
                    logger.warning(f"No dictionary found in manifest {manifest_path}")
                    return None
                manifest_dict = ast.literal_eval(match.group(0))
                return manifest_dict
        except (SyntaxError, ValueError) as e:
            logger.warning(f"Failed to parse manifest {manifest_path}: {e}")
            return None

    def discover_modules(self) -> None:
        """Discover all modules in the repository."""
        logger.info(f"Discovering modules in {self.base_path}")

        for manifest_path in self.base_path.glob("*/__manifest__.py"):
            # Skip archived modules
            if "archived" in str(manifest_path):
                continue

            module_name = manifest_path.parent.name
            manifest = self.parse_manifest(manifest_path)

            if manifest:
                self.modules[module_name] = {
                    "name": manifest.get("name", module_name),
                    "summary": manifest.get("summary", ""),
                    "category": manifest.get("category", ""),
                    "version": manifest.get("version", ""),
                    "depends": manifest.get("depends", []),
                    "installable": manifest.get("installable", True),
                    "path": str(manifest_path.parent),
                }

                # Build dependency graph
                for dep in manifest.get("depends", []):
                    self.dependency_graph[module_name].add(dep)
                    self.reverse_dependencies[dep].add(module_name)

        logger.info(f"Discovered {len(self.modules)} modules")

    def get_transitive_dependencies(self, module_name: str) -> set[str]:
        """Get all transitive dependencies of a module using an iterative approach."""
        deps_to_visit = list(self.dependency_graph.get(module_name, []))
        visited = set(deps_to_visit)
        all_deps = set(deps_to_visit)

        while deps_to_visit:
            dep = deps_to_visit.pop()
            for transitive_dep in self.dependency_graph.get(dep, []):
                if transitive_dep not in visited:
                    visited.add(transitive_dep)
                    all_deps.add(transitive_dep)
                    deps_to_visit.append(transitive_dep)

        return all_deps


class OpenProjectClient:
    """Client for OpenProject REST API."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v3"
        self.session = requests.Session()
        self.session.auth = ("apikey", api_token)
        self.session.headers.update({"Content-Type": "application/json"})

    def get_work_package(self, work_package_id: int) -> dict | None:
        """Get a work package by ID."""
        try:
            response = self.session.get(f"{self.api_url}/work_packages/{work_package_id}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get work package {work_package_id}: {e}")
            return None

    def get_project(self, project_slug: str) -> dict | None:
        """Get a project by slug."""
        try:
            response = self.session.get(f"{self.api_url}/projects/{project_slug}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get project {project_slug}: {e}")
            return None

    def get_priorities(self) -> list[dict]:
        """Get all available priorities."""
        try:
            response = self.session.get(f"{self.api_url}/priorities")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get priorities: {e}")
            return []

    def get_work_package_types(self, project_slug: str) -> list[dict]:
        """Get work package types available in a project."""
        try:
            response = self.session.get(f"{self.api_url}/projects/{project_slug}/types")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get work package types: {e}")
            return []

    def search_work_packages(self, project_slug: str, parent_id: int) -> list[dict]:
        """Search for work packages under a parent, handling pagination."""
        all_packages = []
        page = 1
        try:
            while True:
                # Use filters to find children of the epic
                filters = [{"parent": {"operator": "=", "values": [str(parent_id)]}}]
                response = self.session.get(
                    f"{self.api_url}/projects/{project_slug}/work_packages",
                    params={
                        "filters": json.dumps(filters),
                        "pageSize": 100,
                        "offset": page,
                    },
                )
                response.raise_for_status()
                data = response.json()
                packages = data.get("_embedded", {}).get("elements", [])
                if not packages:
                    break
                all_packages.extend(packages)
                page += 1
            return all_packages
        except requests.RequestException as e:
            logger.error(f"Failed to search work packages: {e}")
            return []

    def create_work_package(
        self,
        project_slug: str,
        subject: str,
        description: str,
        parent_id: int,
        priority_id: int,
        work_package_type: str = "Task",
    ) -> dict | None:
        """Create a new work package (task) under a parent epic."""
        payload = {
            "subject": subject,
            "description": {"format": "markdown", "raw": description},
            "_links": {
                "parent": {"href": f"/api/v3/work_packages/{parent_id}"},
                "priority": {"href": f"/api/v3/priorities/{priority_id}"},
                "type": {"href": None},  # Will be set based on available types
            },
        }

        try:
            # First, get the type ID for "Task"
            types = self.get_work_package_types(project_slug)
            task_type = next((t for t in types if t.get("name") == work_package_type), None)
            if task_type:
                payload["_links"]["type"] = {"href": task_type["_links"]["self"]["href"]}
            else:
                # Remove type link if not found, let OpenProject use default
                del payload["_links"]["type"]
                logger.warning(f"Type '{work_package_type}' not found, using default")

            response = self.session.post(
                f"{self.api_url}/projects/{project_slug}/work_packages",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create work package: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return None


def generate_task_description(module_info: dict) -> str:
    """Generate a markdown description for a module task."""
    description = f"""## Module: `{module_info.get('name', 'Unknown')}`

**Path:** `{module_info.get('path', 'N/A')}`

**Version:** {module_info.get('version', 'N/A')}

**Category:** {module_info.get('category', 'N/A')}

**Summary:** {module_info.get('summary', 'No summary available')}

### Dependencies
{', '.join(f'`{d}`' for d in module_info.get('depends', [])) or 'None'}

---
*Auto-generated task for module review*
"""
    return description


def main():
    parser = argparse.ArgumentParser(description="Create OpenProject tasks for Odoo modules under an epic")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating tasks",
    )
    parser.add_argument(
        "--epic-id",
        type=int,
        default=DEFAULT_EPIC_ID,
        help=f"OpenProject epic work package ID (default: {DEFAULT_EPIC_ID})",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=DEFAULT_PROJECT_SLUG,
        help=f"OpenProject project slug (default: {DEFAULT_PROJECT_SLUG})",
    )
    parser.add_argument(
        "--modules-path",
        type=str,
        default=None,
        help="Path to modules directory (default: auto-detect from script location)",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=PRIORITY_NORMAL,
        help=f"Priority ID for created tasks (default: {PRIORITY_NORMAL})",
    )
    parser.add_argument(
        "--list-priorities",
        action="store_true",
        help="List available priorities and exit",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip creating tasks for modules that already have tasks (default: True)",
    )

    args = parser.parse_args()

    # Get API token from environment
    api_token = os.environ.get("OPENPROJECT_API_TOKEN")
    if not api_token and not args.dry_run:
        logger.error("OPENPROJECT_API_TOKEN environment variable is required")
        logger.info("Get your API token from: OpenProject > My Account > Access tokens")
        sys.exit(1)

    base_url = os.environ.get("OPENPROJECT_URL", DEFAULT_OPENPROJECT_URL)

    # Determine modules path
    if args.modules_path:
        modules_path = Path(args.modules_path)
    else:
        # Auto-detect: assume script is in <repo>/scripts/
        script_dir = Path(__file__).resolve().parent
        modules_path = script_dir.parent

    if not modules_path.exists():
        logger.error(f"Modules path does not exist: {modules_path}")
        sys.exit(1)

    logger.info(f"Using modules path: {modules_path}")

    # Analyze modules
    analyzer = ModuleAnalyzer(modules_path)
    analyzer.discover_modules()

    if args.dry_run:
        logger.info("\n=== DRY RUN - No tasks will be created ===\n")
        client = None
    else:
        client = OpenProjectClient(base_url, api_token)

        # List priorities if requested
        if args.list_priorities:
            priorities = client.get_priorities()
            logger.info("Available priorities:")
            for p in priorities:
                logger.info(f"  ID: {p['id']}, Name: {p['name']}")
            sys.exit(0)

        # Verify epic exists
        epic = client.get_work_package(args.epic_id)
        if not epic:
            logger.error(f"Epic with ID {args.epic_id} not found")
            sys.exit(1)
        logger.info(f"Found epic: {epic.get('subject', 'Unknown')}")

        # Get existing tasks under the epic
        existing_tasks = client.search_work_packages(args.project, args.epic_id)
        existing_module_names = set()
        for task in existing_tasks:
            subject = task.get("subject", "")
            # Extract module name from subject (format: "Review [module_name] Display Name")
            match = re.search(r"\[(.+?)\]", subject)
            if match:
                module_name = match.group(1)
                existing_module_names.add(module_name)
        logger.info(f"Found {len(existing_tasks)} existing tasks under epic")

    # Sort modules alphabetically
    sorted_modules = sorted(analyzer.modules.items(), key=lambda x: x[0])

    # Create tasks
    created_count = 0
    skipped_count = 0
    error_count = 0

    for module_name, module_info in sorted_modules:
        subject = f"Review [{module_name}] {module_info.get('name', module_name)}"
        description = generate_task_description(module_info)

        if args.dry_run:
            logger.info(f"Would create: {subject}")
            created_count += 1
        else:
            # Check if task already exists
            if args.skip_existing and module_name in existing_module_names:
                logger.debug(f"Skipping existing task for: {module_name}")
                skipped_count += 1
                continue

            result = client.create_work_package(
                project_slug=args.project,
                subject=subject,
                description=description,
                parent_id=args.epic_id,
                priority_id=args.priority,
            )

            if result:
                logger.info(f"Created: {subject} (ID: {result.get('id')})")
                created_count += 1
            else:
                logger.error(f"Failed to create: {subject}")
                error_count += 1

    # Summary
    logger.info("\n=== Summary ===")
    logger.info(f"Total modules: {len(analyzer.modules)}")
    if args.dry_run:
        logger.info(f"Would create: {created_count} tasks")
    else:
        logger.info(f"Created: {created_count} tasks")
        logger.info(f"Skipped (existing): {skipped_count} tasks")
        if error_count:
            logger.info(f"Errors: {error_count} tasks")


if __name__ == "__main__":
    main()
