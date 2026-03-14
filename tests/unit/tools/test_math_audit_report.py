"""Tests for the math audit report generator.

Constructs mock ``AuditReport`` models and verifies the generated
markdown contains expected sections, tables, and formatting.
"""

from __future__ import annotations

import datetime

from options_arena.models.audit import AuditFinding, AuditLayerSummary, AuditReport
from options_arena.models.enums import AuditLayer, AuditSeverity
from tools.math_audit_report import generate_math_audit_report


def _make_finding(
    *,
    function_name: str = "pricing.bsm.bsm_price",
    layer: AuditLayer = AuditLayer.CORRECTNESS,
    severity: AuditSeverity = AuditSeverity.WARNING,
    description: str = "Test failure in BSM price computation",
    expected_value: float | None = None,
    actual_value: float | None = None,
    tolerance: float | None = None,
    source: str | None = None,
) -> AuditFinding:
    """Create a test AuditFinding with sensible defaults."""
    return AuditFinding(
        function_name=function_name,
        layer=layer,
        severity=severity,
        description=description,
        expected_value=expected_value,
        actual_value=actual_value,
        tolerance=tolerance,
        source=source,
    )


def _make_layer_summary(
    *,
    layer: AuditLayer = AuditLayer.CORRECTNESS,
    total_functions: int = 87,
    tested_functions: int = 87,
    passed: int = 87,
    failed: int = 0,
    coverage_pct: float = 1.0,
    findings: list[AuditFinding] | None = None,
) -> AuditLayerSummary:
    """Create a test AuditLayerSummary with sensible defaults."""
    return AuditLayerSummary(
        layer=layer,
        total_functions=total_functions,
        tested_functions=tested_functions,
        passed=passed,
        failed=failed,
        coverage_pct=coverage_pct,
        findings=findings or [],
    )


def _make_report(
    *,
    layers: list[AuditLayerSummary] | None = None,
    total_findings: int = 0,
    critical_count: int = 0,
    warning_count: int = 0,
    info_count: int = 0,
) -> AuditReport:
    """Create a test AuditReport with sensible defaults."""
    if layers is None:
        layers = [
            _make_layer_summary(layer=AuditLayer.CORRECTNESS),
            _make_layer_summary(layer=AuditLayer.STABILITY),
            _make_layer_summary(layer=AuditLayer.PERFORMANCE),
        ]
    return AuditReport(
        generated_at=datetime.datetime(2026, 3, 14, 12, 0, 0, tzinfo=datetime.UTC),
        layers=layers,
        total_findings=total_findings,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeneratesValidMarkdown:
    """Report generator produces valid markdown from mock AuditReport."""

    def test_returns_string(self) -> None:
        """Output is a string."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert isinstance(result, str)

    def test_contains_header(self) -> None:
        """Output starts with the expected header."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "# Mathematical Computation Audit Report" in result

    def test_contains_timestamp(self) -> None:
        """Output includes the generation timestamp."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "2026-03-14 12:00 UTC" in result

    def test_contains_total_findings_count(self) -> None:
        """Output includes the total findings breakdown."""
        report = _make_report(
            total_findings=5,
            critical_count=1,
            warning_count=3,
            info_count=1,
        )
        result = generate_math_audit_report(report)
        assert "5" in result
        assert "1 critical" in result
        assert "3 warning" in result
        assert "1 info" in result


class TestIncludesSummaryTable:
    """Report includes per-layer summary table."""

    def test_summary_section_present(self) -> None:
        """Summary section heading exists."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "## Summary" in result

    def test_summary_table_has_headers(self) -> None:
        """Summary table includes column headers."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "Layer" in result
        assert "Total Functions" in result
        assert "Tested" in result
        assert "Passed" in result
        assert "Failed" in result
        assert "Coverage" in result

    def test_summary_table_contains_layer_rows(self) -> None:
        """Summary table has a row for each layer in the report."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "Correctness" in result
        assert "Stability" in result
        assert "Performance" in result

    def test_summary_coverage_percentage(self) -> None:
        """Coverage percentage is formatted correctly."""
        report = _make_report(
            layers=[
                _make_layer_summary(
                    layer=AuditLayer.CORRECTNESS,
                    coverage_pct=0.75,
                ),
            ]
        )
        result = generate_math_audit_report(report)
        assert "75%" in result


class TestIncludesFindings:
    """Report includes findings section with severity."""

    def test_findings_section_present(self) -> None:
        """Findings section heading exists."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "## Findings" in result

    def test_findings_grouped_by_severity(self) -> None:
        """Findings are grouped by severity (CRITICAL first)."""
        critical_finding = _make_finding(
            severity=AuditSeverity.CRITICAL,
            description="Critical failure",
        )
        warning_finding = _make_finding(
            severity=AuditSeverity.WARNING,
            description="Warning issue",
        )
        info_finding = _make_finding(
            severity=AuditSeverity.INFO,
            description="Info note",
        )

        report = _make_report(
            layers=[
                _make_layer_summary(
                    findings=[critical_finding, warning_finding, info_finding],
                    failed=2,
                ),
            ],
            total_findings=3,
            critical_count=1,
            warning_count=1,
            info_count=1,
        )

        result = generate_math_audit_report(report)
        # CRITICAL section must appear before WARNING and INFO
        critical_pos = result.index("CRITICAL")
        warning_pos = result.index("WARNING")
        info_pos = result.index("INFO (1)")
        assert critical_pos < warning_pos < info_pos

    def test_finding_includes_function_name(self) -> None:
        """Each finding includes the function name."""
        finding = _make_finding(
            function_name="pricing.bsm.bsm_price",
            description="Price deviation detected",
        )
        report = _make_report(
            layers=[_make_layer_summary(findings=[finding], failed=1)],
            total_findings=1,
            warning_count=1,
        )
        result = generate_math_audit_report(report)
        assert "pricing.bsm.bsm_price" in result

    def test_finding_with_expected_and_actual(self) -> None:
        """Findings with expected/actual values show comparison."""
        finding = _make_finding(
            expected_value=10.45,
            actual_value=10.50,
            tolerance=0.01,
        )
        report = _make_report(
            layers=[_make_layer_summary(findings=[finding], failed=1)],
            total_findings=1,
            warning_count=1,
        )
        result = generate_math_audit_report(report)
        assert "Expected: 10.45" in result
        assert "Actual: 10.5" in result
        assert "Tolerance: 0.01" in result

    def test_finding_with_source(self) -> None:
        """Findings with a source citation include it."""
        finding = _make_finding(source="Hull 2018, Table 15.2")
        report = _make_report(
            layers=[_make_layer_summary(findings=[finding], failed=1)],
            total_findings=1,
            warning_count=1,
        )
        result = generate_math_audit_report(report)
        assert "Hull 2018, Table 15.2" in result


class TestEmptyFindings:
    """Report handles zero findings gracefully."""

    def test_clean_audit_message(self) -> None:
        """Zero findings produces a clean audit message."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "No findings" in result

    def test_no_severity_headers_on_clean_audit(self) -> None:
        """No severity group headers when there are zero findings."""
        report = _make_report()
        result = generate_math_audit_report(report)
        assert "### CRITICAL" not in result
        assert "### WARNING" not in result
        # INFO is present in header line "0 info" but not as a severity header
        assert "### INFO" not in result


class TestMixedSeverityFindings:
    """Report handles mixed severity findings correctly."""

    def test_all_severity_levels(self) -> None:
        """Report with all 3 severity levels renders all sections."""
        findings = [
            _make_finding(
                function_name="func_a",
                severity=AuditSeverity.CRITICAL,
                description="Critical issue",
            ),
            _make_finding(
                function_name="func_b",
                severity=AuditSeverity.WARNING,
                description="Warning issue",
            ),
            _make_finding(
                function_name="func_c",
                severity=AuditSeverity.INFO,
                description="Info note",
            ),
        ]
        report = _make_report(
            layers=[_make_layer_summary(findings=findings, failed=3)],
            total_findings=3,
            critical_count=1,
            warning_count=1,
            info_count=1,
        )
        result = generate_math_audit_report(report)

        assert "func_a" in result
        assert "func_b" in result
        assert "func_c" in result
        assert "Critical issue" in result
        assert "Warning issue" in result
        assert "Info note" in result

    def test_multiple_findings_per_severity(self) -> None:
        """Multiple findings within the same severity are all rendered."""
        findings = [
            _make_finding(
                function_name="func_x",
                severity=AuditSeverity.CRITICAL,
                description="First critical",
            ),
            _make_finding(
                function_name="func_y",
                severity=AuditSeverity.CRITICAL,
                description="Second critical",
            ),
        ]
        report = _make_report(
            layers=[_make_layer_summary(findings=findings, failed=2)],
            total_findings=2,
            critical_count=2,
        )
        result = generate_math_audit_report(report)

        assert "func_x" in result
        assert "func_y" in result
        assert "First critical" in result
        assert "Second critical" in result
        assert "CRITICAL (2)" in result
