#!/usr/bin/env python3
"""Export curated Odoo modules to a public repository.

Usage:
    python scripts/export_to_public.py /path/to/public-repo          # Full export
    python scripts/export_to_public.py /path/to/public-repo --dry-run # Preview
    python scripts/export_to_public.py /path/to/public-repo --validate-only  # Check deps
"""

import argparse
import ast
import logging
import re
import shutil
import sys
import textwrap
import tomllib
from pathlib import Path

logger = logging.getLogger("export_to_public")

# Directories and files to skip when copying
SKIP_PATTERNS = {"__pycache__", ".pyc", ".pyo"}

# File patterns to exclude from export (sensitive/internal files)
EXCLUDED_FILES = set()

# Odoo core modules that are always available.
# Generated from Odoo 19 source — covers all standard addons.
ODOO_CORE_MODULES = frozenset(
    {
        # Base / framework
        "base",
        "base_import",
        "base_setup",
        "bus",
        "web",
        # Communication
        "mail",
        "sms",
        "fetchmail",
        "digest",
        "mass_mailing",
        # Portal / auth
        "portal",
        "auth_signup",
        "auth_totp",
        # Core business
        "contacts",
        "phone_validation",
        "account",
        "sale",
        "purchase",
        "stock",
        "product",
        "product_expiry",
        "uom",
        "hr",
        "resource",
        # CRM / marketing
        "crm",
        "utm",
        "link_tracker",
        # Project / services
        "project",
        "calendar",
        "event",
        "survey",
        # Manufacturing / logistics
        "mrp",
        "repair",
        "fleet",
        "maintenance",
        # Other standard addons
        "board",
        "note",
        "lunch",
        "iap",
        "website",
        "point_of_sale",
        "base_geolocalize",
        # Spreadsheet / docs
        "spreadsheet",
        "spreadsheet_dashboard",
        "documents",
        "documents_spreadsheet",
        # Odoo 19 additions commonly referenced
        "base_import_module",
        "payment",
        "delivery",
        "l10n_generic_coa",
        "analytic",
        "account_payment",
        "account_check_printing",
    }
)


def load_config(config_path: Path) -> dict:
    """Load the TOML export configuration file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def parse_manifest(manifest_path: Path) -> dict:
    """Parse an Odoo __manifest__.py file using AST (safe eval)."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    source = manifest_path.read_text()
    tree = ast.parse(source, filename=str(manifest_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Dict):
            return ast.literal_eval(node.value)
    raise ValueError(f"No dict found in manifest: {manifest_path}")


def get_external_module_names(config: dict) -> set[str]:
    """Collect all module names declared as external dependencies."""
    external = set()
    repos = config.get("external_dependencies", {}).get("repos", {})
    for _repo, info in repos.items():
        for mod in info.get("modules", []):
            external.add(mod)
    return external


def validate_dependencies(source_dir: Path, config: dict) -> dict[str, list[str]]:
    """Check that every exported module's depends are satisfied.

    Returns a dict mapping module_name -> [list of missing deps].
    Empty dict means all deps are satisfied.
    """
    export_cfg = config["export"]
    exported_modules = set(export_cfg["modules"])
    external_modules = get_external_module_names(config)
    allowed = exported_modules | external_modules | ODOO_CORE_MODULES

    missing = {}
    for mod_name in export_cfg["modules"]:
        manifest_path = source_dir / mod_name / "__manifest__.py"
        if not manifest_path.exists():
            logger.warning("Module %s has no __manifest__.py", mod_name)
            continue
        manifest = parse_manifest(manifest_path)
        deps = manifest.get("depends", [])
        unresolved = [d for d in deps if d not in allowed]
        if unresolved:
            missing[mod_name] = unresolved

    return missing


def _should_skip(name: str) -> bool:
    """Check if a file/directory name should be skipped during copy."""
    return name in SKIP_PATTERNS or name.endswith((".pyc", ".pyo"))


def _copy_directory(src: Path, dst: Path) -> None:
    """Copy a directory, skipping __pycache__, .pyc files, and excluded files."""
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", *EXCLUDED_FILES),
    )


def _clean_target(target_dir: Path, expected_entries: set[str]) -> None:
    """Remove entries from target that are not in the expected set.

    Preserves .git/ and any dotfiles/dotdirs.
    """
    if not target_dir.exists():
        return
    for entry in target_dir.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.name not in expected_entries:
            logger.info("Removing stale: %s", entry.name)
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()


def _generate_readme(target_dir: Path, config: dict) -> None:
    """Generate a README.md for the public repo."""
    modules = config["export"]["modules"]
    readme = textwrap.dedent("""\
        # Odoo Project

        Open-source modules built on [Odoo 19](https://www.odoo.com/).

        ## Quick Start

        ```bash
        # Clone this repository
        git clone https://github.com/your-org/odoo-project.git
        cd odoo-project

        # Start with Docker Compose
        docker compose --profile ui up -d

        # Access at http://localhost:8069 (admin/admin)
        ```

        ## External Dependencies

        This repository requires additional OCA and third-party modules.
        See [EXTERNAL_DEPENDENCIES.md](EXTERNAL_DEPENDENCIES.md) for details.
        The Docker setup handles these automatically.

        ## Modules

        This repository contains {module_count} Odoo modules:

        {module_list}

        ## License

        LGPL-3. See [LICENSE](LICENSE) for details.
    """).format(
        module_count=len(modules),
        module_list="\n".join(f"- `{m}`" for m in sorted(modules)),
    )
    (target_dir / "README.md").write_text(readme)


def _generate_external_deps_doc(target_dir: Path, config: dict) -> None:
    """Generate EXTERNAL_DEPENDENCIES.md documenting required OCA repos."""
    repos = config.get("external_dependencies", {}).get("repos", {})
    if not repos:
        return

    lines = [
        "# External Dependencies",
        "",
        "This project requires the following external Odoo module repositories.",
        "The Docker setup fetches these automatically. For manual installation,",
        "clone each repo and add it to your Odoo addons path.",
        "",
        "| Repository | Branch | Modules |",
        "|------------|--------|---------|",
    ]
    for repo, info in sorted(repos.items()):
        branch = info.get("branch", "19.0")
        mods = ", ".join(f"`{m}`" for m in info.get("modules", []))
        lines.append(f"| [{repo}](https://github.com/{repo}) | {branch} | {mods} |")

    lines.append("")
    (target_dir / "EXTERNAL_DEPENDENCIES.md").write_text("\n".join(lines))


# Workflows to exclude from public export (internal/team-specific)
EXCLUDED_WORKFLOWS = {
    "auto-assign-pr.yml",
    "auto-assign.yml",
    "build-env-cache.yml",
    "ci-full.yml",
    "ci-integration.yml",
    "cla.yml",
    "test-pypi.yml",
    "test.yml.disabled",
}


def _transform_workflows(target_dir: Path) -> None:
    """Transform GitHub workflows for public GitHub-hosted runners.

    - Changes self-hosted runners to ubuntu-latest
    - Removes Docker registry mirror config (internal infrastructure)
    - Adds Node.js setup to pre-commit workflow
    - Removes excluded workflows
    """
    workflows_dir = target_dir / ".github" / "workflows"
    if not workflows_dir.exists():
        return

    # Remove excluded workflows
    for workflow in EXCLUDED_WORKFLOWS:
        workflow_path = workflows_dir / workflow
        if workflow_path.exists():
            workflow_path.unlink()
            logger.info("Removed excluded workflow: %s", workflow)

    # Transform remaining workflows
    for workflow_path in workflows_dir.glob("*.yml"):
        content = workflow_path.read_text()
        original_content = content

        # Replace self-hosted runner with ubuntu-latest
        content = re.sub(
            r"runs-on:\s*\[self-hosted,\s*linux,\s*x64,\s*[a-z0-9_-]+\]",
            "runs-on: ubuntu-latest",
            content,
        )

        # Remove buildkitd-config-inline sections (Docker registry mirror config)
        # This removes the entire 'with:' block containing buildkitd-config-inline
        content = re.sub(
            r"(\s+- name: Set up Docker Buildx\n"
            r"\s+uses: docker/setup-buildx-action@v3\n)"
            r"\s+with:\n"
            r"\s+buildkitd-config-inline: \|[\s\S]*?(?=\n\s+-|\n\s+\n|\Z)",
            r"\1",
            content,
        )

        # Add Node.js setup to pre-commit workflow
        if workflow_path.name == "pre-commit.yml":
            # Add Node.js setup after Python setup
            if "setup-node" not in content:
                content = re.sub(
                    r"(- uses: actions/setup-python@v\d+\n\s+with:\n\s+python-version:.*\n)",
                    r"\1      - name: Setup Node.js\n"
                    r"        uses: actions/setup-node@v4\n"
                    r"        with:\n"
                    r"          node-version: '22'\n",
                    content,
                )

        if content != original_content:
            workflow_path.write_text(content)
            logger.info("Transformed workflow: %s", workflow_path.name)


def _update_precommit_config(target_dir: Path) -> None:
    """Update .pre-commit-config.yaml repo references for the public repo."""
    precommit_path = target_dir / ".pre-commit-config.yaml"
    if not precommit_path.exists():
        return

    content = precommit_path.read_text()
    original_content = content

    if content != original_content:
        precommit_path.write_text(content)
        logger.info("Updated .pre-commit-config.yaml repo references")


def run_export(
    source_dir: Path,
    target_dir: Path,
    config: dict,
    *,
    dry_run: bool = False,
) -> None:
    """Execute the export from source to target directory."""
    export_cfg = config["export"]
    modules = export_cfg["modules"]
    extra_dirs = export_cfg.get("extra_directories", [])
    extra_subdirs = export_cfg.get("extra_subdirectories", [])
    root_files = export_cfg.get("root_files", [])
    scripts_files = export_cfg.get("scripts_files", [])
    docker_dir = export_cfg.get("docker_directory")

    # Build set of expected entries in target (top-level names only)
    expected = set(modules) | set(extra_dirs) | set(root_files) | {"README.md", "EXTERNAL_DEPENDENCIES.md"}
    if docker_dir:
        expected.add(docker_dir)
    # Add top-level directories from nested paths
    for sf in scripts_files:
        expected.add(Path(sf).parts[0])
    for sd in extra_subdirs:
        expected.add(Path(sd).parts[0])

    if dry_run:
        logger.info("=== DRY RUN - no files will be modified ===")
        logger.info("Modules to export (%d):", len(modules))
        for mod in sorted(modules):
            exists = (source_dir / mod / "__manifest__.py").exists()
            status = "OK" if exists else "MISSING"
            logger.info("  %s [%s]", mod, status)
        logger.info("Extra directories: %s", extra_dirs)
        logger.info("Extra subdirectories: %s", extra_subdirs)
        logger.info("Root files: %s", root_files)
        logger.info("Scripts files: %s", scripts_files)
        logger.info("Docker directory: %s", docker_dir)
        return

    # Ensure target exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale entries
    _clean_target(target_dir, expected)

    # Copy modules
    for mod in modules:
        src = source_dir / mod
        dst = target_dir / mod
        if not src.exists():
            logger.warning("Source module not found: %s", mod)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        _copy_directory(src, dst)
        logger.info("Exported module: %s", mod)

    # Copy extra directories
    for extra in extra_dirs:
        src = source_dir / extra
        dst = target_dir / extra
        if not src.exists():
            logger.warning("Extra directory not found: %s", extra)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        _copy_directory(src, dst)
        logger.info("Exported directory: %s", extra)

    # Copy extra subdirectories (nested paths like "scripts/lint")
    for subdir in extra_subdirs:
        src = source_dir / subdir
        dst = target_dir / subdir
        if not src.exists():
            logger.warning("Extra subdirectory not found: %s", subdir)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        _copy_directory(src, dst)
        logger.info("Exported subdirectory: %s", subdir)

    # Copy root files
    for filename in root_files:
        src = source_dir / filename
        dst = target_dir / filename
        if not src.exists():
            logger.warning("Root file not found: %s", filename)
            continue
        shutil.copy2(src, dst)
        logger.info("Exported file: %s", filename)

    # Copy individual files from subdirectories (scripts_files)
    for filepath in scripts_files:
        src = source_dir / filepath
        dst = target_dir / filepath
        if not src.exists():
            logger.warning("Scripts file not found: %s", filepath)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info("Exported file: %s", filepath)

    # Copy docker directory
    if docker_dir:
        src = source_dir / docker_dir
        dst = target_dir / docker_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            _copy_directory(src, dst)
            logger.info("Exported docker directory: %s", docker_dir)
        else:
            logger.warning("Docker directory not found: %s", docker_dir)

    # Generate documentation
    _generate_readme(target_dir, config)
    _generate_external_deps_doc(target_dir, config)
    logger.info("Generated README.md and EXTERNAL_DEPENDENCIES.md")

    # Post-processing for public repo
    _transform_workflows(target_dir)
    _update_precommit_config(target_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export custom Odoo modules to a public repository.")
    parser.add_argument("target", help="Path to the target (public) repository")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be exported without making changes",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate dependencies, don't export",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Source directory (defaults to repo root, two levels up from this script)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to export_config.toml (defaults to scripts/export_config.toml)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Resolve source directory
    if args.source:
        source_dir = Path(args.source).resolve()
    else:
        source_dir = Path(__file__).resolve().parent.parent

    # Resolve config path
    if args.config:
        config_path = Path(args.config).resolve()
    else:
        config_path = source_dir / "scripts" / "export_config.toml"

    target_dir = Path(args.target).resolve()

    # Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    # Validate dependencies
    missing = validate_dependencies(source_dir, config)
    if missing:
        logger.error("Missing dependencies detected:")
        for mod, deps in sorted(missing.items()):
            logger.error("  %s depends on: %s", mod, ", ".join(deps))
        if args.validate_only:
            return 1
        logger.error("Continuing with export despite missing dependencies.")

    if args.validate_only:
        logger.info("All dependencies validated successfully.")
        return 0

    # Run export
    run_export(source_dir, target_dir, config, dry_run=args.dry_run)

    if args.dry_run:
        logger.info("Dry run complete. No files were modified.")
    else:
        module_count = len(config["export"]["modules"])
        logger.info("Export complete: %d modules to %s", module_count, target_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
