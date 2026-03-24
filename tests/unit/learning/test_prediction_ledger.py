"""Tests for prediction scoring and attribution in learning/prediction_ledger.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from options_arena.learning.prediction_ledger import (
    _classify_adx,
    _classify_atr_pct,
    _classify_iv_rank,
    _classify_rsi,
    _direction_was_correct,
    compute_attribution,
    run_prediction_scoring,
    score_predictions_for_recommendation,
    score_predictions_for_scan,
)
from options_arena.models.attribution import PredictionSource
from options_arena.models.enums import SignalDirection
from tests.factories import make_prediction

# ---------------------------------------------------------------------------
# _direction_was_correct — pure logic tests
# ---------------------------------------------------------------------------


class TestDirectionCorrectness:
    @pytest.mark.parametrize(
        ("direction", "return_pct", "expected"),
        [
            (SignalDirection.BULLISH, 5.2, True),
            (SignalDirection.BULLISH, -3.1, False),
            (SignalDirection.BEARISH, -2.0, True),
            (SignalDirection.BEARISH, 4.0, False),
            (SignalDirection.NEUTRAL, 5.0, False),
            (SignalDirection.NEUTRAL, -5.0, False),
            (SignalDirection.BULLISH, 0.0, False),
            (SignalDirection.BEARISH, 0.0, False),
            (SignalDirection.NEUTRAL, 0.0, False),
        ],
        ids=[
            "bullish_positive",
            "bullish_negative",
            "bearish_negative",
            "bearish_positive",
            "neutral_positive",
            "neutral_negative",
            "bullish_zero",
            "bearish_zero",
            "neutral_zero",
        ],
    )
    def test_direction_correctness(
        self,
        direction: SignalDirection,
        return_pct: float,
        expected: bool,
    ) -> None:
        """Verify correctness logic for all direction x return combinations."""
        assert _direction_was_correct(direction, return_pct) is expected

    def test_non_finite_returns_false(self) -> None:
        """NaN and Inf stock returns always produce False."""
        assert _direction_was_correct(SignalDirection.BULLISH, float("nan")) is False
        assert _direction_was_correct(SignalDirection.BEARISH, float("inf")) is False
        assert _direction_was_correct(SignalDirection.BULLISH, float("-inf")) is False

    def test_tiny_positive_return_is_bullish_correct(self) -> None:
        """Very small positive return still counts as bullish correct."""
        assert _direction_was_correct(SignalDirection.BULLISH, 0.0001) is True

    def test_tiny_negative_return_is_bearish_correct(self) -> None:
        """Very small negative return still counts as bearish correct."""
        assert _direction_was_correct(SignalDirection.BEARISH, -0.0001) is True


# ---------------------------------------------------------------------------
# Helper to build a mock repo with a mock DB connection
# ---------------------------------------------------------------------------


def _make_mock_row(mapping: dict[str, object]) -> MagicMock:
    """Create a mock sqlite3.Row-like object supporting dict-style access."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: mapping[key]
    return row


class _MockCursor:
    """Async context manager wrapping a list of rows for fetchall/fetchone."""

    def __init__(self, rows: list[MagicMock], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    async def __aenter__(self) -> _MockCursor:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def fetchall(self) -> list[MagicMock]:
        return self._rows

    async def fetchone(self) -> MagicMock | None:
        return self._rows[0] if self._rows else None


def _make_repo_with_queries(
    query_results: dict[str, list[dict[str, object]]],
    *,
    update_rowcounts: list[int] | None = None,
) -> MagicMock:
    """Build a mock Repository whose conn.execute returns canned results.

    Parameters
    ----------
    query_results
        Maps a substring from the SQL query to a list of row dicts.
        The first matching substring wins.
    update_rowcounts
        Sequence of rowcount values for UPDATE queries. Popped in order.
    """
    remaining_counts = list(update_rowcounts or [])

    def execute_side_effect(sql: str, params: tuple[object, ...] = ()) -> object:
        sql_upper = sql.strip().upper()

        # For UPDATE statements, return an awaitable mock cursor with rowcount
        if sql_upper.startswith("UPDATE"):
            count = remaining_counts.pop(0) if remaining_counts else 1
            cursor_mock = MagicMock()
            cursor_mock.rowcount = count

            async def _update_coro() -> MagicMock:
                return cursor_mock

            return _update_coro()

        # For SELECT statements, return async context manager cursor
        for key, rows in query_results.items():
            if key.upper() in sql_upper:
                mock_rows = [_make_mock_row(r) for r in rows]
                return _MockCursor(mock_rows)

        # Default: no results
        return _MockCursor([])

    conn = MagicMock()
    conn.execute = MagicMock(side_effect=execute_side_effect)
    conn.commit = AsyncMock()

    db = MagicMock()
    type(db).conn = PropertyMock(return_value=conn)

    repo = MagicMock()
    type(repo)._db = PropertyMock(return_value=db)

    return repo


# ---------------------------------------------------------------------------
# score_predictions_for_recommendation
# ---------------------------------------------------------------------------


class TestScorePredictionsForRecommendation:
    @pytest.mark.asyncio
    async def test_scores_desk_predictions(self) -> None:
        """Score 6 desk predictions based on positive stock return."""
        repo = _make_repo_with_queries(
            {
                "AVG(co.stock_return_pct)": [{"avg_stock_return": 5.2}],
                "DISTINCT predicted_direction": [
                    {"predicted_direction": "bullish"},
                    {"predicted_direction": "bearish"},
                ],
            },
            # First UPDATE: bullish (correct), rowcount=4
            # Second UPDATE: bearish (incorrect), rowcount=2
            update_rowcounts=[4, 2],
        )

        count = await score_predictions_for_recommendation(repo, 1)
        assert count == 6

    @pytest.mark.asyncio
    async def test_no_outcomes_returns_zero(self) -> None:
        """No outcomes -> 0 predictions scored."""
        repo = _make_repo_with_queries(
            {
                "AVG(co.stock_return_pct)": [{"avg_stock_return": None}],
            },
        )

        count = await score_predictions_for_recommendation(repo, 1)
        assert count == 0

    @pytest.mark.asyncio
    async def test_negative_return_marks_bearish_correct(self) -> None:
        """Negative stock return -> bearish predictions correct."""
        repo = _make_repo_with_queries(
            {
                "AVG(co.stock_return_pct)": [{"avg_stock_return": -3.5}],
                "DISTINCT predicted_direction": [
                    {"predicted_direction": "bearish"},
                ],
            },
            update_rowcounts=[3],
        )

        count = await score_predictions_for_recommendation(repo, 1)
        assert count == 3

    @pytest.mark.asyncio
    async def test_no_unscored_predictions_returns_zero(self) -> None:
        """Outcomes exist but no unscored predictions -> 0."""
        repo = _make_repo_with_queries(
            {
                "AVG(co.stock_return_pct)": [{"avg_stock_return": 2.0}],
                "DISTINCT predicted_direction": [],  # no unscored predictions
            },
        )

        count = await score_predictions_for_recommendation(repo, 1)
        assert count == 0

    @pytest.mark.asyncio
    async def test_non_finite_avg_return_returns_zero(self) -> None:
        """Non-finite average stock return -> skip scoring."""
        repo = _make_repo_with_queries(
            {
                "AVG(co.stock_return_pct)": [{"avg_stock_return": float("nan")}],
            },
        )

        count = await score_predictions_for_recommendation(repo, 1)
        assert count == 0


# ---------------------------------------------------------------------------
# score_predictions_for_scan
# ---------------------------------------------------------------------------


class TestScorePredictionsForScan:
    @pytest.mark.asyncio
    async def test_scores_scan_predictions_by_ticker(self) -> None:
        """Score scan predictions grouped by ticker."""
        repo = _make_repo_with_queries(
            {
                "GROUP BY rc.ticker": [
                    {"ticker": "AAPL", "avg_stock_return": 3.0},
                    {"ticker": "MSFT", "avg_stock_return": -2.0},
                ],
                "DISTINCT predicted_direction": [
                    {"predicted_direction": "bullish"},
                ],
            },
            # AAPL bullish correct: 1, MSFT bullish incorrect: 1
            update_rowcounts=[1, 1],
        )

        count = await score_predictions_for_scan(repo, 10)
        assert count == 2

    @pytest.mark.asyncio
    async def test_no_outcomes_returns_zero(self) -> None:
        """No outcomes for scan run -> 0."""
        repo = _make_repo_with_queries(
            {
                "GROUP BY rc.ticker": [],
            },
        )

        count = await score_predictions_for_scan(repo, 10)
        assert count == 0

    @pytest.mark.asyncio
    async def test_non_finite_ticker_return_skipped(self) -> None:
        """Non-finite stock return for a ticker is skipped."""
        repo = _make_repo_with_queries(
            {
                "GROUP BY rc.ticker": [
                    {"ticker": "AAPL", "avg_stock_return": float("inf")},
                    {"ticker": "MSFT", "avg_stock_return": 2.0},
                ],
                "DISTINCT predicted_direction": [
                    {"predicted_direction": "bullish"},
                ],
            },
            # Only MSFT scored (AAPL skipped due to non-finite)
            update_rowcounts=[1],
        )

        count = await score_predictions_for_scan(repo, 10)
        assert count == 1


# ---------------------------------------------------------------------------
# run_prediction_scoring (never-raises)
# ---------------------------------------------------------------------------


class TestRunPredictionScoring:
    @pytest.mark.asyncio
    async def test_never_raises(self) -> None:
        """Exception in scoring -> logged, not raised."""
        conn = MagicMock()
        conn.execute = MagicMock(side_effect=RuntimeError("DB exploded"))

        db = MagicMock()
        type(db).conn = PropertyMock(return_value=conn)

        repo = MagicMock()
        type(repo)._db = PropertyMock(return_value=db)

        # Should not raise despite the DB error
        await run_prediction_scoring(repo)

    @pytest.mark.asyncio
    async def test_logs_exception_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Exception during scoring is logged."""
        conn = MagicMock()
        conn.execute = MagicMock(side_effect=RuntimeError("DB gone"))

        db = MagicMock()
        type(db).conn = PropertyMock(return_value=conn)

        repo = MagicMock()
        type(repo)._db = PropertyMock(return_value=db)

        with caplog.at_level("ERROR", logger="options_arena.learning.prediction_ledger"):
            await run_prediction_scoring(repo)

        assert "Prediction scoring failed" in caplog.text

    @pytest.mark.asyncio
    async def test_succeeds_with_no_data(self) -> None:
        """Empty DB -> completes without error."""
        repo = _make_repo_with_queries(
            {
                "DISTINCT p.recommendation_id": [],
                "DISTINCT p.scan_run_id": [],
            },
        )

        # Should complete without raising
        await run_prediction_scoring(repo)


# ---------------------------------------------------------------------------
# Condition classifiers (#766)
# ---------------------------------------------------------------------------


class TestClassifiers:
    """Tests for condition bucket classifiers."""

    @pytest.mark.parametrize(
        ("adx", "expected"),
        [
            (0.0, "weak"),
            (10.0, "weak"),
            (19.9, "weak"),
            (20.0, "moderate"),
            (25.0, "moderate"),
            (29.9, "moderate"),
            (30.0, "strong"),
            (40.0, "strong"),
            (100.0, "strong"),
            (None, None),
        ],
        ids=[
            "adx_0_weak",
            "adx_10_weak",
            "adx_19.9_weak",
            "adx_20_boundary_moderate",
            "adx_25_moderate",
            "adx_29.9_moderate",
            "adx_30_boundary_strong",
            "adx_40_strong",
            "adx_100_last_bucket_inclusive",
            "adx_none",
        ],
    )
    def test_classify_adx(self, adx: float | None, expected: str | None) -> None:
        assert _classify_adx(adx) == expected

    @pytest.mark.parametrize(
        ("iv_rank", "expected"),
        [
            (0.0, "low"),
            (15.0, "low"),
            (29.9, "low"),
            (30.0, "mid"),
            (50.0, "mid"),
            (69.9, "mid"),
            (70.0, "high"),
            (85.0, "high"),
            (100.0, "high"),
            (None, None),
        ],
        ids=[
            "iv_0_low",
            "iv_15_low",
            "iv_29.9_low",
            "iv_30_boundary_mid",
            "iv_50_mid",
            "iv_69.9_mid",
            "iv_70_boundary_high",
            "iv_85_high",
            "iv_100_last_bucket_inclusive",
            "iv_none",
        ],
    )
    def test_classify_iv_rank(self, iv_rank: float | None, expected: str | None) -> None:
        assert _classify_iv_rank(iv_rank) == expected

    @pytest.mark.parametrize(
        ("atr_pct", "expected"),
        [
            (0.0, "low"),
            (0.8, "low"),
            (1.49, "low"),
            (1.5, "medium"),
            (2.0, "medium"),
            (2.99, "medium"),
            (3.0, "high"),
            (5.0, "high"),
            (100.0, "high"),
            (None, None),
        ],
        ids=[
            "atr_0_low",
            "atr_0.8_low",
            "atr_1.49_low",
            "atr_1.5_boundary_medium",
            "atr_2.0_medium",
            "atr_2.99_medium",
            "atr_3.0_boundary_high",
            "atr_5.0_high",
            "atr_100_last_bucket_inclusive",
            "atr_none",
        ],
    )
    def test_classify_atr_pct(self, atr_pct: float | None, expected: str | None) -> None:
        assert _classify_atr_pct(atr_pct) == expected

    @pytest.mark.parametrize(
        ("rsi", "expected"),
        [
            (0.0, "oversold"),
            (20.0, "oversold"),
            (29.9, "oversold"),
            (30.0, "neutral"),
            (50.0, "neutral"),
            (69.9, "neutral"),
            (70.0, "overbought"),
            (80.0, "overbought"),
            (100.0, "overbought"),
            (None, None),
        ],
        ids=[
            "rsi_0_oversold",
            "rsi_20_oversold",
            "rsi_29.9_oversold",
            "rsi_30_boundary_neutral",
            "rsi_50_neutral",
            "rsi_69.9_neutral",
            "rsi_70_boundary_overbought",
            "rsi_80_overbought",
            "rsi_100_last_bucket_inclusive",
            "rsi_none",
        ],
    )
    def test_classify_rsi(self, rsi: float | None, expected: str | None) -> None:
        assert _classify_rsi(rsi) == expected

    def test_nan_returns_none(self) -> None:
        """Non-finite values return None (excluded from bucketing)."""
        assert _classify_adx(float("nan")) is None
        assert _classify_iv_rank(float("inf")) is None
        assert _classify_atr_pct(float("-inf")) is None
        assert _classify_rsi(float("nan")) is None


# ---------------------------------------------------------------------------
# compute_attribution (#766)
# ---------------------------------------------------------------------------


class TestComputeAttribution:
    """Tests for the top-level attribution computation."""

    def test_empty_predictions(self) -> None:
        """No predictions -> empty report, no crash."""
        report = compute_attribution([])
        assert report.total_recommendations == 0
        assert report.total_outcomes == 0
        assert report.source_accuracy == []
        assert report.condition_accuracy == []
        assert report.contract_guidance is None

    def test_source_accuracy(self) -> None:
        """3 correct + 1 incorrect desk_trend -> 75% accuracy."""
        preds = [
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=True),
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=True),
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=True),
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=False),
        ]
        report = compute_attribution(preds)
        assert len(report.source_accuracy) == 1
        src = report.source_accuracy[0]
        assert src.source == PredictionSource.DESK_TREND
        assert src.total == 4
        assert src.correct == 3
        assert src.accuracy == pytest.approx(0.75)

    def test_sample_sufficient_threshold(self) -> None:
        """< 10 samples -> sample_sufficient=False; >= 10 -> True."""
        # 5 predictions: insufficient
        few_preds = [
            make_prediction(source=PredictionSource.DESK_VOLATILITY, was_correct=True)
            for _ in range(5)
        ]
        report_few = compute_attribution(few_preds)
        assert len(report_few.source_accuracy) == 1
        assert report_few.source_accuracy[0].sample_sufficient is False

        # 15 predictions: sufficient
        many_preds = [
            make_prediction(source=PredictionSource.DESK_VOLATILITY, was_correct=True)
            for _ in range(15)
        ]
        report_many = compute_attribution(many_preds)
        assert len(report_many.source_accuracy) == 1
        assert report_many.source_accuracy[0].sample_sufficient is True

    def test_condition_bucketing(self) -> None:
        """Predictions with ADX=25 grouped into 'adx:moderate' bucket."""
        # Need >= MIN_CONDITION_SAMPLES (20) to appear in output
        preds = [
            make_prediction(
                source=PredictionSource.DESK_TREND,
                adx=25.0,
                was_correct=(i % 3 != 0),  # 2/3 correct
            )
            for i in range(25)
        ]
        report = compute_attribution(preds)
        # Find the condition entry for adx:moderate
        adx_entries = [c for c in report.condition_accuracy if c.condition == "adx:moderate"]
        assert len(adx_entries) == 1
        entry = adx_entries[0]
        assert entry.source == PredictionSource.DESK_TREND
        assert entry.total == 25
        # 2/3 pattern: indices 0,3,6,9,12,15,18,21,24 are False (9 false)
        # so 16 correct out of 25
        assert entry.correct == 16
        assert entry.accuracy == pytest.approx(16 / 25)

    def test_condition_min_samples(self) -> None:
        """< 20 samples in condition bucket -> excluded from output."""
        # Only 10 predictions with ADX context (below MIN_CONDITION_SAMPLES=20)
        preds = [
            make_prediction(
                source=PredictionSource.DESK_TREND,
                adx=25.0,
                was_correct=True,
            )
            for _ in range(10)
        ]
        report = compute_attribution(preds)
        # No condition accuracy entries because 10 < 20
        assert report.condition_accuracy == []

    def test_unscored_excluded_from_accuracy(self) -> None:
        """was_correct=None predictions not counted in accuracy."""
        preds = [
            make_prediction(source=PredictionSource.DESK_FLOW, was_correct=True),
            make_prediction(source=PredictionSource.DESK_FLOW, was_correct=False),
            make_prediction(source=PredictionSource.DESK_FLOW, was_correct=None),
            make_prediction(source=PredictionSource.DESK_FLOW, was_correct=None),
        ]
        report = compute_attribution(preds)
        assert len(report.source_accuracy) == 1
        src = report.source_accuracy[0]
        assert src.total == 2  # only scored predictions
        assert src.correct == 1
        assert src.accuracy == pytest.approx(0.5)
        # total_outcomes counts scored only
        assert report.total_outcomes == 2

    def test_multiple_sources(self) -> None:
        """Different sources return separate PredictionAccuracy entries."""
        preds = [
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=True),
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=False),
            make_prediction(source=PredictionSource.DESK_VOLATILITY, was_correct=True),
            make_prediction(source=PredictionSource.DESK_VOLATILITY, was_correct=True),
            make_prediction(source=PredictionSource.DESK_VOLATILITY, was_correct=True),
        ]
        report = compute_attribution(preds)
        assert len(report.source_accuracy) == 2
        sources = {s.source: s for s in report.source_accuracy}

        trend = sources[PredictionSource.DESK_TREND]
        assert trend.total == 2
        assert trend.correct == 1
        assert trend.accuracy == pytest.approx(0.5)

        vol = sources[PredictionSource.DESK_VOLATILITY]
        assert vol.total == 3
        assert vol.correct == 3
        assert vol.accuracy == pytest.approx(1.0)

    def test_all_unscored_returns_empty_accuracy(self) -> None:
        """All predictions unscored -> empty accuracy lists."""
        preds = [
            make_prediction(source=PredictionSource.DESK_TREND, was_correct=None),
            make_prediction(source=PredictionSource.DESK_FLOW, was_correct=None),
        ]
        report = compute_attribution(preds)
        assert report.source_accuracy == []
        assert report.condition_accuracy == []
        assert report.total_outcomes == 0
        # Recommendations still counted from full list
        assert report.total_recommendations == 1  # all have recommendation_id=1

    def test_none_context_excluded_from_dimension_only(self) -> None:
        """None context field excluded from that dimension, not others."""
        # adx=None, iv_rank=50 -> excluded from ADX dimension, included in IV
        preds = [
            make_prediction(
                source=PredictionSource.DESK_TREND,
                adx=None,
                iv_rank=50.0,
                was_correct=True,
            )
            for _ in range(25)
        ]
        report = compute_attribution(preds)
        # Should have iv_rank:mid but no adx entries
        conditions = {c.condition for c in report.condition_accuracy}
        assert "iv_rank:mid" in conditions
        assert not any(c.startswith("adx:") for c in conditions)

    def test_contract_guidance_passthrough(self) -> None:
        """contract_guidance parameter is included in report."""
        from options_arena.models.attribution import ContractGuidance

        guidance = ContractGuidance(
            optimal_delta_low=0.25,
            optimal_delta_high=0.45,
            optimal_dte_low=30,
            optimal_dte_high=60,
            delta_win_rate=0.65,
            dte_win_rate=0.70,
            sample_count=100,
        )
        report = compute_attribution([], contract_guidance=guidance)
        assert report.contract_guidance is guidance

    def test_total_recommendations_counts_distinct(self) -> None:
        """total_recommendations counts distinct recommendation_ids."""
        preds = [
            make_prediction(recommendation_id=1, was_correct=True),
            make_prediction(recommendation_id=1, was_correct=False),
            make_prediction(recommendation_id=2, was_correct=True),
            make_prediction(recommendation_id=3, was_correct=None),
        ]
        report = compute_attribution(preds)
        assert report.total_recommendations == 3
