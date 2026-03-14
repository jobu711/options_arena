"""Tests for the /math-audit skill file and --discover CLI integration.

Verifies the skill definition file exists and contains expected sections,
the --discover flag is accepted without error, and discovery findings
display works with mock data.

No real API calls -- uses mocks and patching throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.cli.audit import (
    _load_discovery_findings,
    _render_discovery_findings,
    _run_discovery,
)
from options_arena.models.audit import AuditFinding
from options_arena.models.enums import AuditLayer, AuditSeverity

# Absolute path to the skill definition file.
_SKILL_FILE = Path(__file__).resolve().parents[3] / ".claude" / "commands" / "math-audit.md"

runner = CliRunner()


# ---------------------------------------------------------------------------
# Skill file existence and content tests
# ---------------------------------------------------------------------------


class TestSkillFileExists:
    """Verify the /math-audit skill definition file exists."""

    def test_skill_file_exists(self) -> None:
        """Skill definition file must exist at .claude/commands/math-audit.md."""
        assert _SKILL_FILE.exists(), f"Skill file not found: {_SKILL_FILE}"

    def test_skill_file_is_markdown(self) -> None:
        """Skill file must be a .md file."""
        assert _SKILL_FILE.suffix == ".md"


class TestSkillFileContent:
    """Verify the skill file contains expected sections."""

    @pytest.fixture(autouse=True)
    def _read_skill(self) -> None:
        """Read skill file content once for all tests in this class."""
        self.content = _SKILL_FILE.read_text(encoding="utf-8")

    def test_has_frontmatter(self) -> None:
        """Skill file must start with YAML frontmatter."""
        assert self.content.startswith("---")

    def test_has_allowed_tools(self) -> None:
        """Frontmatter must declare allowed-tools."""
        assert "allowed-tools:" in self.content

    def test_has_description(self) -> None:
        """Frontmatter must include a description."""
        assert "description:" in self.content

    def test_has_source_files_section(self) -> None:
        """Skill must reference the mathematical source modules to audit."""
        assert "pricing/" in self.content
        assert "indicators/" in self.content
        assert "scoring/" in self.content

    def test_has_severity_guide(self) -> None:
        """Skill must define the severity classification system."""
        assert "CRITICAL" in self.content
        assert "WARNING" in self.content
        assert "INFO" in self.content

    def test_has_output_format(self) -> None:
        """Skill must describe the structured output format."""
        assert "Finding" in self.content or "finding" in self.content
        assert "Proposed Test" in self.content or "proposed_test" in self.content

    def test_has_formula_verification_section(self) -> None:
        """Skill must instruct agent to verify formulas against cited papers."""
        assert "formula" in self.content.lower() or "Formula" in self.content

    def test_has_boundary_conditions_section(self) -> None:
        """Skill must instruct agent to check boundary conditions."""
        assert "boundary" in self.content.lower() or "Boundary" in self.content

    def test_references_bsm(self) -> None:
        """Skill must reference BSM (Black-Scholes-Merton) model."""
        assert "BSM" in self.content or "Black-Scholes" in self.content

    def test_references_baw(self) -> None:
        """Skill must reference BAW (Barone-Adesi-Whaley) model."""
        assert "BAW" in self.content or "Barone-Adesi" in self.content


# ---------------------------------------------------------------------------
# Discovery findings loading tests
# ---------------------------------------------------------------------------


def _make_finding_dict(
    *,
    function_name: str = "bsm_price",
    severity: str = "warning",
    description: str = "Test finding",
    source: str | None = "bsm.py",
    proposed_test: str | None = None,
) -> dict[str, Any]:
    """Create a dict matching the AuditFinding schema for JSON test data."""
    return {
        "function_name": function_name,
        "layer": "discovery",
        "severity": severity,
        "description": description,
        "source": source,
        "proposed_test": proposed_test,
    }


class TestLoadDiscoveryFindings:
    """Test _load_discovery_findings with mock JSON files."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent file returns empty list, no exception."""
        result = _load_discovery_findings(tmp_path / "nonexistent.json")
        assert result == []

    def test_empty_list_returns_empty(self, tmp_path: Path) -> None:
        """A JSON file containing an empty list returns empty findings."""
        path = tmp_path / "findings.json"
        path.write_text("[]", encoding="utf-8")
        result = _load_discovery_findings(path)
        assert result == []

    def test_single_finding_parsed(self, tmp_path: Path) -> None:
        """A single valid finding is correctly parsed into AuditFinding."""
        finding = _make_finding_dict(
            function_name="bsm_greeks",
            severity="critical",
            description="Sign error in d1 formula",
        )
        path = tmp_path / "findings.json"
        path.write_text(json.dumps([finding]), encoding="utf-8")

        result = _load_discovery_findings(path)

        assert len(result) == 1
        assert isinstance(result[0], AuditFinding)
        assert result[0].function_name == "bsm_greeks"
        assert result[0].severity == AuditSeverity.CRITICAL
        assert result[0].layer == AuditLayer.DISCOVERY

    def test_multiple_findings_parsed(self, tmp_path: Path) -> None:
        """Multiple findings with different severities are all parsed."""
        findings = [
            _make_finding_dict(severity="critical", function_name="bsm_price"),
            _make_finding_dict(severity="warning", function_name="american_price"),
            _make_finding_dict(severity="info", function_name="compute_rsi"),
        ]
        path = tmp_path / "findings.json"
        path.write_text(json.dumps(findings), encoding="utf-8")

        result = _load_discovery_findings(path)

        assert len(result) == 3
        severities = {f.severity for f in result}
        assert severities == {
            AuditSeverity.CRITICAL,
            AuditSeverity.WARNING,
            AuditSeverity.INFO,
        }

    def test_finding_with_proposed_test(self, tmp_path: Path) -> None:
        """A finding with proposed_test field is correctly parsed."""
        finding = _make_finding_dict(
            proposed_test="def test_bsm_price_sign() -> None:\n    assert bsm_price(...) > 0",
        )
        path = tmp_path / "findings.json"
        path.write_text(json.dumps([finding]), encoding="utf-8")

        result = _load_discovery_findings(path)
        assert result[0].proposed_test is not None
        assert "test_bsm_price_sign" in result[0].proposed_test


# ---------------------------------------------------------------------------
# Discovery rendering tests
# ---------------------------------------------------------------------------


class TestRenderDiscoveryFindings:
    """Test _render_discovery_findings output (no assertions on rendered text)."""

    def test_empty_findings_no_crash(self) -> None:
        """Rendering empty findings list does not raise."""
        _render_discovery_findings([])

    def test_findings_render_no_crash(self) -> None:
        """Rendering a list of findings does not raise."""
        findings = [
            AuditFinding(
                function_name="bsm_price",
                layer=AuditLayer.DISCOVERY,
                severity=AuditSeverity.CRITICAL,
                description="Sign error in d1",
                source="bsm.py",
            ),
            AuditFinding(
                function_name="american_iv",
                layer=AuditLayer.DISCOVERY,
                severity=AuditSeverity.WARNING,
                description="Missing T=0 guard",
            ),
            AuditFinding(
                function_name="compute_rsi",
                layer=AuditLayer.DISCOVERY,
                severity=AuditSeverity.INFO,
                description="Uses 365-day year convention",
            ),
        ]
        # Should not raise
        _render_discovery_findings(findings)


# ---------------------------------------------------------------------------
# _run_discovery integration tests
# ---------------------------------------------------------------------------


class TestRunDiscovery:
    """Test _run_discovery never-raises contract."""

    def test_run_discovery_no_findings_file(self) -> None:
        """_run_discovery succeeds when no findings file exists."""
        with patch(
            "options_arena.cli.audit._DISCOVERY_FINDINGS_PATH",
            Path("/nonexistent/path/findings.json"),
        ):
            # Should not raise
            _run_discovery()

    def test_run_discovery_with_invalid_json(self, tmp_path: Path) -> None:
        """_run_discovery does not crash on malformed JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        with patch("options_arena.cli.audit._DISCOVERY_FINDINGS_PATH", bad_file):
            # Should not raise -- caught by the outer try/except
            _run_discovery()


# ---------------------------------------------------------------------------
# CLI --discover flag acceptance tests
# ---------------------------------------------------------------------------


class TestDiscoverFlag:
    """Test that --discover flag is accepted by the CLI without error."""

    def test_discover_flag_accepted(self) -> None:
        """CLI accepts --discover flag and returns exit code 0."""
        with patch(
            "options_arena.cli.audit._DISCOVERY_FINDINGS_PATH",
            Path("/nonexistent/path/findings.json"),
        ):
            result = runner.invoke(app, ["audit", "math", "--discover"])
            assert result.exit_code == 0, (
                f"Expected exit code 0, got {result.exit_code}.\nOutput: {result.output}"
            )

    def test_discover_flag_shows_skill_guidance(self) -> None:
        """CLI --discover output includes guidance to run /math-audit skill."""
        with patch(
            "options_arena.cli.audit._DISCOVERY_FINDINGS_PATH",
            Path("/nonexistent/path/findings.json"),
        ):
            result = runner.invoke(app, ["audit", "math", "--discover"])
            assert "/math-audit" in result.output

    def test_discover_with_findings_shows_table(self, tmp_path: Path) -> None:
        """CLI --discover displays findings table when JSON file exists."""
        findings = [
            _make_finding_dict(
                severity="critical",
                function_name="bsm_price",
                description="Sign error in d1 formula",
            ),
        ]
        findings_path = tmp_path / "findings.json"
        findings_path.write_text(json.dumps(findings), encoding="utf-8")

        with patch("options_arena.cli.audit._DISCOVERY_FINDINGS_PATH", findings_path):
            result = runner.invoke(app, ["audit", "math", "--discover"])
            assert result.exit_code == 0
            assert "bsm_price" in result.output
