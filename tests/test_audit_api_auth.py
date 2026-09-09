"""Tests for the API authentication audit script.

Validates that scripts/audit-api-auth.py correctly detects authenticated
and unauthenticated FastAPI endpoints using AST analysis.
"""

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit-api-auth.py"
ROOT_DIR = Path(__file__).resolve().parent.parent


def run_audit(args=None, timeout=30):
    """Run the audit script and return the completed process."""
    cmd = ["python", str(SCRIPT)]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT_DIR),
    )


class TestAuditBasicExecution:
    """Test basic script execution modes."""

    def test_runs_successfully(self):
        """Script should exit 0 when run on the codebase."""
        result = run_audit()
        assert result.returncode == 0, f"Script failed:\n{result.stderr}"

    def test_strict_mode_exits_zero_on_clean_codebase(self):
        """--strict should exit 0 when all endpoints have auth or are allowlisted."""
        result = run_audit(["--strict"])
        assert result.returncode == 0, f"Strict mode found unauthenticated endpoints:\n{result.stdout}"

    def test_verbose_output(self):
        """--verbose should show protected and public endpoint lists."""
        result = run_audit(["--verbose"])
        assert result.returncode == 0
        assert "PROTECTED ENDPOINTS" in result.stdout
        assert "PUBLIC (ALLOWLISTED) ENDPOINTS" in result.stdout

    def test_json_output_format(self):
        """--json should produce valid JSON with expected keys."""
        result = run_audit(["--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "missing_auth" in data
        assert "public_allowed" in data
        summary = data["summary"]
        assert "total_endpoints" in summary
        assert "protected" in summary
        assert "public_allowed" in summary
        assert "missing_auth" in summary
        assert summary["total_endpoints"] > 0, "Should find at least one endpoint"

    def test_json_strict_combined(self):
        """--json --strict should produce JSON and exit 0 on clean codebase."""
        result = run_audit(["--json", "--strict"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["summary"]["missing_auth"] == 0


class TestKnownEndpoints:
    """Test that specific known endpoints are correctly classified."""

    @pytest.fixture(scope="class")
    def audit_data(self):
        """Run audit once and parse JSON for use across tests."""
        result = run_audit(["--json"])
        assert result.returncode == 0
        return json.loads(result.stdout)

    def _find_endpoint(self, findings, module, filename, function):
        """Find a specific endpoint in the findings list."""
        for f in findings:
            if f["module"] == module and f["file"].endswith(filename) and f["function"] == function:
                return f
        return None

    def test_no_missing_auth_endpoints(self, audit_data):
        """All endpoints should be authenticated or allowlisted."""
        missing = audit_data["missing_auth"]
        assert not missing, f"Found unprotected endpoints: {missing}"


class TestSyntheticRouterDetection:
    """Test auth detection with synthetic router files."""

    @pytest.fixture()
    def module_dir(self, tmp_path):
        """Create a minimal module directory structure."""
        mod = tmp_path / "test_module" / "routers"
        mod.mkdir(parents=True)
        return mod

    def _run_on_dir(self, root_dir, args=None):
        """Run the audit script pointed at a custom root directory.

        The script uses its parent.parent as root_dir, so we invoke the
        analysis functions directly via a wrapper script.
        """
        wrapper = root_dir / "_run_audit.py"
        wrapper.write_text(
            textwrap.dedent(f"""\
            import sys
            sys.path.insert(0, {str(SCRIPT.parent)!r})

            # Import the script as a module
            import importlib.util
            spec = importlib.util.spec_from_file_location("audit", {str(SCRIPT)!r})
            audit = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(audit)

            root_dir = {str(root_dir)!r}
            router_files = audit.find_router_files(root_dir)
            all_findings = []
            for filepath in router_files:
                all_findings.extend(audit.analyze_file(filepath, root_dir))

            import json
            print(json.dumps(all_findings))
        """)
        )
        result = subprocess.run(
            ["python", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Wrapper failed:\n{result.stderr}"
        return json.loads(result.stdout)

    def test_detects_authenticated_endpoint(self, module_dir, tmp_path):
        """Endpoint with Depends(get_authenticated_client) should be detected."""
        router_file = module_dir / "protected.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter, Depends
            from typing import Annotated

            router = APIRouter()

            @router.get("/protected")
            def protected_endpoint(
                client: Annotated[str, Depends(get_authenticated_client)],
            ):
                return {"status": "ok"}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 1
        assert findings[0]["has_auth"] is True
        assert findings[0]["function"] == "protected_endpoint"

    def test_detects_missing_auth(self, module_dir, tmp_path):
        """Endpoint without auth dependency should be flagged."""
        router_file = module_dir / "unprotected.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/public")
            def public_endpoint():
                return {"status": "open"}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 1
        assert findings[0]["has_auth"] is False
        assert findings[0]["function"] == "public_endpoint"

    def test_detects_decorator_level_dependencies(self, module_dir, tmp_path):
        """Auth in decorator dependencies=[] should be detected."""
        router_file = module_dir / "decorator_auth.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter, Depends

            router = APIRouter()

            @router.get("/secured", dependencies=[Depends(verify_bearer_token)])
            def secured_endpoint():
                return {"status": "ok"}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 1
        assert findings[0]["has_auth"] is True

    def test_detects_default_depends(self, module_dir, tmp_path):
        """Auth as default parameter value should be detected."""
        router_file = module_dir / "default_auth.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter, Depends

            router = APIRouter()

            @router.post("/action")
            def action_endpoint(client=Depends(get_current_client)):
                return {"status": "ok"}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 1
        assert findings[0]["has_auth"] is True

    def test_extracts_route_info(self, module_dir, tmp_path):
        """Route method and path should be extracted correctly."""
        router_file = module_dir / "info.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter, Depends

            router = APIRouter()

            @router.post("/submit")
            def submit(client=Depends(get_authenticated_client)):
                return {}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 1
        assert findings[0]["method"] == "POST"
        assert findings[0]["path"] == "/submit"

    def test_multiple_endpoints_in_file(self, module_dir, tmp_path):
        """Multiple endpoints in a single file should all be detected."""
        router_file = module_dir / "multi.py"
        router_file.write_text(
            textwrap.dedent("""\
            from fastapi import APIRouter, Depends

            router = APIRouter()

            @router.get("/a")
            def endpoint_a(client=Depends(get_authenticated_client)):
                return {}

            @router.get("/b")
            def endpoint_b():
                return {}

            @router.post("/c")
            def endpoint_c(client=Depends(verify_request_signature)):
                return {}
        """)
        )
        findings = self._run_on_dir(tmp_path)
        assert len(findings) == 3
        auth_status = {f["function"]: f["has_auth"] for f in findings}
        assert auth_status["endpoint_a"] is True
        assert auth_status["endpoint_b"] is False
        assert auth_status["endpoint_c"] is True
