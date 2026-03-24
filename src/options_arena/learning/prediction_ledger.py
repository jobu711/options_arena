"""Prediction scoring and attribution computation for the recommendation learning loop.

Scores predictions by comparing predicted direction against actual stock return
direction from collected contract outcomes.  Correctness rule:
  - BULLISH + positive return -> correct
  - BEARISH + negative return -> correct
  - NEUTRAL -> always incorrect (neutral predictions can't be validated)
  - stock_return_pct == 0.0 -> incorrect for all directions

Attribution computation groups scored predictions by source and condition bucket
to produce per-source and per-condition accuracy statistics.

All orchestration functions follow the never-raises contract.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from options_arena.data.repository import Repository
from options_arena.models.attribution import (
    AttributionReport,
    ConditionBucketAccuracy,
    ContractGuidance,
    Prediction,
    PredictionAccuracy,
    PredictionSource,
)
from options_arena.models.enums import SignalDirection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bucket constants for condition classifiers
# ---------------------------------------------------------------------------

MIN_SOURCE_SAMPLES: int = 10
MIN_CONDITION_SAMPLES: int = 20

ADX_BUCKETS: list[tuple[float, float, str]] = [
    (0, 20, "weak"),
    (20, 30, "moderate"),
    (30, 100, "strong"),
]
IV_RANK_BUCKETS: list[tuple[float, float, str]] = [
    (0, 30, "low"),
    (30, 70, "mid"),
    (70, 100, "high"),
]
ATR_PCT_BUCKETS: list[tuple[float, float, str]] = [
    (0, 1.5, "low"),
    (1.5, 3.0, "medium"),
    (3.0, 100, "high"),
]
RSI_BUCKETS: list[tuple[float, float, str]] = [
    (0, 30, "oversold"),
    (30, 70, "neutral"),
    (70, 100, "overbought"),
]


# ---------------------------------------------------------------------------
# Condition classifiers
# ---------------------------------------------------------------------------


def _classify_bucket(
    value: float | None,
    buckets: list[tuple[float, float, str]],
) -> str | None:
    """Classify a value into a bucket label.

    Parameters
    ----------
    value
        The value to classify.  ``None`` yields ``None`` (excluded).
    buckets
        List of ``(low, high, label)`` tuples.  Lower bound inclusive,
        upper bound exclusive — except the last bucket which is inclusive
        on both ends.

    Returns
    -------
    str | None
        The bucket label, or ``None`` if the value is ``None`` or non-finite.
    """
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    last_idx = len(buckets) - 1
    for idx, (low, high, label) in enumerate(buckets):
        if idx == last_idx:
            # Last bucket: inclusive on both ends
            if low <= value <= high:
                return label
        else:
            if low <= value < high:
                return label
    return None


def _classify_adx(adx: float | None) -> str | None:
    """Classify ADX into weak/moderate/strong bucket."""
    return _classify_bucket(adx, ADX_BUCKETS)


def _classify_iv_rank(iv_rank: float | None) -> str | None:
    """Classify IV Rank into low/mid/high bucket."""
    return _classify_bucket(iv_rank, IV_RANK_BUCKETS)


def _classify_atr_pct(atr_pct: float | None) -> str | None:
    """Classify ATR% into low/medium/high bucket."""
    return _classify_bucket(atr_pct, ATR_PCT_BUCKETS)


def _classify_rsi(rsi: float | None) -> str | None:
    """Classify RSI into oversold/neutral/overbought bucket."""
    return _classify_bucket(rsi, RSI_BUCKETS)


# ---------------------------------------------------------------------------
# Source-level accuracy
# ---------------------------------------------------------------------------


def _compute_source_accuracy(predictions: list[Prediction]) -> list[PredictionAccuracy]:
    """Group scored predictions by source, compute accuracy per source.

    Parameters
    ----------
    predictions
        Predictions to analyze.  Only those with ``was_correct is not None``
        are included.

    Returns
    -------
    list[PredictionAccuracy]
        One entry per source that has at least one scored prediction.
    """
    by_source: dict[PredictionSource, list[bool]] = defaultdict(list)
    for p in predictions:
        if p.was_correct is not None:
            by_source[p.source].append(p.was_correct)

    result: list[PredictionAccuracy] = []
    for source, outcomes in sorted(by_source.items(), key=lambda x: x[0].value):
        total = len(outcomes)
        correct = sum(outcomes)
        accuracy = correct / total if total > 0 else 0.0
        result.append(
            PredictionAccuracy(
                source=source,
                total=total,
                correct=correct,
                accuracy=accuracy,
                sample_sufficient=total >= MIN_SOURCE_SAMPLES,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Condition-level accuracy
# ---------------------------------------------------------------------------

# Maps dimension name to (accessor attribute, classifier function)
_CONDITION_CLASSIFIERS: list[tuple[str, str, object]] = [
    ("adx", "adx", _classify_adx),
    ("iv_rank", "iv_rank", _classify_iv_rank),
    ("atr_pct", "atr_pct", _classify_atr_pct),
    ("rsi", "rsi", _classify_rsi),
]


def _compute_condition_accuracy(
    predictions: list[Prediction],
) -> list[ConditionBucketAccuracy]:
    """Group scored predictions by source + condition bucket, compute accuracy.

    For each scored prediction, classifies all 4 dimensions (ADX, IV Rank,
    ATR%, RSI).  Groups by ``(source, "dimension:label")`` and computes
    accuracy.  Groups with fewer than ``MIN_CONDITION_SAMPLES`` are excluded.

    Parameters
    ----------
    predictions
        Predictions to analyze.  Only those with ``was_correct is not None``
        are included.

    Returns
    -------
    list[ConditionBucketAccuracy]
        One entry per source+condition pair meeting the minimum sample threshold.
    """
    # Key: (source, condition_label) -> list of was_correct booleans
    groups: dict[tuple[PredictionSource, str], list[bool]] = defaultdict(list)

    for p in predictions:
        if p.was_correct is None:
            continue

        for dim_name, attr_name, classifier_fn in _CONDITION_CLASSIFIERS:
            raw_value = getattr(p, attr_name)
            label = classifier_fn(raw_value)  # type: ignore[operator]
            if label is not None:
                key = (p.source, f"{dim_name}:{label}")
                groups[key].append(p.was_correct)

    result: list[ConditionBucketAccuracy] = []
    sorted_groups = sorted(groups.items(), key=lambda x: (x[0][0].value, x[0][1]))
    for (source, condition), outcomes in sorted_groups:
        total = len(outcomes)
        if total < MIN_CONDITION_SAMPLES:
            continue
        correct = sum(outcomes)
        accuracy = correct / total if total > 0 else 0.0
        result.append(
            ConditionBucketAccuracy(
                source=source,
                condition=condition,
                total=total,
                correct=correct,
                accuracy=accuracy,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Top-level attribution computation (pure function, no DB access)
# ---------------------------------------------------------------------------


def compute_attribution(
    predictions: list[Prediction],
    contract_guidance: ContractGuidance | None = None,
) -> AttributionReport:
    """Compute attribution report from predictions.  Pure function, no DB access.

    Parameters
    ----------
    predictions
        Full list of predictions (scored and unscored).
    contract_guidance
        Optional learned contract parameters to include in the report.

    Returns
    -------
    AttributionReport
        Report with source accuracy, condition accuracy, and totals.
    """
    scored = [p for p in predictions if p.was_correct is not None]

    source_accuracy = _compute_source_accuracy(predictions)
    condition_accuracy = _compute_condition_accuracy(predictions)

    # Count distinct recommendation_ids for total_recommendations
    rec_ids = {p.recommendation_id for p in predictions if p.recommendation_id is not None}

    return AttributionReport(
        window_days=0,
        total_recommendations=len(rec_ids),
        total_outcomes=len(scored),
        source_accuracy=source_accuracy,
        condition_accuracy=condition_accuracy,
        contract_guidance=contract_guidance,
    )


# ---------------------------------------------------------------------------
# Pure direction correctness logic (no I/O)
# ---------------------------------------------------------------------------


def _direction_was_correct(predicted: SignalDirection, stock_return_pct: float) -> bool:
    """Check if predicted direction matched actual stock return.

    Parameters
    ----------
    predicted
        The predicted signal direction.
    stock_return_pct
        The actual stock return percentage from outcome collection.

    Returns
    -------
    bool
        ``True`` if the prediction matched the actual market direction.
    """
    if not math.isfinite(stock_return_pct):
        return False
    if stock_return_pct == 0.0:
        return False
    if predicted is SignalDirection.NEUTRAL:
        return False
    if predicted is SignalDirection.BULLISH:
        return stock_return_pct > 0.0
    if predicted is SignalDirection.BEARISH:
        return stock_return_pct < 0.0
    return False


# ---------------------------------------------------------------------------
# Scoring by recommendation_id
# ---------------------------------------------------------------------------


async def score_predictions_for_recommendation(
    repo: Repository,
    recommendation_id: int,
) -> int:
    """Score all predictions for a recommendation based on outcome direction.

    Joins through ``recommendation_results`` -> ``recommended_contracts`` ->
    ``contract_outcomes`` to determine the stock return for the recommendation's
    ticker, then calls ``repo.score_predictions()`` for each distinct direction.

    Parameters
    ----------
    repo
        Repository instance for DB reads and writes.
    recommendation_id
        The ``recommendation_results.id`` whose predictions to score.

    Returns
    -------
    int
        Number of predictions scored (0 if no outcomes found).
    """
    conn = repo._db.conn  # noqa: SLF001

    # Get the average stock_return_pct for this recommendation's contracts.
    # Join: recommendation_results -> recommended_contracts (via scan_run_id + ticker)
    #       -> contract_outcomes (via recommended_contract_id)
    sql = (
        "SELECT AVG(co.stock_return_pct) AS avg_stock_return "
        "FROM recommendation_results rr "
        "JOIN recommended_contracts rc "
        "  ON rc.scan_run_id = rr.scan_run_id AND rc.ticker = rr.ticker "
        "JOIN contract_outcomes co "
        "  ON co.recommended_contract_id = rc.id "
        "WHERE rr.id = ? "
        "  AND co.stock_return_pct IS NOT NULL"
    )
    async with conn.execute(sql, (recommendation_id,)) as cursor:
        row = await cursor.fetchone()

    if row is None or row["avg_stock_return"] is None:
        logger.debug(
            "No outcomes found for recommendation_id=%d, nothing to score",
            recommendation_id,
        )
        return 0

    avg_stock_return = float(row["avg_stock_return"])
    if not math.isfinite(avg_stock_return):
        logger.warning(
            "Non-finite avg stock return for recommendation_id=%d, skipping",
            recommendation_id,
        )
        return 0

    # Get all unscored predictions for this recommendation
    pred_sql = (
        "SELECT DISTINCT predicted_direction FROM predictions "
        "WHERE recommendation_id = ? AND was_correct IS NULL"
    )
    async with conn.execute(pred_sql, (recommendation_id,)) as cursor:
        direction_rows = await cursor.fetchall()

    if not direction_rows:
        logger.debug(
            "No unscored predictions for recommendation_id=%d",
            recommendation_id,
        )
        return 0

    # Determine correctness based on stock return direction and score all at once
    # We need per-direction scoring because different desk predictions may have
    # different predicted_directions.  However, repo.score_predictions() applies
    # a single was_correct to ALL predictions for that recommendation_id.
    # We compute per-prediction correctness via SQL instead.
    total_scored = 0
    for drow in direction_rows:
        direction = SignalDirection(str(drow["predicted_direction"]))
        was_correct = _direction_was_correct(direction, avg_stock_return)

        update_sql = (
            "UPDATE predictions SET was_correct = ? "
            "WHERE recommendation_id = ? AND predicted_direction = ? "
            "AND was_correct IS NULL"
        )
        cursor = await conn.execute(
            update_sql,
            (int(was_correct), recommendation_id, direction.value),
        )
        total_scored += cursor.rowcount

    await conn.commit()

    logger.info(
        "Scored %d predictions for recommendation_id=%d (avg_stock_return=%.2f%%)",
        total_scored,
        recommendation_id,
        avg_stock_return,
    )
    return total_scored


# ---------------------------------------------------------------------------
# Scoring by scan_run_id
# ---------------------------------------------------------------------------


async def score_predictions_for_scan(
    repo: Repository,
    scan_run_id: int,
) -> int:
    """Score scan predictions based on outcome direction.

    Groups predictions by ticker, determines per-ticker stock direction from
    contract outcomes, and scores accordingly.

    Parameters
    ----------
    repo
        Repository instance for DB reads and writes.
    scan_run_id
        The ``scan_runs.id`` whose predictions to score.

    Returns
    -------
    int
        Total number of predictions scored across all tickers.
    """
    conn = repo._db.conn  # noqa: SLF001

    # Get per-ticker average stock return from outcomes linked to this scan run
    sql = (
        "SELECT rc.ticker, AVG(co.stock_return_pct) AS avg_stock_return "
        "FROM recommended_contracts rc "
        "JOIN contract_outcomes co "
        "  ON co.recommended_contract_id = rc.id "
        "WHERE rc.scan_run_id = ? "
        "  AND co.stock_return_pct IS NOT NULL "
        "GROUP BY rc.ticker"
    )
    async with conn.execute(sql, (scan_run_id,)) as cursor:
        outcome_rows = await cursor.fetchall()

    if not outcome_rows:
        logger.debug(
            "No outcomes found for scan_run_id=%d, nothing to score",
            scan_run_id,
        )
        return 0

    total_scored = 0

    for orow in outcome_rows:
        ticker = str(orow["ticker"])
        avg_return = float(orow["avg_stock_return"])
        if not math.isfinite(avg_return):
            logger.warning(
                "Non-finite avg stock return for scan_run_id=%d ticker=%s, skipping",
                scan_run_id,
                ticker,
            )
            continue

        # Get distinct predicted directions for unscored predictions for this ticker
        pred_sql = (
            "SELECT DISTINCT predicted_direction FROM predictions "
            "WHERE scan_run_id = ? AND ticker = ? AND was_correct IS NULL"
        )
        async with conn.execute(pred_sql, (scan_run_id, ticker)) as cursor:
            direction_rows = await cursor.fetchall()

        for drow in direction_rows:
            direction = SignalDirection(str(drow["predicted_direction"]))
            was_correct = _direction_was_correct(direction, avg_return)

            update_sql = (
                "UPDATE predictions SET was_correct = ? "
                "WHERE scan_run_id = ? AND ticker = ? AND predicted_direction = ? "
                "AND was_correct IS NULL"
            )
            cursor = await conn.execute(
                update_sql,
                (int(was_correct), scan_run_id, ticker, direction.value),
            )
            total_scored += cursor.rowcount

    await conn.commit()

    logger.info(
        "Scored %d scan predictions for scan_run_id=%d",
        total_scored,
        scan_run_id,
    )
    return total_scored


# ---------------------------------------------------------------------------
# Top-level orchestration (never-raises)
# ---------------------------------------------------------------------------


async def run_prediction_scoring(repo: Repository) -> None:
    """Top-level never-raises orchestration wrapper for prediction scoring.

    Finds recommendations and scan runs with recently collected outcomes that
    have unscored predictions, then scores them.

    Parameters
    ----------
    repo
        Repository instance for DB reads and writes.
    """
    try:
        await _run_scoring_pipeline(repo)
    except Exception:
        logger.exception("Prediction scoring failed")


async def _run_scoring_pipeline(repo: Repository) -> None:
    """Internal scoring pipeline (may raise)."""
    conn = repo._db.conn  # noqa: SLF001

    # Find recommendation_ids with unscored predictions that have outcomes available
    rec_sql = (
        "SELECT DISTINCT p.recommendation_id "
        "FROM predictions p "
        "JOIN recommendation_results rr ON rr.id = p.recommendation_id "
        "JOIN recommended_contracts rc "
        "  ON rc.scan_run_id = rr.scan_run_id AND rc.ticker = rr.ticker "
        "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
        "WHERE p.was_correct IS NULL "
        "  AND p.recommendation_id IS NOT NULL "
        "  AND co.stock_return_pct IS NOT NULL"
    )
    async with conn.execute(rec_sql) as cursor:
        rec_rows = await cursor.fetchall()

    rec_total = 0
    for row in rec_rows:
        rec_id = int(row["recommendation_id"])
        try:
            count = await score_predictions_for_recommendation(repo, rec_id)
            rec_total += count
        except Exception:
            logger.warning(
                "Failed to score predictions for recommendation_id=%d",
                rec_id,
                exc_info=True,
            )

    # Find scan_run_ids with unscored predictions that have outcomes available
    scan_sql = (
        "SELECT DISTINCT p.scan_run_id "
        "FROM predictions p "
        "JOIN recommended_contracts rc "
        "  ON rc.scan_run_id = p.scan_run_id AND rc.ticker = p.ticker "
        "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
        "WHERE p.was_correct IS NULL "
        "  AND p.scan_run_id IS NOT NULL "
        "  AND p.recommendation_id IS NULL "
        "  AND co.stock_return_pct IS NOT NULL"
    )
    async with conn.execute(scan_sql) as cursor:
        scan_rows = await cursor.fetchall()

    scan_total = 0
    for row in scan_rows:
        scan_id = int(row["scan_run_id"])
        try:
            count = await score_predictions_for_scan(repo, scan_id)
            scan_total += count
        except Exception:
            logger.warning(
                "Failed to score predictions for scan_run_id=%d",
                scan_id,
                exc_info=True,
            )

    if rec_total or scan_total:
        logger.info(
            "Prediction scoring complete: %d recommendation + %d scan predictions scored",
            rec_total,
            scan_total,
        )
    else:
        logger.debug("No predictions needed scoring")
