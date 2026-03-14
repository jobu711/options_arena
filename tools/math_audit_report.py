"""Pure markdown report generator for mathematical computation audit results.

Converts an ``AuditReport`` model into a GitHub-flavored Markdown string.
No I/O, no side effects -- the caller is responsible for writing the output.
"""

from __future__ import annotations

from options_arena.models.audit import AuditFinding, AuditReport
from options_arena.models.enums import AuditSeverity


def _render_summary_table(report: AuditReport) -> str:
    """Render the per-layer summary as a Markdown table.

    Args:
        report: The completed audit report.

    Returns:
        Markdown table string with header and one row per layer.
    """
    lines: list[str] = [
        "## Summary",
        "",
        "| Layer | Total Functions | Tested | Passed | Failed | Coverage |",
        "|-------|-----------------|--------|--------|--------|----------|",
    ]

    for layer_summary in report.layers:
        coverage_str = f"{layer_summary.coverage_pct:.0%}"
        lines.append(
            f"| {layer_summary.layer.value.capitalize()} "
            f"| {layer_summary.total_functions} "
            f"| {layer_summary.tested_functions} "
            f"| {layer_summary.passed} "
            f"| {layer_summary.failed} "
            f"| {coverage_str} |"
        )

    lines.append("")
    return "\n".join(lines)


def _render_finding(finding: AuditFinding) -> str:
    """Render a single finding as a Markdown bullet point.

    Args:
        finding: An individual audit finding.

    Returns:
        Markdown string for one finding entry.
    """
    lines: list[str] = [
        f"- **{finding.function_name}** ({finding.layer.value}): {finding.description}",
    ]

    if finding.expected_value is not None and finding.actual_value is not None:
        lines.append(f"  - Expected: {finding.expected_value}, Actual: {finding.actual_value}")
        if finding.tolerance is not None:
            lines.append(f"  - Tolerance: {finding.tolerance}")

    if finding.source is not None:
        lines.append(f"  - Source: {finding.source}")

    return "\n".join(lines)


def _render_findings_section(findings: list[AuditFinding]) -> str:
    """Render findings grouped by severity (CRITICAL first, then WARNING, then INFO).

    Args:
        findings: All findings from the audit report.

    Returns:
        Markdown string for the complete findings section.
    """
    if not findings:
        return "## Findings\n\nNo findings -- all audited functions passed.\n"

    severity_order: list[AuditSeverity] = [
        AuditSeverity.CRITICAL,
        AuditSeverity.WARNING,
        AuditSeverity.INFO,
    ]

    lines: list[str] = ["## Findings", ""]

    for severity in severity_order:
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue

        lines.append(f"### {severity.value.upper()} ({len(group)})")
        lines.append("")
        for finding in group:
            lines.append(_render_finding(finding))
        lines.append("")

    return "\n".join(lines)


def generate_math_audit_report(report: AuditReport) -> str:
    """Convert an ``AuditReport`` into a GitHub-flavored Markdown string.

    This is a pure function with no side effects. The caller is responsible
    for writing the returned string to a file or displaying it.

    Args:
        report: Complete audit report from the CLI audit command.

    Returns:
        A Markdown string with header, summary table, and findings section.
    """
    date_str = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = []

    # Header
    header_lines: list[str] = [
        "# Mathematical Computation Audit Report",
        "",
        f"**Generated**: {date_str}",
        "",
        f"**Total Findings**: {report.total_findings} "
        f"({report.critical_count} critical, "
        f"{report.warning_count} warning, "
        f"{report.info_count} info)",
        "",
    ]
    sections.append("\n".join(header_lines))

    # Summary table
    sections.append(_render_summary_table(report))

    # Collect all findings from all layers
    all_findings: list[AuditFinding] = []
    for layer_summary in report.layers:
        all_findings.extend(layer_summary.findings)

    # Findings section
    sections.append(_render_findings_section(all_findings))

    return "\n".join(sections)
