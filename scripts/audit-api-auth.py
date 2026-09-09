#!/usr/bin/env python3
"""Audit FastAPI router files for missing authentication dependencies.

Scans all router files in the codebase and verifies that every endpoint
function has an authentication dependency in its signature. Endpoints
that are intentionally public must be listed in the ALLOWED_PUBLIC
allowlist below.

Usage:
    python scripts/audit-api-auth.py              # Audit all routers
    python scripts/audit-api-auth.py --strict      # Exit 1 on any finding
    python scripts/audit-api-auth.py --json        # Output as JSON
    python scripts/audit-api-auth.py --verbose     # Show all endpoints

Exit codes:
    0 - All endpoints have auth or are allowlisted
    1 - Found endpoints missing auth (--strict mode)
"""

import ast
import glob
import json as json_mod
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Auth dependency names that count as "authenticated"
AUTH_DEPENDENCIES = {
    "get_authenticated_client",
    "get_current_client",
    "verify_request_signature",
    "verify_bearer_token",
}

# Decorator names that indicate a FastAPI route
ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options"}

# Endpoints that are intentionally public.
# Format: (module_dir, router_file_basename, function_name)
# Keep this list small and review changes carefully.
ALLOWED_PUBLIC = {
    # Format: (module_dir, router_file_basename, function_name)
    # Use "*" for function_name to allow all functions in a file.
    # Keep this list small and review changes carefully.
    #
    # Example:
    # ("trn_api", "oauth.py", "get_token"),  # OAuth token endpoint - public by design
    # ("fastapi", "demo_router.py", "*"),  # FastAPI demo router (development only)
}


# ---------------------------------------------------------------------------
# AST Analysis
# ---------------------------------------------------------------------------


def find_router_files(root_dir):
    """Find all Python files in routers/ directories."""
    patterns = [
        os.path.join(root_dir, "*/routers/*.py"),
        os.path.join(root_dir, "*/routers/**/*.py"),
    ]
    files = set()
    for pattern in patterns:
        for f in glob.glob(pattern, recursive=True):
            if not f.endswith("__init__.py") and not f.endswith("__pycache__"):
                files.add(f)
    return sorted(files)


def get_module_dir(filepath, root_dir):
    """Extract the module directory name from a file path."""
    rel = os.path.relpath(filepath, root_dir)
    return rel.split(os.sep)[0]


def is_route_decorator(node):
    """Check if an AST node is a FastAPI route decorator."""
    if isinstance(node, ast.Call):
        func = node.func
        # router.get(...), router.post(...), etc.
        if isinstance(func, ast.Attribute) and func.attr in ROUTE_DECORATORS:
            return True
    return False


def get_route_info(decorator_node):
    """Extract HTTP method and path from a route decorator."""
    if isinstance(decorator_node, ast.Call):
        func = decorator_node.func
        method = func.attr.upper() if isinstance(func, ast.Attribute) else "UNKNOWN"
        path = ""
        if decorator_node.args:
            arg = decorator_node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                path = arg.value
        return method, path
    return "UNKNOWN", ""


def _ast_contains_auth_name(node):
    """Check if an AST subtree contains any AUTH_DEPENDENCIES reference."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in AUTH_DEPENDENCIES:
            return True
        if isinstance(child, ast.Attribute) and child.attr in AUTH_DEPENDENCIES:
            return True
    return False


def has_auth_dependency(func_node, decorator_node=None):
    """Check if a function has an auth dependency.

    Checks both:
    1. Function parameters (Annotated[..., Depends(auth_func)] or default=Depends(auth_func))
    2. Decorator-level dependencies=[Depends(auth_func)]
    """
    # Check function parameter annotations
    for arg in func_node.args.args:
        annotation = arg.annotation
        if annotation is not None and _ast_contains_auth_name(annotation):
            return True

    # Check defaults (some use Depends(get_authenticated_client) as default)
    all_defaults = func_node.args.defaults + func_node.args.kw_defaults
    for default in all_defaults:
        if default is not None and _ast_contains_auth_name(default):
            return True

    # Check decorator-level dependencies=[Depends(auth_func)]
    if decorator_node and isinstance(decorator_node, ast.Call):
        for keyword in decorator_node.keywords:
            if keyword.arg == "dependencies" and _ast_contains_auth_name(keyword.value):
                return True

    return False


def is_allowed_public(module_dir, filename, func_name):
    """Check if an endpoint is in the allowed public list."""
    basename = os.path.basename(filename)
    # Check exact match
    if (module_dir, basename, func_name) in ALLOWED_PUBLIC:
        return True
    # Check wildcard match (all functions in file)
    if (module_dir, basename, "*") in ALLOWED_PUBLIC:
        return True
    return False


def analyze_file(filepath, root_dir):
    """Analyze a single router file for missing auth.

    Returns list of findings: (module, file, func, method, path, has_auth, is_allowed)
    """
    module_dir = get_module_dir(filepath, root_dir)
    findings = []

    try:
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        print(f"WARNING: Could not parse {filepath}: {e}", file=sys.stderr)
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        # Check if this function has route decorators
        for decorator in node.decorator_list:
            if not is_route_decorator(decorator):
                continue

            method, path = get_route_info(decorator)
            auth = has_auth_dependency(node, decorator)
            allowed = is_allowed_public(module_dir, filepath, node.name)

            findings.append(
                {
                    "module": module_dir,
                    "file": os.path.relpath(filepath, root_dir),
                    "function": node.name,
                    "method": method,
                    "path": path,
                    "has_auth": auth,
                    "is_allowed_public": allowed,
                    "line": node.lineno,
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    verbose = "--verbose" in sys.argv
    strict = "--strict" in sys.argv
    output_json = "--json" in sys.argv

    root_dir = Path(__file__).resolve().parent.parent

    router_files = find_router_files(root_dir)

    all_findings = []
    for filepath in router_files:
        all_findings.extend(analyze_file(filepath, root_dir))

    # Separate into categories
    protected = [f for f in all_findings if f["has_auth"]]
    public_allowed = [f for f in all_findings if not f["has_auth"] and f["is_allowed_public"]]
    missing_auth = [f for f in all_findings if not f["has_auth"] and not f["is_allowed_public"]]

    if output_json:
        result = {
            "summary": {
                "total_endpoints": len(all_findings),
                "protected": len(protected),
                "public_allowed": len(public_allowed),
                "missing_auth": len(missing_auth),
            },
            "missing_auth": missing_auth,
            "public_allowed": public_allowed,
        }
        print(json_mod.dumps(result, indent=2))
    else:
        print(f"\n{'=' * 70}")
        print("  API Authentication Audit")
        print(f"{'=' * 70}")
        print(f"  Router files scanned:  {len(router_files)}")
        print(f"  Total endpoints found: {len(all_findings)}")
        print(f"  Protected (auth):      {len(protected)}")
        print(f"  Public (allowlisted):  {len(public_allowed)}")
        print(f"  MISSING AUTH:          {len(missing_auth)}")
        print(f"{'=' * 70}\n")

        if missing_auth:
            print("ENDPOINTS MISSING AUTHENTICATION:")
            print("-" * 70)
            for f in missing_auth:
                print(f"  {f['method']:6s} {f['path']:40s} {f['file']}:{f['line']}")
                print(f"         function: {f['function']}")
            print()
            print("FIX: Add Depends(get_authenticated_client) to these endpoints,")
            print("     or add them to ALLOWED_PUBLIC in this script if intentionally public.")
            print()

        if verbose:
            print("\nPROTECTED ENDPOINTS:")
            print("-" * 70)
            for f in protected:
                print(f"  {f['method']:6s} {f['path']:40s} {f['file']}:{f['line']}")

            print("\nPUBLIC (ALLOWLISTED) ENDPOINTS:")
            print("-" * 70)
            for f in public_allowed:
                print(f"  {f['method']:6s} {f['path']:40s} {f['file']}:{f['line']}")

        if not missing_auth:
            print("All endpoints have authentication or are explicitly allowlisted.")

    if strict and missing_auth:
        sys.exit(1)


if __name__ == "__main__":
    main()
