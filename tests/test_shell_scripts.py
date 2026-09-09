"""Tests for security scanning shell scripts.

Validates argument handling, syntax, and basic error paths
without requiring Docker or external tools.

Detection tests (marked @pytest.mark.slow) verify that tools
actually find real vulnerabilities in synthetic test files.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def run_script(script_path, args=None, env=None, timeout=10):
    """Run a shell script and return the completed process."""
    cmd = ["bash", str(script_path)]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def tool_available(name):
    """Check if a CLI tool is available on PATH."""
    return shutil.which(name) is not None


class TestWaitForUrl:
    script = SCRIPTS_DIR / "wait_for_url.sh"

    def test_unreachable_url_exits_nonzero(self):
        result = run_script(
            self.script,
            ["http://127.0.0.1:19999/nonexistent", "2"],
            timeout=15,
        )
        assert result.returncode != 0


class TestDependencyScan:
    script = SCRIPTS_DIR / "dependency-scan.sh"

    def test_unknown_option_exits_nonzero(self):
        result = run_script(self.script, ["--bogus"])
        assert result.returncode != 0


class TestGitleaks:
    script = SCRIPTS_DIR / "gitleaks" / "run-gitleaks.sh"

    def test_unknown_option_exits_nonzero(self):
        result = run_script(self.script, ["--bogus"])
        assert result.returncode != 0


class TestTrivy:
    script = SCRIPTS_DIR / "trivy" / "run-trivy.sh"

    def test_unknown_option_exits_nonzero(self):
        result = run_script(self.script, ["--bogus"])
        assert result.returncode != 0


class TestZapBaseline:
    script = SCRIPTS_DIR / "zap" / "run-baseline.sh"

    def test_unknown_option_exits_nonzero(self):
        result = run_script(self.script, ["--bogus"])
        assert result.returncode != 0


class TestBashSyntax:
    def test_all_scripts_valid_bash_syntax(self):
        """Every .sh file should pass bash -n syntax check."""
        sh_files = list(SCRIPTS_DIR.rglob("*.sh"))
        assert sh_files, "No shell scripts found"

        failures = []
        for script in sh_files:
            result = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                failures.append(f"{script.name}: {result.stderr.strip()}")

        assert not failures, "Bash syntax errors:\n" + "\n".join(failures)


# =============================================================================
# Detection tests — verify tools actually find real problems
# =============================================================================


@pytest.mark.slow
@pytest.mark.skipif(not tool_available("semgrep"), reason="semgrep not installed")
class TestSemgrepDetection:
    """Verify custom Semgrep rules detect known-bad patterns."""

    SEMGREP_CONFIG = Path(__file__).resolve().parent.parent / ".semgrep"

    def test_detects_sql_injection_string_format(self, tmp_path):
        """Semgrep should flag SQL injection via % formatting."""
        bad_file = tmp_path / "vuln.py"
        bad_file.write_text("def bad(cr, uid):\n" '    cr.execute("SELECT * FROM t WHERE id = %s" % uid)\n')
        result = subprocess.run(
            [
                "semgrep",
                "scan",
                "--config",
                str(self.SEMGREP_CONFIG),
                "--json",
                "--metrics",
                "off",
                str(bad_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = json.loads(result.stdout)
        rule_ids = [r["check_id"] for r in output.get("results", [])]
        assert "odoo-sql-injection-string-format" in rule_ids, f"Expected SQL injection rule to fire, got: {rule_ids}"

    def test_detects_sudo_on_sensitive_model(self, tmp_path):
        """Semgrep should flag sudo() on sensitive models."""
        bad_file = tmp_path / "vuln2.py"
        bad_file.write_text("def bad(self):\n" "    return self.env['res.partner'].sudo()\n")
        result = subprocess.run(
            [
                "semgrep",
                "scan",
                "--config",
                str(self.SEMGREP_CONFIG),
                "--json",
                "--metrics",
                "off",
                str(bad_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = json.loads(result.stdout)
        rule_ids = [r["check_id"] for r in output.get("results", [])]
        assert (
            "odoo-sudo-on-sensitive-models" in rule_ids
        ), f"Expected sensitive model sudo rule to fire, got: {rule_ids}"


@pytest.mark.slow
@pytest.mark.skipif(not tool_available("gitleaks"), reason="gitleaks not installed")
class TestGitleaksDetection:
    """Verify Gitleaks detects known secret patterns."""

    def test_detects_aws_access_key(self, tmp_path):
        """Gitleaks should flag a known AWS key pattern."""
        secret_file = tmp_path / "config.py"
        secret_file.write_text('AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n')
        result = subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                str(tmp_path),
                "--no-git",
                "--report-format",
                "json",
                "--report-path",
                str(tmp_path / "report.json"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # gitleaks exits non-zero when secrets are found
        assert result.returncode != 0, "Expected gitleaks to detect the AWS key"
        report = json.loads((tmp_path / "report.json").read_text())
        assert len(report) > 0, "Expected at least one finding in gitleaks report"


@pytest.mark.slow
@pytest.mark.skipif(not tool_available("pip-audit"), reason="pip-audit not installed")
class TestPipAuditDetection:
    """Verify pip-audit detects known-vulnerable packages."""

    def test_detects_vulnerable_package(self, tmp_path):
        """pip-audit should flag urllib3==1.26.5 (CVE-2023-43804)."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("urllib3==1.26.5\n")
        result = subprocess.run(
            [
                "pip-audit",
                "-r",
                str(req_file),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = json.loads(result.stdout)
        vulnerable = [dep for dep in output.get("dependencies", []) if dep.get("vulns")]
        assert len(vulnerable) > 0, "Expected pip-audit to find vulnerabilities in urllib3==1.26.5"
