"""CLI audit subcommand group: mathematical computation audit tools.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Audit layers are invoked via ``subprocess.run()``
to run pytest with the appropriate marker.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import subprocess
import sys
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

from options_arena.cli.app import app
from options_arena.models.audit import AuditFinding, AuditLayerSummary, AuditReport
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
            import re  # noqa: PLC0415

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

    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
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
        console.print("Discovery requires /math-audit skill")
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

    # Get total function count from registry
    try:
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY  # noqa: PLC0415

        total_functions = len(MATH_FUNCTION_REGISTRY)
    except ImportError:
        logger.warning("Could not import MATH_FUNCTION_REGISTRY, using default count")
        total_functions = 87

    err_console.print(
        f"Running {len(layers_to_run)} audit layer(s) "
        f"against {total_functions} mathematical functions...\n"
    )

    # Run each layer sequentially (subprocess-based, no async benefit)
    summaries: list[AuditLayerSummary] = []
    for layer in layers_to_run:
        layer_result = await asyncio.to_thread(_run_audit_layer, layer)
        summary = _build_layer_summary(layer_result, total_functions)
        summaries.append(summary)

    audit_report = _build_report(summaries)

    # Display summary table
    _render_summary_table(audit_report)

    # Optionally generate markdown report
    if report:
        from tools.math_audit_report import generate_math_audit_report  # noqa: PLC0415

        md_content = generate_math_audit_report(audit_report)
        console.print("\n--- Markdown Report ---\n")
        console.print(md_content, highlight=False)
