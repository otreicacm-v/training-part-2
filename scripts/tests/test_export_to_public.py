"""Tests for the public repo export script."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def source_dir(tmp_path):
    """Create a fake source repo with a few modules and config."""
    src = tmp_path / "source"
    src.mkdir()

    # Create a minimal export_config.toml
    config = src / "scripts" / "export_config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        textwrap.dedent("""\
        [export]
        modules = ["mod_a", "mod_b"]
        extra_directories = ["extra_pkg"]
        root_files = ["LICENSE", "requirements.txt"]
        docker_directory = "docker"

        [external_dependencies]
        [external_dependencies.repos]
        "OCA/queue" = { branch = "19.0", modules = ["queue_job"] }
    """)
    )

    # Create module directories with manifests
    for mod_name, deps in [("mod_a", ["base"]), ("mod_b", ["mod_a", "queue_job"])]:
        mod_dir = src / mod_name
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("")
        (mod_dir / "__manifest__.py").write_text(f'{{"name": "{mod_name}", "depends": {deps!r}, "installable": True}}')

    # Create extra directory
    extra = src / "extra_pkg"
    extra.mkdir()
    (extra / "__init__.py").write_text("")
    (extra / "data.csv").write_text("a,b\n1,2\n")

    # Create root files
    (src / "LICENSE").write_text("LGPL-3")
    (src / "requirements.txt").write_text("odoo>=19\n")

    # Create docker directory
    docker = src / "docker"
    docker.mkdir()
    (docker / "Dockerfile").write_text("FROM odoo:19\n")
    (docker / "entrypoint.sh").write_text("#!/bin/bash\n")

    # Create a private module that should NOT be exported
    private = src / "mod_private"
    private.mkdir()
    (private / "__init__.py").write_text("")
    (private / "__manifest__.py").write_text('{"name": "Private", "depends": ["base"], "installable": True}')

    return src


@pytest.fixture
def source_with_scripts(source_dir):
    """Source dir with scripts_files, extra_subdirectories, and dotfiles configured."""
    # Add a scripts file to the source
    scripts_dir = source_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "test_single_module.sh").write_text("#!/bin/bash\necho test\n")

    # Add subdirectories under scripts/
    lint_dir = scripts_dir / "lint"
    lint_dir.mkdir()
    (lint_dir / "__init__.py").write_text("")
    (lint_dir / "check_naming.py").write_text("# naming check\n")

    compliance_dir = scripts_dir / "compliance"
    compliance_dir.mkdir()
    (compliance_dir / "__init__.py").write_text("")
    (compliance_dir / "checker.py").write_text("# compliance checker\n")

    # Update the config to include scripts_files, extra_subdirectories, and dotfiles
    config = source_dir / "scripts" / "export_config.toml"
    config.write_text(
        textwrap.dedent("""\
        [export]
        modules = ["mod_a", "mod_b"]
        extra_directories = ["extra_pkg"]
        extra_subdirectories = ["scripts/lint", "scripts/compliance"]
        root_files = ["LICENSE", "requirements.txt", ".gitignore", "odools"]
        scripts_files = ["scripts/test_single_module.sh"]
        docker_directory = "docker"

        [external_dependencies]
        [external_dependencies.repos]
        "OCA/queue" = { branch = "19.0", modules = ["queue_job"] }
    """)
    )

    # Create the dotfile and CLI script
    (source_dir / ".gitignore").write_text("*.pyc\n__pycache__/\n")
    (source_dir / "odools").write_text("#!/usr/bin/env python3\nprint('odoo cli')\n")

    return source_dir


@pytest.fixture
def target_dir(tmp_path):
    """Create an empty target directory."""
    tgt = tmp_path / "target"
    tgt.mkdir()
    return tgt


@pytest.fixture
def target_with_git(target_dir):
    """Target directory that has a .git folder (simulates existing repo)."""
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    return target_dir


# ---------------------------------------------------------------------------
# Unit tests: config loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_modules_list(self, source_dir):
        from export_to_public import load_config

        config = load_config(source_dir / "scripts" / "export_config.toml")
        assert config["export"]["modules"] == ["mod_a", "mod_b"]

    def test_loads_extra_directories(self, source_dir):
        from export_to_public import load_config

        config = load_config(source_dir / "scripts" / "export_config.toml")
        assert config["export"]["extra_directories"] == ["extra_pkg"]

    def test_loads_root_files(self, source_dir):
        from export_to_public import load_config

        config = load_config(source_dir / "scripts" / "export_config.toml")
        assert config["export"]["root_files"] == ["LICENSE", "requirements.txt"]

    def test_loads_external_deps(self, source_dir):
        from export_to_public import load_config

        config = load_config(source_dir / "scripts" / "export_config.toml")
        repos = config["external_dependencies"]["repos"]
        assert "OCA/queue" in repos
        assert repos["OCA/queue"]["modules"] == ["queue_job"]

    def test_missing_config_raises(self, tmp_path):
        from export_to_public import load_config

        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")


# ---------------------------------------------------------------------------
# Unit tests: manifest parsing
# ---------------------------------------------------------------------------


class TestParseManifest:
    def test_reads_depends(self, source_dir):
        from export_to_public import parse_manifest

        manifest = parse_manifest(source_dir / "mod_a" / "__manifest__.py")
        assert manifest["depends"] == ["base"]

    def test_reads_name(self, source_dir):
        from export_to_public import parse_manifest

        manifest = parse_manifest(source_dir / "mod_b" / "__manifest__.py")
        assert manifest["name"] == "mod_b"

    def test_missing_manifest_raises(self, tmp_path):
        from export_to_public import parse_manifest

        with pytest.raises(FileNotFoundError):
            parse_manifest(tmp_path / "missing" / "__manifest__.py")


# ---------------------------------------------------------------------------
# Unit tests: dependency validation
# ---------------------------------------------------------------------------


class TestValidateDependencies:
    def test_valid_deps_pass(self, source_dir):
        from export_to_public import load_config, validate_dependencies

        config = load_config(source_dir / "scripts" / "export_config.toml")
        # Should not raise
        missing = validate_dependencies(source_dir, config)
        assert missing == {}

    def test_missing_dep_detected(self, source_dir):
        from export_to_public import load_config, validate_dependencies

        # Rewrite mod_b to depend on something not exported and not external
        (source_dir / "mod_b" / "__manifest__.py").write_text(
            '{"name": "mod_b", "depends": ["mod_a", "missing_module"], "installable": True}'
        )
        config = load_config(source_dir / "scripts" / "export_config.toml")
        missing = validate_dependencies(source_dir, config)
        assert "mod_b" in missing
        assert "missing_module" in missing["mod_b"]


# ---------------------------------------------------------------------------
# Integration tests: full export
# ---------------------------------------------------------------------------


class TestExportIntegration:
    def test_exports_modules(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert (target_dir / "mod_a" / "__manifest__.py").exists()
        assert (target_dir / "mod_b" / "__manifest__.py").exists()

    def test_exports_extra_directories(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert (target_dir / "extra_pkg" / "__init__.py").exists()
        assert (target_dir / "extra_pkg" / "data.csv").exists()

    def test_exports_root_files(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert (target_dir / "LICENSE").exists()
        assert (target_dir / "requirements.txt").exists()

    def test_exports_docker_directory(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert (target_dir / "docker" / "Dockerfile").exists()
        assert (target_dir / "docker" / "entrypoint.sh").exists()

    def test_private_module_not_exported(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert not (target_dir / "mod_private").exists()

    def test_preserves_git_directory(self, source_dir, target_with_git):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_with_git, config)

        assert (target_with_git / ".git" / "HEAD").exists()

    def test_cleans_stale_directories(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        # Pre-populate target with a stale module
        stale = target_dir / "old_module"
        stale.mkdir()
        (stale / "old_file.py").write_text("stale")

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert not (target_dir / "old_module").exists()

    def test_generates_readme(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        readme = target_dir / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert "Odoo" in content
        assert "docker" in content.lower()

    def test_generates_external_dependencies_doc(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        ext_deps = target_dir / "EXTERNAL_DEPENDENCIES.md"
        assert ext_deps.exists()
        content = ext_deps.read_text()
        assert "OCA/queue" in content
        assert "queue_job" in content

    def test_skips_pycache(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        # Add __pycache__ to a module
        pycache = source_dir / "mod_a" / "__pycache__"
        pycache.mkdir()
        (pycache / "mod_a.cpython-311.pyc").write_bytes(b"\x00")

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)

        assert not (target_dir / "mod_a" / "__pycache__").exists()

    def test_idempotent_export(self, source_dir, target_dir):
        """Running export twice produces identical results."""
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config)
        run_export(source_dir, target_dir, config)

        assert (target_dir / "mod_a" / "__manifest__.py").exists()
        assert (target_dir / "mod_b" / "__manifest__.py").exists()
        assert not (target_dir / "mod_private").exists()


# ---------------------------------------------------------------------------
# Integration tests: scripts_files and dotfiles
# ---------------------------------------------------------------------------


class TestScriptsFilesExport:
    def test_exports_scripts_files(self, source_with_scripts, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / "scripts" / "test_single_module.sh").exists()
        content = (target_dir / "scripts" / "test_single_module.sh").read_text()
        assert "echo test" in content

    def test_exports_dotfiles_as_root_files(self, source_with_scripts, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / ".gitignore").exists()
        content = (target_dir / ".gitignore").read_text()
        assert "*.pyc" in content

    def test_exports_cli_script(self, source_with_scripts, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / "odools").exists()

    def test_scripts_files_creates_parent_dirs(self, source_with_scripts, target_dir):
        """scripts_files should create intermediate directories."""
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / "scripts").is_dir()

    def test_missing_scripts_file_warns(self, source_with_scripts, target_dir):
        """Missing scripts_files should warn but not fail."""
        from export_to_public import load_config, run_export

        # Add a nonexistent file to the config
        config_path = source_with_scripts / "scripts" / "export_config.toml"
        config_text = config_path.read_text()
        config_text = config_text.replace(
            'scripts_files = ["scripts/test_single_module.sh"]',
            'scripts_files = ["scripts/test_single_module.sh", "scripts/nonexistent.sh"]',
        )
        config_path.write_text(config_text)

        config = load_config(config_path)
        # Should not raise
        run_export(source_with_scripts, target_dir, config)
        assert (target_dir / "scripts" / "test_single_module.sh").exists()
        assert not (target_dir / "scripts" / "nonexistent.sh").exists()

    def test_dotfiles_preserved_during_clean(self, source_with_scripts, target_dir):
        """Dotfiles in root_files should not be cleaned as stale."""
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")

        # Run export twice — dotfiles should survive the clean pass
        run_export(source_with_scripts, target_dir, config)
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / ".gitignore").exists()

    def test_exports_extra_subdirectories(self, source_with_scripts, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / "scripts" / "lint" / "check_naming.py").exists()
        assert (target_dir / "scripts" / "lint" / "__init__.py").exists()
        assert (target_dir / "scripts" / "compliance" / "checker.py").exists()
        assert (target_dir / "scripts" / "compliance" / "__init__.py").exists()

    def test_extra_subdirectories_idempotent(self, source_with_scripts, target_dir):
        """Running export twice with extra_subdirectories works correctly."""
        from export_to_public import load_config, run_export

        config = load_config(source_with_scripts / "scripts" / "export_config.toml")
        run_export(source_with_scripts, target_dir, config)
        run_export(source_with_scripts, target_dir, config)

        assert (target_dir / "scripts" / "lint" / "check_naming.py").exists()
        assert (target_dir / "scripts" / "compliance" / "checker.py").exists()


# ---------------------------------------------------------------------------
# Integration tests: dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_copy(self, source_dir, target_dir):
        from export_to_public import load_config, run_export

        config = load_config(source_dir / "scripts" / "export_config.toml")
        run_export(source_dir, target_dir, config, dry_run=True)

        # Target should remain empty (no modules copied)
        entries = list(target_dir.iterdir())
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# End-to-end tests: CLI interface
# ---------------------------------------------------------------------------


class TestCLI:
    def test_dry_run_flag(self, source_dir, target_dir):
        """Test the script can be invoked with --dry-run."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "export_to_public.py"),
                str(target_dir),
                "--dry-run",
                "--source",
                str(source_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        combined = result.stdout + result.stderr
        assert "DRY RUN" in combined or "dry run" in combined.lower()

    def test_validate_only_flag(self, source_dir, target_dir):
        """Test the script can be invoked with --validate-only."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "export_to_public.py"),
                str(target_dir),
                "--validate-only",
                "--source",
                str(source_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_validate_only_fails_on_missing_deps(self, source_dir, target_dir):
        """--validate-only exits non-zero when deps are missing."""
        # Break a dependency
        (source_dir / "mod_b" / "__manifest__.py").write_text(
            '{"name": "mod_b", "depends": ["nonexistent"], "installable": True}'
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "export_to_public.py"),
                str(target_dir),
                "--validate-only",
                "--source",
                str(source_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_full_export_via_cli(self, source_dir, target_dir):
        """Full export produces expected output."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "export_to_public.py"),
                str(target_dir),
                "--source",
                str(source_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (target_dir / "mod_a" / "__manifest__.py").exists()
        assert (target_dir / "mod_b" / "__manifest__.py").exists()
        assert (target_dir / "README.md").exists()
        assert (target_dir / "EXTERNAL_DEPENDENCIES.md").exists()
