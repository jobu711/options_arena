"""Eval runner — orchestrates graders, computes pass@k, compares baselines.

``run_eval_check()`` is the primary entry point. It loads eval definitions,
runs the appropriate grader for each, computes pass@1 and pass@3 metrics,
and compares against stored baselines to produce a SHIP/NEEDS_WORK/BLOCKED
verdict.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from options_arena.data import Repository
from options_arena.models import (
    EvalBaseline,
    EvalConfig,
    EvalDefinition,
    EvalReport,
    EvalRun,
)
from options_arena.models.enums import DeskType, EvalVerdict, GraderType, SignalDirection
from options_arena.models.eval import EvalOutcome

from .graders import CodeGrader, GraderResult, ModelGrader

logger = logging.getLogger(__name__)

# Maximum fixture file size (10 MB) — defense against DoS via large files
_MAX_FIXTURE_BYTES = 10 * 1024 * 1024

# Project root for fixture path confinement
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _sanitize_error(exc: Exception) -> str:
    """Sanitize exception message for storage — strip file paths."""
    msg = type(exc).__name__
    exc_str = str(exc)
    # Strip anything that looks like a file path
    exc_str = exc_str.replace(str(_PROJECT_ROOT), "<project>")
    # Truncate to prevent oversized details
    if len(exc_str) > 200:  # noqa: PLR2004
        exc_str = exc_str[:200] + "..."
    return f"{msg}: {exc_str}"


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
            d for d in definitions if d.target_desk == desk_filter or d.target_desk is None
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
        first_attempt_passed = False
        successes = 0

        for attempt_idx in range(pass_at_k):
            result = await asyncio.to_thread(
                _run_single_eval, definition, code_grader, model_grader
            )
            if result.passed:
                successes += 1
                if attempt_idx == 0:
                    first_attempt_passed = True

        elapsed_ms = _now_ms() - start_ms

        run = EvalRun(
            eval_name=definition.name,
            timestamp=datetime.now(UTC),
            passed=first_attempt_passed,
            attempts=pass_at_k,
            successes=successes,
            model_used=(
                "code_grader" if definition.grader_type == GraderType.CODE else "model_grader"
            ),
            duration_ms=elapsed_ms,
            details=json.dumps(
                {
                    "successes": successes,
                    "attempts": pass_at_k,
                    "first_attempt_passed": first_attempt_passed,
                    "grader_type": definition.grader_type.value,
                }
            ),
        )
        runs.append(run)

        # Persist the run
        await repo.save_eval_run(run)

    # Compute pass@k metrics
    pass_at_1 = _compute_pass_at_1(runs)
    pass_at_3 = _compute_pass_at_k(runs, pass_at_k)

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


def _run_single_eval(
    definition: EvalDefinition,
    code_grader: CodeGrader,
    model_grader: ModelGrader,
) -> GraderResult:
    """Run a single eval attempt.

    For code and model graders, we need assessment data from the fixture.
    Since fixtures are file-based and may not exist yet during initial setup,
    return a fail result for definitions with missing fixtures.
    """
    fixture_path = (_PROJECT_ROOT / definition.market_context_fixture).resolve()

    # Path confinement — reject paths outside project root
    if not fixture_path.is_relative_to(_PROJECT_ROOT):
        return GraderResult(
            passed=False,
            details=json.dumps({"error": "fixture path outside project root"}),
        )

    if not fixture_path.exists():
        logger.debug(
            "Fixture not found for eval %s: %s",
            definition.name,
            fixture_path.name,
        )
        return GraderResult(
            passed=False,
            details=json.dumps({"error": f"fixture not found: {fixture_path.name}"}),
        )

    # File size guard — reject oversized fixtures
    if fixture_path.stat().st_size > _MAX_FIXTURE_BYTES:
        return GraderResult(
            passed=False,
            details=json.dumps({"error": "fixture file exceeds 10 MB limit"}),
        )

    try:
        fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to load fixture for %s: %s",
            definition.name,
            type(exc).__name__,
        )
        return GraderResult(
            passed=False,
            details=json.dumps({"error": _sanitize_error(exc)}),
        )

    # Dispatch to appropriate grader
    match definition.grader_type:
        case GraderType.CODE:
            return _run_code_eval(fixture_data, definition, code_grader)
        case GraderType.MODEL:
            return _run_model_eval(fixture_data, definition, model_grader)
        case GraderType.OUTCOME:
            return _run_outcome_eval(fixture_data, definition)
        case _:
            return GraderResult(
                passed=False,
                details=json.dumps(
                    {
                        "error": f"unknown grader type: {definition.grader_type}",
                    }
                ),
            )


def _run_code_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
    grader: CodeGrader,
) -> GraderResult:
    """Run a code-based eval from fixture data."""
    from options_arena.models import DomainAssessment  # noqa: PLC0415

    try:
        assessment_data = fixture_data.get("assessment")
        if assessment_data is None:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no 'assessment' key in fixture"}),
            )
        assessment = DomainAssessment.model_validate(assessment_data)
        return grader.grade_assessment(assessment, definition)
    except (ValueError, KeyError, ValidationError) as exc:
        logger.warning("Code eval %s failed: %s", definition.name, type(exc).__name__)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": _sanitize_error(exc)}),
        )


def _run_model_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
    grader: ModelGrader,
) -> GraderResult:
    """Run a model-based (heuristic) eval from fixture data."""
    from options_arena.models import DomainAssessment  # noqa: PLC0415

    try:
        assessment_data = fixture_data.get("assessment")
        if assessment_data is None:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no 'assessment' key in fixture"}),
            )
        assessment = DomainAssessment.model_validate(assessment_data)
        return grader.grade_assessment(assessment, definition)
    except (ValueError, KeyError, ValidationError) as exc:
        logger.warning("Model eval %s failed: %s", definition.name, type(exc).__name__)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": _sanitize_error(exc)}),
        )


def _run_outcome_eval(
    fixture_data: dict[str, object],
    definition: EvalDefinition,
) -> GraderResult:
    """Run an outcome-based eval from fixture data."""
    from options_arena.evals.graders import OutcomeGrader, OutcomeRecord  # noqa: PLC0415

    try:
        raw_outcomes = fixture_data.get("outcomes", [])
        if not isinstance(raw_outcomes, list) or not raw_outcomes:
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
            for o in raw_outcomes
        ]

        grader = OutcomeGrader()
        return grader.grade_calibration(outcomes, definition)
    except (ValueError, KeyError, ValidationError) as exc:
        logger.warning("Outcome eval %s failed: %s", definition.name, type(exc).__name__)
        return GraderResult(
            passed=False,
            details=json.dumps({"error": _sanitize_error(exc)}),
        )


def _compute_pass_at_1(runs: list[EvalRun]) -> float:
    """Compute pass@1: fraction of evals that passed on first attempt."""
    if not runs:
        return 0.0
    passed = sum(1 for r in runs if r.passed)
    return passed / len(runs)


def _compute_pass_at_k(runs: list[EvalRun], k: int) -> float:
    """Compute pass@k: fraction of evals with at least one success in k attempts.

    Uses the unbiased estimator: 1 - C(n-c, k) / C(n, k)
    where n = total attempts, c = successes.
    """
    if not runs or k < 1:
        return 0.0
    total_pass = 0
    for r in runs:
        n = r.attempts
        c = r.successes
        if c >= k:
            total_pass += 1
        elif n <= 0 or c <= 0:
            pass  # no successes
        else:
            # 1 - C(n-c, k) / C(n, k)
            numerator = math.comb(n - c, k)
            denominator = math.comb(n, k)
            if denominator > 0:
                pass_k = 1.0 - numerator / denominator
                if pass_k > 0.5:  # noqa: PLR2004
                    total_pass += 1
    return total_pass / len(runs)


async def _load_baseline(repo: Repository) -> EvalBaseline | None:
    """Load the most recent baseline from eval history.

    Constructs a baseline from the previous runs stored in the database.
    Returns None if no previous runs exist.
    """
    latest_runs = await repo.get_latest_eval_runs()
    if not latest_runs:
        return None

    eval_results = [EvalOutcome(eval_name=run.eval_name, passed=run.passed) for run in latest_runs]
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

    baseline_map = {o.eval_name: o.passed for o in baseline.eval_results}
    regressions: list[str] = []
    for run in runs:
        baseline_passed = baseline_map.get(run.eval_name)
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
