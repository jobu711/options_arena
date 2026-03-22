"""Eval runner — orchestrates graders, computes pass@k, compares baselines.

``run_eval_check()`` is the primary entry point. It loads eval definitions,
runs the appropriate grader for each, computes pass@1 and pass@3 metrics,
and compares against stored baselines to produce a SHIP/NEEDS_WORK/BLOCKED
verdict.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from options_arena.data import Repository
from options_arena.models.config import EvalConfig
from options_arena.models.enums import DeskType, EvalVerdict, GraderType
from options_arena.models.eval import EvalBaseline, EvalDefinition, EvalReport, EvalRun

from .graders import CodeGrader, GraderResult, ModelGrader

logger = logging.getLogger(__name__)


async def run_eval_check(
    repo: Repository,
    config: EvalConfig,
    *,
    desk_filter: DeskType | None = None,
) -> EvalReport:
    """Run all eval definitions and produce a report.

    Parameters
    ----------
    repo
        Repository for loading definitions and persisting runs.
    config
        Eval configuration (eval_dir, pass_at_k, etc.).
    desk_filter
        If provided, only run evals targeting this desk.

    Returns
    -------
    EvalReport
        Aggregated results with pass@k metrics and verdict.
    """
    definitions = await repo.get_eval_definitions()
    if desk_filter is not None:
        definitions = [
            d for d in definitions
            if d.target_desk == desk_filter or d.target_desk is None
        ]

    if not definitions:
        logger.warning("No eval definitions found")
        return EvalReport(
            runs=[],
            pass_at_1=0.0,
            pass_at_3=0.0,
            regressions=[],
            verdict=EvalVerdict.NEEDS_WORK,
        )

    code_grader = CodeGrader()
    model_grader = ModelGrader()
    runs: list[EvalRun] = []
    pass_at_k = max(1, config.pass_at_k)

    for definition in definitions:
        start_ms = _now_ms()
        successes = 0

        for _attempt in range(pass_at_k):
            result = _run_single_eval(definition, code_grader, model_grader)
            if result.passed:
                successes += 1

        elapsed_ms = _now_ms() - start_ms
        passed = successes >= 1  # pass@1: at least one success

        run = EvalRun(
            eval_name=definition.name,
            timestamp=datetime.now(UTC),
            passed=passed,
            attempts=pass_at_k,
            successes=successes,
            model_used=(
                "code_grader"
                if definition.grader_type == GraderType.CODE
                else "model_grader"
            ),
            duration_ms=elapsed_ms,
            details=json.dumps({
                "successes": successes,
                "attempts": pass_at_k,
                "grader_type": definition.grader_type.value,
            }),
        )
        runs.append(run)

        # Persist the run
        await repo.save_eval_run(run)

    # Compute pass@k metrics
    pass_at_1 = _compute_pass_at_1(runs)
    pass_at_3 = _compute_pass_at_3(runs, pass_at_k)

    # Compare against baseline
    baseline = await _load_baseline(repo)
    regressions = _find_regressions(runs, baseline)

    verdict = _compute_verdict(pass_at_1, regressions)

    return EvalReport(
        runs=runs,
        pass_at_1=pass_at_1,
        pass_at_3=pass_at_3,
        regressions=regressions,
        verdict=verdict,
    )


async def save_baseline(
    repo: Repository,
    report: EvalReport,
) -> EvalBaseline:
    """Save the current eval results as the baseline for future comparison.

    Parameters
    ----------
    repo
        Repository (currently baselines stored in-memory; future: SQLite).
    report
        The eval report to use as baseline.

    Returns
    -------
    EvalBaseline
        The saved baseline.
    """
    eval_results = {run.eval_name: run.passed for run in report.runs}
    baseline = EvalBaseline(
        eval_results=eval_results,
        pass_at_1=report.pass_at_1,
        pass_at_3=report.pass_at_3,
        timestamp=datetime.now(UTC),
    )
    return baseline


def _run_single_eval(
    definition: EvalDefinition,
    code_grader: CodeGrader,
    model_grader: ModelGrader,
) -> GraderResult:
    """Run a single eval attempt.

    For code and model graders, we need assessment data from the fixture.
    Since fixtures are file-based and may not exist yet during initial setup,
    return a pass result for definitions with missing fixtures.
    """
    fixture_path = Path(definition.market_context_fixture)

    if not fixture_path.exists():
        logger.debug(
            "Fixture not found for eval %s: %s",
            definition.name,
            fixture_path,
        )
        return GraderResult(
            passed=False,
            details=json.dumps({"error": f"fixture not found: {fixture_path}"}),
        )

    try:
        fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load fixture for %s: %s", definition.name, exc)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": f"fixture load error: {exc}"}),
        )

    # Dispatch to appropriate grader
    match definition.grader_type:
        case GraderType.CODE:
            return _run_code_eval(fixture_data, definition, code_grader)
        case GraderType.MODEL:
            return _run_model_eval(fixture_data, definition, model_grader)
        case GraderType.OUTCOME:
            return _run_outcome_eval(fixture_data, definition)


def _run_code_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
    grader: CodeGrader,
) -> GraderResult:
    """Run a code-based eval from fixture data."""
    from options_arena.models.recommendation import DomainAssessment  # noqa: PLC0415

    try:
        assessment_data = fixture_data.get("assessment")
        if assessment_data is None:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no 'assessment' key in fixture"}),
            )
        assessment = DomainAssessment.model_validate(assessment_data)
        return grader.grade_assessment(assessment, definition)
    except Exception as exc:
        logger.warning("Code eval %s failed: %s", definition.name, exc)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": str(exc)}),
        )


def _run_model_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
    grader: ModelGrader,
) -> GraderResult:
    """Run a model-based (heuristic) eval from fixture data."""
    from options_arena.models.recommendation import DomainAssessment  # noqa: PLC0415

    try:
        assessment_data = fixture_data.get("assessment")
        if assessment_data is None:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no 'assessment' key in fixture"}),
            )
        assessment = DomainAssessment.model_validate(assessment_data)
        return grader.grade_assessment(assessment, definition)
    except Exception as exc:
        logger.warning("Model eval %s failed: %s", definition.name, exc)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": str(exc)}),
        )


def _run_outcome_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
) -> GraderResult:
    """Run an outcome-based eval from fixture data."""
    from options_arena.evals.graders import OutcomeGrader, OutcomeRecord  # noqa: PLC0415
    from options_arena.models.enums import SignalDirection  # noqa: PLC0415

    try:
        outcomes_data = fixture_data.get("outcomes", [])
        if not outcomes_data:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no 'outcomes' key in fixture"}),
            )

        outcomes = [
            OutcomeRecord(
                direction=SignalDirection(o["direction"]),
                confidence=float(o["confidence"]),
                pnl_pct=float(o["pnl_pct"]),
            )
            for o in outcomes_data
        ]

        grader = OutcomeGrader()
        return grader.grade_calibration(outcomes, definition)
    except Exception as exc:
        logger.warning("Outcome eval %s failed: %s", definition.name, exc)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": str(exc)}),
        )


def _compute_pass_at_1(runs: list[EvalRun]) -> float:
    """Compute pass@1: fraction of evals that passed on first attempt."""
    if not runs:
        return 0.0
    passed = sum(1 for r in runs if r.passed)
    return passed / len(runs)


def _compute_pass_at_3(runs: list[EvalRun], k: int) -> float:
    """Compute pass@k: fraction of evals with at least one success in k attempts."""
    if not runs:
        return 0.0
    passed = sum(1 for r in runs if r.successes >= 1)
    return passed / len(runs)


async def _load_baseline(repo: Repository) -> EvalBaseline | None:
    """Load the most recent baseline from eval history.

    Constructs a baseline from the previous runs stored in the database.
    Returns None if no previous runs exist.
    """
    latest_runs = await repo.get_latest_eval_runs()
    if not latest_runs:
        return None

    eval_results = {run.eval_name: run.passed for run in latest_runs}
    passed_count = sum(1 for r in latest_runs if r.passed)
    total = len(latest_runs)

    return EvalBaseline(
        eval_results=eval_results,
        pass_at_1=passed_count / total if total > 0 else 0.0,
        pass_at_3=passed_count / total if total > 0 else 0.0,
        timestamp=max(r.timestamp for r in latest_runs),
    )


def _find_regressions(
    runs: list[EvalRun],
    baseline: EvalBaseline | None,
) -> list[str]:
    """Find evals that regressed compared to baseline."""
    if baseline is None:
        return []

    regressions: list[str] = []
    for run in runs:
        baseline_passed = baseline.eval_results.get(run.eval_name)
        if baseline_passed is True and not run.passed:
            regressions.append(run.eval_name)
    return regressions


def _compute_verdict(
    pass_at_1: float,
    regressions: list[str],
) -> EvalVerdict:
    """Compute the overall verdict from pass rate and regressions."""
    if len(regressions) > 0:
        return EvalVerdict.BLOCKED
    if pass_at_1 >= 0.8:  # noqa: PLR2004
        return EvalVerdict.SHIP
    return EvalVerdict.NEEDS_WORK


def _now_ms() -> int:
    """Current time in milliseconds (monotonic)."""
    return int(time.monotonic() * 1000)
