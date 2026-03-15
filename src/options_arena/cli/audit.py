"""CLI audit subcommand group: mathematical computation audit tools.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Audit layers are invoked via ``subprocess.run()``
to run pytest with the appropriate marker. The ``--discover`` flag triggers
the AI-powered discovery layer using pre-existing JSON findings.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from options_arena.cli.app import app
from options_arena.models.audit import (
    MATH_FUNCTION_COUNT,
    AuditFinding,
    AuditLayerSummary,
    AuditReport,
)
from options_arena.models.enums import AuditLayer, AuditSeverity

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

audit_app = typer.Typer(
    help="Mathematical computation audit tools.",
    no_args_is_help=True,
)
app.add_typer(audit_app, name="audit")

# ---------------------------------------------------------------------------
# Marker-to-AuditLayer mapping
# ---------------------------------------------------------------------------

_LAYER_MARKERS: dict[AuditLayer, str] = {
    AuditLayer.CORRECTNESS: "audit_correctness",
    AuditLayer.STABILITY: "audit_stability",
    AuditLayer.PERFORMANCE: "audit_performance",
}


@dataclass
class _LayerResult:
    """Intermediate result from running a single audit layer via pytest."""

    layer: AuditLayer
    return_code: int
    passed: int
    failed: int
    errors: int
    total: int


def _parse_pytest_output(output: str) -> tuple[int, int, int]:
    """Parse pytest summary line to extract passed/failed/error counts.

    Looks for the final summary line like ``"5 passed, 2 failed in 1.23s"``
    or ``"87 passed in 12.45s"``.

    Returns:
        Tuple of (passed, failed, errors).
    """
    passed = 0
    failed = 0
    errors = 0

    # Search lines in reverse for the summary line
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        # pytest summary lines contain counts like "N passed", "N failed", "N error"
        if "passed" in stripped or "failed" in stripped or "error" in stripped:
            passed_match = re.search(r"(\d+)\s+passed", stripped)
            failed_match = re.search(r"(\d+)\s+failed", stripped)
            error_match = re.search(r"(\d+)\s+error", stripped)
            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
            if error_match:
                errors = int(error_match.group(1))
            break

    return passed, failed, errors


def _run_audit_layer(layer: AuditLayer) -> _LayerResult:
    """Run a single audit layer by invoking pytest with the appropriate marker.

    Args:
        layer: The audit layer to run.

    Returns:
        A ``_LayerResult`` with pass/fail/error counts.
    """
    marker = _LAYER_MARKERS[layer]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        marker,
        "-q",
        "--tb=short",
        "--no-header",
    ]

    err_console.print(f"  Running {layer.value} layer...")

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Audit layer %s timed out after 300s", layer.value)
        return _LayerResult(
            layer=layer,
            return_code=-1,
            passed=0,
            failed=0,
            errors=1,
            total=1,
        )

    passed, failed, errors = _parse_pytest_output(result.stdout + "\n" + result.stderr)
    total = passed + failed + errors

    return _LayerResult(
        layer=layer,
        return_code=result.returncode,
        passed=passed,
        failed=failed,
        errors=errors,
        total=total,
    )


def _build_layer_summary(
    result: _LayerResult,
    total_functions: int,
) -> AuditLayerSummary:
    """Convert a ``_LayerResult`` into a frozen ``AuditLayerSummary`` model.

    Args:
        result: The layer result from running pytest.
        total_functions: Total number of math functions in the registry.

    Returns:
        An ``AuditLayerSummary`` model.
    """
    tested = result.passed + result.failed
    coverage = tested / total_functions if total_functions > 0 else 0.0

    findings: list[AuditFinding] = []
    if result.failed > 0:
        findings.append(
            AuditFinding(
                function_name="(aggregate)",
                layer=result.layer,
                severity=AuditSeverity.WARNING,
                description=f"{result.failed} test(s) failed in {result.layer.value} layer",
            )
        )
    if result.errors > 0:
        findings.append(
            AuditFinding(
                function_name="(aggregate)",
                layer=result.layer,
                severity=AuditSeverity.CRITICAL,
                description=f"{result.errors} test error(s) in {result.layer.value} layer",
            )
        )

    return AuditLayerSummary(
        layer=result.layer,
        total_functions=total_functions,
        tested_functions=tested,
        passed=result.passed,
        failed=result.failed,
        coverage_pct=min(coverage, 1.0),
        findings=findings,
    )


def _build_report(summaries: list[AuditLayerSummary]) -> AuditReport:
    """Aggregate layer summaries into a complete ``AuditReport``.

    Args:
        summaries: List of per-layer summary models.

    Returns:
        A frozen ``AuditReport`` model.
    """
    all_findings: list[AuditFinding] = []
    for s in summaries:
        all_findings.extend(s.findings)

    critical_count = sum(1 for f in all_findings if f.severity == AuditSeverity.CRITICAL)
    warning_count = sum(1 for f in all_findings if f.severity == AuditSeverity.WARNING)
    info_count = sum(1 for f in all_findings if f.severity == AuditSeverity.INFO)

    return AuditReport(
        generated_at=datetime.datetime.now(datetime.UTC),
        layers=summaries,
        total_findings=len(all_findings),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def _render_summary_table(report: AuditReport) -> None:
    """Print a Rich summary table from the audit report.

    Args:
        report: The completed audit report.
    """
    table = Table(title="Mathematical Computation Audit Summary")
    table.add_column("Layer", style="cyan", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Tested", justify="right")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Coverage", justify="right")

    for layer_summary in report.layers:
        coverage_str = f"{layer_summary.coverage_pct:.0%}"
        table.add_row(
            layer_summary.layer.value.capitalize(),
            str(layer_summary.total_functions),
            str(layer_summary.tested_functions),
            str(layer_summary.passed),
            str(layer_summary.failed),
            coverage_str,
        )

    console.print(table)

    # Print findings summary
    if report.total_findings > 0:
        console.print(
            f"\nFindings: {report.critical_count} critical, "
            f"{report.warning_count} warning, {report.info_count} info"
        )
    else:
        console.print("\nNo findings -- all layers passed cleanly.")


# ---------------------------------------------------------------------------
# Discovery layer — AI-powered formula audit
# ---------------------------------------------------------------------------

# Default path for pre-existing discovery findings (JSON).
_DISCOVERY_FINDINGS_PATH = Path("tests/audit/reference_data/discovery_findings.json")

# Severity-to-Rich-style mapping for colored output.
_SEVERITY_STYLES: dict[AuditSeverity, str] = {
    AuditSeverity.CRITICAL: "bold red",
    AuditSeverity.WARNING: "bold yellow",
    AuditSeverity.INFO: "bold blue",
}


def _load_discovery_findings(
    path: Path | None = None,
) -> list[AuditFinding]:
    """Load pre-existing discovery findings from a JSON file.

    The JSON file should contain a list of objects matching the
    ``AuditFinding`` schema. If the file does not exist or cannot
    be parsed, returns an empty list and logs a warning.

    Args:
        path: Path to the discovery findings JSON file. Defaults to
              ``_DISCOVERY_FINDINGS_PATH`` when ``None``.

    Returns:
        List of validated ``AuditFinding`` models.
    """
    resolved = path if path is not None else _DISCOVERY_FINDINGS_PATH
    if not resolved.exists():
        logger.debug("Discovery findings file not found: %s", resolved)
        return []

    try:
        raw_text = resolved.read_text(encoding="utf-8")
        raw_data: list[dict[str, object]] = json.loads(raw_text)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse discovery findings from %s: %s", resolved, exc)
        return []

    findings: list[AuditFinding] = []
    for item in raw_data:
        try:
            findings.append(AuditFinding.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping invalid finding entry: %s", exc)
    return findings


def _render_discovery_findings(findings: list[AuditFinding]) -> None:
    """Display discovery findings with severity-colored Rich output.

    Args:
        findings: List of ``AuditFinding`` models to render.
    """
    if not findings:
        console.print(
            Panel(
                "No discovery findings available.\n"
                "Run [bold cyan]/math-audit[/bold cyan] in Claude Code "
                "to invoke the quant-analyst discovery agent.",
                title="Discovery Layer",
                border_style="cyan",
            )
        )
        return

    # Summary counts
    critical = sum(1 for f in findings if f.severity == AuditSeverity.CRITICAL)
    warning = sum(1 for f in findings if f.severity == AuditSeverity.WARNING)
    info = sum(1 for f in findings if f.severity == AuditSeverity.INFO)

    # Findings table
    table = Table(title="Discovery Layer Findings")
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Severity", justify="center", width=10)
    table.add_column("Function", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Source", style="dim")

    for idx, finding in enumerate(findings, 1):
        severity_style = _SEVERITY_STYLES.get(finding.severity, "white")
        severity_text = Text(finding.severity.value.upper(), style=severity_style)
        table.add_row(
            str(idx),
            severity_text,
            finding.function_name,
            finding.description,
            finding.source or "--",
        )

    console.print(table)
    console.print(f"\nDiscovery totals: {critical} critical, {warning} warning, {info} info")


def _run_discovery() -> None:
    """Execute the discovery layer: load findings and display with Rich output.

    Prints guidance on how to invoke the ``/math-audit`` skill in Claude Code,
    then loads and displays any pre-existing findings from the JSON file.
    Never raises -- all errors are caught and logged as warnings.
    """
    try:
        console.print(
            Panel(
                "Run [bold cyan]/math-audit[/bold cyan] in Claude Code "
                "to invoke the quant-analyst discovery agent.\n\n"
                "The discovery layer uses AI to review mathematical functions\n"
                "for correctness issues, edge-case gaps, and undocumented\n"
                "approximations. Findings are advisory and require human review.",
                title="AI-Powered Discovery",
                border_style="cyan",
            )
        )

        findings = _load_discovery_findings()
        _render_discovery_findings(findings)

    except Exception:
        logger.warning("Discovery layer encountered an error", exc_info=True)
        err_console.print(
            "[yellow]Warning: Discovery layer failed. See logs for details.[/yellow]"
        )


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@audit_app.command("math")
def math_audit(
    correctness: bool = typer.Option(  # noqa: FBT001
        False, "--correctness", help="Run only the correctness layer"
    ),
    stability: bool = typer.Option(  # noqa: FBT001
        False, "--stability", help="Run only the stability layer"
    ),
    performance: bool = typer.Option(  # noqa: FBT001
        False, "--performance", help="Run only the performance layer"
    ),
    report: bool = typer.Option(  # noqa: FBT001
        False, "--report", help="Generate markdown audit report"
    ),
    discover: bool = typer.Option(  # noqa: FBT001
        False, "--discover", help="Run AI-powered discovery layer"
    ),
) -> None:
    """Run mathematical computation audit across selected layers."""
    asyncio.run(
        _math_audit_async(
            correctness=correctness,
            stability=stability,
            performance=performance,
            report=report,
            discover=discover,
        )
    )


async def _math_audit_async(
    *,
    correctness: bool,
    stability: bool,
    performance: bool,
    report: bool,
    discover: bool,
) -> None:
    """Execute audit layers and optionally generate a report.

    If no layer flags are specified, runs all 3 deterministic layers
    (correctness, stability, performance).
    """
    if discover:
        _run_discovery()
        return

    # Determine which layers to run
    no_layer_selected = not correctness and not stability and not performance
    layers_to_run: list[AuditLayer] = []
    if no_layer_selected or correctness:
        layers_to_run.append(AuditLayer.CORRECTNESS)
    if no_layer_selected or stability:
        layers_to_run.append(AuditLayer.STABILITY)
    if no_layer_selected or performance:
        layers_to_run.append(AuditLayer.PERFORMANCE)

    err_console.print(
        f"Running {len(layers_to_run)} audit layer(s) "
        f"against {MATH_FUNCTION_COUNT} mathematical functions...\n"
    )

    # Run each layer sequentially (subprocess-based, no async benefit)
    summaries: list[AuditLayerSummary] = []
    for layer in layers_to_run:
        layer_result = await asyncio.to_thread(_run_audit_layer, layer)
        summary = _build_layer_summary(layer_result, MATH_FUNCTION_COUNT)
        summaries.append(summary)

    audit_report = _build_report(summaries)

    # Display summary table
    _render_summary_table(audit_report)

    # Optionally generate markdown report
    if report:
        from tools.math_audit_report import generate_math_audit_report  # noqa: PLC0415

        md_content = generate_math_audit_report(audit_report)

        # Write report to disk as an artifact
        report_path = Path("math-audit-report.md")
        report_path.write_text(md_content, encoding="utf-8")
        console.print(f"\nReport written to [bold cyan]{report_path.resolve()}[/bold cyan]")

        # Also print to stdout for immediate review
        console.print("\n--- Markdown Report ---\n")
        console.print(md_content, highlight=False)
