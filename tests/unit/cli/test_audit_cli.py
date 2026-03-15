"""Tests for the ``audit math`` CLI command.

All tests mock ``subprocess.run`` to avoid actually running pytest.
Typer CliRunner captures output and exit codes for assertion.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from options_arena.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestAuditCommandRegistration:
    """Verify the audit math command is registered and accessible."""

    def test_audit_group_exists(self) -> None:
        """The 'audit' subcommand group is registered on the main app."""
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0
        assert "Mathematical computation audit tools" in result.output

    def test_math_command_exists(self) -> None:
        """The 'audit math' command is registered."""
        result = runner.invoke(app, ["audit", "math", "--help"])
        assert result.exit_code == 0
        assert "--correctness" in result.output
        assert "--stability" in result.output
        assert "--performance" in result.output
        assert "--report" in result.output
        assert "--discover" in result.output


# ---------------------------------------------------------------------------
# Flag parsing and layer selection
# ---------------------------------------------------------------------------


class TestAuditFlagParsing:
    """Verify flag parsing and layer selection logic."""

    @patch("options_arena.cli.audit._run_audit_layer")
    @patch(
        "options_arena.cli.audit.MATH_FUNCTION_REGISTRY",
        new={"func1": lambda: None},
        create=True,
    )
    def test_no_flags_runs_all_three_layers(self, mock_run_layer: MagicMock) -> None:
        """Without flags, all 3 deterministic layers run."""
        mock_run_layer.return_value = MagicMock(
            layer=None, return_code=0, passed=10, failed=0, errors=0, total=10
        )
        # Patch the layer attribute dynamically
        from options_arena.models.enums import AuditLayer

        call_count = 0

        def side_effect(layer: AuditLayer) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return MagicMock(
                layer=layer,
                return_code=0,
                passed=10,
                failed=0,
                errors=0,
                total=10,
            )

        mock_run_layer.side_effect = side_effect

        runner.invoke(app, ["audit", "math"])
        assert mock_run_layer.call_count == 3

    @patch("options_arena.cli.audit._run_audit_layer")
    def test_correctness_flag_runs_only_correctness(self, mock_run_layer: MagicMock) -> None:
        """--correctness flag runs only the correctness layer."""
        from options_arena.models.enums import AuditLayer

        mock_run_layer.return_value = MagicMock(
            layer=AuditLayer.CORRECTNESS,
            return_code=0,
            passed=10,
            failed=0,
            errors=0,
            total=10,
        )

        runner.invoke(app, ["audit", "math", "--correctness"])
        assert mock_run_layer.call_count == 1
        mock_run_layer.assert_called_once_with(AuditLayer.CORRECTNESS)

    @patch("options_arena.cli.audit._run_audit_layer")
    def test_stability_flag_runs_only_stability(self, mock_run_layer: MagicMock) -> None:
        """--stability flag runs only the stability layer."""
        from options_arena.models.enums import AuditLayer

        mock_run_layer.return_value = MagicMock(
            layer=AuditLayer.STABILITY,
            return_code=0,
            passed=10,
            failed=0,
            errors=0,
            total=10,
        )

        runner.invoke(app, ["audit", "math", "--stability"])
        assert mock_run_layer.call_count == 1
        mock_run_layer.assert_called_once_with(AuditLayer.STABILITY)

    @patch("options_arena.cli.audit._run_audit_layer")
    def test_performance_flag_runs_only_performance(self, mock_run_layer: MagicMock) -> None:
        """--performance flag runs only the performance layer."""
        from options_arena.models.enums import AuditLayer

        mock_run_layer.return_value = MagicMock(
            layer=AuditLayer.PERFORMANCE,
            return_code=0,
            passed=10,
            failed=0,
            errors=0,
            total=10,
        )

        runner.invoke(app, ["audit", "math", "--performance"])
        assert mock_run_layer.call_count == 1
        mock_run_layer.assert_called_once_with(AuditLayer.PERFORMANCE)

    def test_discover_flag_prints_stub_message(self) -> None:
        """--discover flag prints stub message and returns."""
        result = runner.invoke(app, ["audit", "math", "--discover"])
        assert result.exit_code == 0
        assert "/math-audit" in result.output


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestAuditReportFlag:
    """Verify --report flag generates markdown output and writes to disk."""

    @patch("options_arena.cli.audit._run_audit_layer")
    def test_report_flag_generates_markdown(self, mock_run_layer: MagicMock) -> None:
        """--report flag produces markdown content in output."""
        from options_arena.models.enums import AuditLayer

        mock_run_layer.return_value = MagicMock(
            layer=AuditLayer.CORRECTNESS,
            return_code=0,
            passed=10,
            failed=0,
            errors=0,
            total=10,
        )

        result = runner.invoke(app, ["audit", "math", "--correctness", "--report"])
        assert result.exit_code == 0
        assert "Markdown Report" in result.output

    @patch("options_arena.cli.audit._run_audit_layer")
    def test_report_flag_writes_file_to_disk(
        self, mock_run_layer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--report flag writes markdown report to math-audit-report.md on disk."""
        from options_arena.models.enums import AuditLayer

        mock_run_layer.return_value = MagicMock(
            layer=AuditLayer.CORRECTNESS,
            return_code=0,
            passed=10,
            failed=0,
            errors=0,
            total=10,
        )

        # Change working directory so the report file lands in tmp_path
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["audit", "math", "--correctness", "--report"])
        assert result.exit_code == 0

        report_file = tmp_path / "math-audit-report.md"
        assert report_file.exists(), "Report file was not written to disk"

        content = report_file.read_text(encoding="utf-8")
        assert "Mathematical Computation Audit Report" in content
        assert "Report written to" in result.output


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


class TestPytestOutputParsing:
    """Verify parsing of pytest summary lines."""

    def test_parse_all_passed(self) -> None:
        """Parse a line with only passed tests."""
        from options_arena.cli.audit import _parse_pytest_output

        passed, failed, errors = _parse_pytest_output("87 passed in 12.45s\n")
        assert passed == 87
        assert failed == 0
        assert errors == 0

    def test_parse_mixed_results(self) -> None:
        """Parse a line with passed, failed, and error counts."""
        from options_arena.cli.audit import _parse_pytest_output

        output = "5 passed, 2 failed, 1 error in 3.21s\n"
        passed, failed, errors = _parse_pytest_output(output)
        assert passed == 5
        assert failed == 2
        assert errors == 1

    def test_parse_empty_output(self) -> None:
        """Empty output returns all zeros."""
        from options_arena.cli.audit import _parse_pytest_output

        passed, failed, errors = _parse_pytest_output("")
        assert passed == 0
        assert failed == 0
        assert errors == 0

    def test_parse_only_failed(self) -> None:
        """Parse output with only failures."""
        from options_arena.cli.audit import _parse_pytest_output

        passed, failed, errors = _parse_pytest_output("3 failed in 0.5s\n")
        assert passed == 0
        assert failed == 3
        assert errors == 0
