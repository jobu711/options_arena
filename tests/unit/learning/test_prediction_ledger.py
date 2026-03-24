"""Tests for prediction scoring in learning/prediction_ledger.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from options_arena.learning.prediction_ledger import (
    _direction_was_correct,
    run_prediction_scoring,
    score_predictions_for_recommendation,
    score_predictions_for_scan,
)
from options_arena.models.enums import SignalDirection

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
