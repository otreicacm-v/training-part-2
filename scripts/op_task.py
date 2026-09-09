#!/usr/bin/env python3
"""
OpenProject task management CLI for Claude Code workflows.

Usage:
    python scripts/op_task.py get <id> [--format=markdown|json]
    python scripts/op_task.py list [--project myproject] [--status open] [--json]
    python scripts/op_task.py search <query> [--project myproject] [--json]
    python scripts/op_task.py create --project myproject --subject "Title" [options]
    python scripts/op_task.py update <id> [--status "In progress"] [--assignee "Name"]

Environment variables:
    OPENPROJECT_API_TOKEN: API token for OpenProject authentication
    OPENPROJECT_URL: Base URL for OpenProject (default: https://projects.acn.fr)
"""

import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


DEFAULT_OPENPROJECT_URL = "https://projects.acn.fr"


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
            print(f"ERROR: Failed to fetch work package {work_package_id}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return None

    def get_work_package_activities(self, work_package_id: int) -> list[dict]:
        """Get activities (comments) for a work package."""
        try:
            response = self.session.get(f"{self.api_url}/work_packages/{work_package_id}/activities")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException:
            return []

    def list_work_packages(
        self,
        project_slug: str = None,
        status: str = None,
        assignee: str = None,
        wp_type: str = None,
        parent_id: int = None,
        limit: int = 20,
    ) -> list[dict]:
        """List work packages with optional filters."""
        try:
            filters = []

            # Build filter array
            if status and status != "all":
                if status == "open":
                    # Open includes multiple statuses
                    filters.append(
                        {
                            "status": {
                                "operator": "o",  # open
                                "values": [],
                            }
                        }
                    )
                elif status == "closed":
                    filters.append(
                        {
                            "status": {
                                "operator": "c",  # closed
                                "values": [],
                            }
                        }
                    )

            if assignee:
                filters.append({"assignee": {"operator": "~", "values": [assignee]}})

            if wp_type:
                filters.append({"type": {"operator": "=", "values": [wp_type]}})

            if parent_id:
                filters.append({"parent": {"operator": "=", "values": [str(parent_id)]}})

            params = {
                "pageSize": min(limit, 100),
                "offset": 1,
            }

            if filters:
                params["filters"] = json.dumps(filters)

            # Use project-specific endpoint if project is specified
            if project_slug:
                url = f"{self.api_url}/projects/{project_slug}/work_packages"
            else:
                url = f"{self.api_url}/work_packages"

            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to list work packages: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return []

    def search_work_packages(self, query: str, project_slug: str = None, limit: int = 20) -> list[dict]:
        """Search work packages by text query."""
        try:
            params = {
                "pageSize": min(limit, 100),
                "offset": 1,
            }

            # Add search filter
            filters = [{"search": {"operator": "**", "values": [query]}}]

            params["filters"] = json.dumps(filters)

            # Use project-specific endpoint if project is specified
            if project_slug:
                url = f"{self.api_url}/projects/{project_slug}/work_packages"
            else:
                url = f"{self.api_url}/work_packages"

            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to search work packages: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return []

    def get_project(self, project_slug: str) -> dict | None:
        """Get a project by slug."""
        try:
            response = self.session.get(f"{self.api_url}/projects/{project_slug}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"ERROR: Failed to get project {project_slug}: {e}")
            return None

    def get_priorities(self) -> list[dict]:
        """Get all available priorities."""
        try:
            response = self.session.get(f"{self.api_url}/priorities")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to get priorities: {e}")
            return []

    def get_work_package_types(self, project_slug: str) -> list[dict]:
        """Get work package types available in a project."""
        try:
            response = self.session.get(f"{self.api_url}/projects/{project_slug}/types")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to get work package types: {e}")
            return []

    def get_statuses(self) -> list[dict]:
        """Get all available statuses."""
        try:
            response = self.session.get(f"{self.api_url}/statuses")
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to get statuses: {e}")
            return []

    def get_users(self, name_filter: str = None) -> list[dict]:
        """Get users, optionally filtered by name."""
        try:
            params = {}
            if name_filter:
                filters = [{"name": {"operator": "~", "values": [name_filter]}}]
                params["filters"] = json.dumps(filters)

            response = self.session.get(f"{self.api_url}/users", params=params)
            response.raise_for_status()
            return response.json().get("_embedded", {}).get("elements", [])
        except requests.RequestException as e:
            print(f"ERROR: Failed to get users: {e}")
            return []

    def create_work_package(
        self,
        project_slug: str,
        subject: str,
        description: str = None,
        wp_type: str = "Task",
        parent_id: int = None,
        priority_name: str = None,
    ) -> dict | None:
        """Create a new work package."""
        try:
            # Get the project to ensure it exists
            project = self.get_project(project_slug)
            if not project:
                print(f"ERROR: Project '{project_slug}' not found")
                return None

            # Get the type
            types = self.get_work_package_types(project_slug)
            type_obj = next((t for t in types if t.get("name") == wp_type), None)
            if not type_obj:
                print(f"ERROR: Work package type '{wp_type}' not found")
                print(f"Available types: {', '.join(t['name'] for t in types)}")
                return None

            payload = {"subject": subject, "_links": {"type": {"href": type_obj["_links"]["self"]["href"]}}}

            # Add optional fields
            if description:
                payload["description"] = {"format": "markdown", "raw": description}

            if parent_id:
                payload["_links"]["parent"] = {"href": f"/api/v3/work_packages/{parent_id}"}

            if priority_name:
                priorities = self.get_priorities()
                priority_obj = next((p for p in priorities if p.get("name") == priority_name), None)
                if priority_obj:
                    payload["_links"]["priority"] = {"href": priority_obj["_links"]["self"]["href"]}
                else:
                    print(f"WARNING: Priority '{priority_name}' not found, using default")

            response = self.session.post(
                f"{self.api_url}/projects/{project_slug}/work_packages",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"ERROR: Failed to create work package: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return None

    def update_work_package(
        self,
        work_package_id: int,
        status_name: str = None,
        assignee_name: str = None,
    ) -> dict | None:
        """Update a work package."""
        try:
            # First, get the current work package to get the lock version
            wp = self.get_work_package(work_package_id)
            if not wp:
                return None

            payload = {"lockVersion": wp.get("lockVersion", 0), "_links": {}}

            # Update status
            if status_name:
                statuses = self.get_statuses()
                status_obj = next((s for s in statuses if s.get("name") == status_name), None)
                if status_obj:
                    payload["_links"]["status"] = {"href": status_obj["_links"]["self"]["href"]}
                else:
                    print(f"ERROR: Status '{status_name}' not found")
                    print(f"Available statuses: {', '.join(s['name'] for s in statuses)}")
                    return None

            # Update assignee
            if assignee_name:
                users = self.get_users(assignee_name)
                if users:
                    # Use the first matching user
                    payload["_links"]["assignee"] = {"href": users[0]["_links"]["self"]["href"]}
                else:
                    print(f"ERROR: User '{assignee_name}' not found")
                    return None

            response = self.session.patch(
                f"{self.api_url}/work_packages/{work_package_id}",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"ERROR: Failed to update work package: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return None

    def add_comment(self, work_package_id: int, comment: str) -> dict | None:
        """Add a comment to a work package."""
        try:
            payload = {"comment": {"format": "markdown", "raw": comment}}

            response = self.session.post(
                f"{self.api_url}/work_packages/{work_package_id}/activities",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"ERROR: Failed to add comment: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return None


def format_markdown(wp: dict, activities: list[dict] = None) -> str:
    """Format work package as markdown for Claude."""
    subject = wp.get("subject", "Unknown")
    wp_id = wp.get("id", "?")
    wp_type = wp.get("_links", {}).get("type", {}).get("title", "Task")
    status = wp.get("_links", {}).get("status", {}).get("title", "Unknown")
    priority = wp.get("_links", {}).get("priority", {}).get("title", "Normal")
    assignee = wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned")

    description = wp.get("description", {})
    if isinstance(description, dict):
        description_text = description.get("raw", "No description")
    else:
        description_text = str(description) if description else "No description"

    created_at = wp.get("createdAt", "")
    updated_at = wp.get("updatedAt", "")

    output = f"""# {wp_type} #{wp_id}: {subject}

**Status:** {status}
**Priority:** {priority}
**Assignee:** {assignee}
**Created:** {created_at[:10] if created_at else 'N/A'}
**Updated:** {updated_at[:10] if updated_at else 'N/A'}

## Description

{description_text}
"""

    # Add comments if any
    if activities:
        comments = [a for a in activities if a.get("comment", {}).get("raw")]
        if comments:
            output += "\n## Comments\n\n"
            for activity in comments[-5:]:  # Last 5 comments
                comment = activity.get("comment", {}).get("raw", "")
                user = activity.get("_links", {}).get("user", {}).get("title", "Unknown")
                created = activity.get("createdAt", "")[:10]
                output += f"**{user}** ({created}):\n{comment}\n\n"

    return output


def format_work_package_short(wp: dict) -> str:
    """Format work package as a single line for list view."""
    wp_id = wp.get("id", "?")
    wp_type = wp.get("_links", {}).get("type", {}).get("title", "Task")
    status = wp.get("_links", {}).get("status", {}).get("title", "Unknown")
    assignee = wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned")
    subject = wp.get("subject", "Unknown")

    return f"#{wp_id:>4} [{wp_type:>10}] [{status:>12}] {assignee:>20} | {subject}"


def format_json_output(data: dict | list) -> str:
    """Format data as JSON."""
    return json.dumps(data, indent=2)


def cmd_get(args, client: OpenProjectClient):
    """Handle 'get' subcommand."""
    wp = client.get_work_package(args.id)
    if not wp:
        sys.exit(1)

    activities = client.get_work_package_activities(args.id)

    if args.json:
        output = {
            "id": wp.get("id"),
            "subject": wp.get("subject"),
            "type": wp.get("_links", {}).get("type", {}).get("title"),
            "status": wp.get("_links", {}).get("status", {}).get("title"),
            "priority": wp.get("_links", {}).get("priority", {}).get("title"),
            "assignee": wp.get("_links", {}).get("assignee", {}).get("title"),
            "description": wp.get("description", {}).get("raw", ""),
            "created_at": wp.get("createdAt"),
            "updated_at": wp.get("updatedAt"),
            "comments": [
                {
                    "user": a.get("_links", {}).get("user", {}).get("title"),
                    "date": a.get("createdAt"),
                    "text": a.get("comment", {}).get("raw"),
                }
                for a in activities
                if a.get("comment", {}).get("raw")
            ][-5:],
        }
        print(format_json_output(output))
    else:
        print(format_markdown(wp, activities))


def cmd_list(args, client: OpenProjectClient):
    """Handle 'list' subcommand."""
    wps = client.list_work_packages(
        project_slug=args.project,
        status=args.status,
        assignee=args.assignee,
        wp_type=args.type,
        parent_id=args.parent,
        limit=args.limit,
    )

    if not wps:
        print("No work packages found")
        return

    if args.json:
        output = [
            {
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "type": wp.get("_links", {}).get("type", {}).get("title"),
                "status": wp.get("_links", {}).get("status", {}).get("title"),
                "assignee": wp.get("_links", {}).get("assignee", {}).get("title"),
            }
            for wp in wps
        ]
        print(format_json_output(output))
    else:
        print(f"Found {len(wps)} work package(s):\n")
        for wp in wps:
            print(format_work_package_short(wp))


def cmd_search(args, client: OpenProjectClient):
    """Handle 'search' subcommand."""
    wps = client.search_work_packages(
        query=args.query,
        project_slug=args.project,
        limit=args.limit,
    )

    if not wps:
        print(f"No work packages found matching '{args.query}'")
        return

    if args.json:
        output = [
            {
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "type": wp.get("_links", {}).get("type", {}).get("title"),
                "status": wp.get("_links", {}).get("status", {}).get("title"),
                "assignee": wp.get("_links", {}).get("assignee", {}).get("title"),
            }
            for wp in wps
        ]
        print(format_json_output(output))
    else:
        print(f"Found {len(wps)} work package(s) matching '{args.query}':\n")
        for wp in wps:
            print(format_work_package_short(wp))


def cmd_create(args, client: OpenProjectClient):
    """Handle 'create' subcommand."""
    wp = client.create_work_package(
        project_slug=args.project,
        subject=args.subject,
        description=args.description,
        wp_type=args.type,
        parent_id=args.parent,
        priority_name=args.priority,
    )

    if not wp:
        sys.exit(1)

    wp_id = wp.get("id")
    print(f"Successfully created work package #{wp_id}: {args.subject}")
    print(f"View at: {client.base_url}/work_packages/{wp_id}")


def cmd_update(args, client: OpenProjectClient):
    """Handle 'update' subcommand."""
    # Update work package fields
    if args.status or args.assignee:
        wp = client.update_work_package(
            work_package_id=args.id,
            status_name=args.status,
            assignee_name=args.assignee,
        )

        if not wp:
            sys.exit(1)

        print(f"Successfully updated work package #{args.id}")

    # Add comment if provided
    if args.add_comment:
        result = client.add_comment(args.id, args.add_comment)
        if not result:
            sys.exit(1)
        print(f"Successfully added comment to work package #{args.id}")

    # Show updated work package
    wp = client.get_work_package(args.id)
    if wp:
        print()
        print(format_markdown(wp))


def main():
    parser = argparse.ArgumentParser(
        description="OpenProject task management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Create subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.required = True

    # 'get' subcommand
    parser_get = subparsers.add_parser("get", help="Get a single work package by ID")
    parser_get.add_argument("id", type=int, help="Work package ID")
    parser_get.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    # 'list' subcommand
    parser_list = subparsers.add_parser("list", help="List work packages with filters")
    parser_list.add_argument(
        "--project",
        default=None,
        help="Filter by project slug",
    )
    parser_list.add_argument(
        "--status",
        choices=["open", "closed", "all"],
        default="open",
        help="Filter by status (default: open)",
    )
    parser_list.add_argument(
        "--assignee",
        help="Filter by assignee name",
    )
    parser_list.add_argument(
        "--type",
        help="Filter by work package type (Task, Bug, Feature, Epic, etc.)",
    )
    parser_list.add_argument(
        "--parent",
        type=int,
        help="List children of a parent work package ID",
    )
    parser_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)",
    )
    parser_list.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    # 'search' subcommand
    parser_search = subparsers.add_parser("search", help="Search work packages by text")
    parser_search.add_argument("query", help="Search query")
    parser_search.add_argument(
        "--project",
        help="Filter by project slug",
    )
    parser_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)",
    )
    parser_search.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    # 'create' subcommand
    parser_create = subparsers.add_parser("create", help="Create a new work package")
    parser_create.add_argument(
        "--project",
        required=True,
        help="Project slug (required)",
    )
    parser_create.add_argument(
        "--subject",
        required=True,
        help="Work package subject/title (required)",
    )
    parser_create.add_argument(
        "--description",
        help="Work package description (markdown)",
    )
    parser_create.add_argument(
        "--type",
        default="Task",
        help="Work package type (default: Task)",
    )
    parser_create.add_argument(
        "--parent",
        type=int,
        help="Parent work package ID",
    )
    parser_create.add_argument(
        "--priority",
        help="Priority name (e.g., Normal, High, Immediate)",
    )

    # 'update' subcommand
    parser_update = subparsers.add_parser("update", help="Update a work package")
    parser_update.add_argument("id", type=int, help="Work package ID")
    parser_update.add_argument(
        "--status",
        help="Change status",
    )
    parser_update.add_argument(
        "--assignee",
        help="Assign to user (name)",
    )
    parser_update.add_argument(
        "--add-comment",
        help="Add a comment (markdown)",
    )

    args = parser.parse_args()

    # Check for API token
    api_token = os.environ.get("OPENPROJECT_API_TOKEN")
    if not api_token:
        print("ERROR: OPENPROJECT_API_TOKEN environment variable is required")
        print("Get your API token from: OpenProject > My Account > Access tokens")
        print()
        print("Set it with:")
        print("  export OPENPROJECT_API_TOKEN='your-token-here'")
        sys.exit(1)

    base_url = os.environ.get("OPENPROJECT_URL", DEFAULT_OPENPROJECT_URL)

    # Create client
    client = OpenProjectClient(base_url, api_token)

    # Dispatch to command handler
    if args.command == "get":
        cmd_get(args, client)
    elif args.command == "list":
        cmd_list(args, client)
    elif args.command == "search":
        cmd_search(args, client)
    elif args.command == "create":
        cmd_create(args, client)
    elif args.command == "update":
        cmd_update(args, client)


if __name__ == "__main__":
    main()
