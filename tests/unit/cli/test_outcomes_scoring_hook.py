"""Tests for prediction scoring hook in outcomes collect command.

Verifies that ``run_prediction_scoring`` is called after outcome collection
and before confidence decay, and that an unexpected exception from scoring
does not prevent confidence decay from running.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.cli.outcomes import _outcomes_collect_async

pytestmark = pytest.mark.critical


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


def _mock_outcome() -> MagicMock:
    """Create a minimal mock outcome for the display table."""
    outcome = MagicMock()
    outcome.recommended_contract_id = 1
    outcome.stock_return_pct = 5.0
    outcome.contract_return_pct = 12.0
    outcome.is_winner = True
    outcome.holding_days = 20
    outcome.collection_method = MagicMock()
    outcome.collection_method.value = "market_close"
    return outcome


def _setup_mocks(
    mock_settings_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_collector_cls: MagicMock,
    *,
    outcomes: list[MagicMock] | None = None,
) -> AsyncMock:
    """Wire up standard mocks for _outcomes_collect_async and return the repo mock."""
    mock_db_cls.return_value = _mock_db()
    mock_repo = AsyncMock()
    mock_repo_cls.return_value = mock_repo

    mock_market = AsyncMock()
    mock_market_cls.return_value = mock_market
    mock_options = AsyncMock()
    mock_options_cls.return_value = mock_options

    mock_collector = AsyncMock()
    mock_collector.collect_outcomes = AsyncMock(
        return_value=outcomes if outcomes is not None else [_mock_outcome()]
    )
    mock_collector_cls.return_value = mock_collector

    # Mock the DB cursor for ticker lookup in outcome display
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value={"ticker": "AAPL"})
    mock_conn.execute = MagicMock(return_value=mock_cursor)
    mock_repo._db = MagicMock()
    mock_repo._db.conn = mock_conn

    mock_settings = MagicMock()
    mock_settings.data.db_path = None
    mock_settings.service.rate_limit_rps = 5
    mock_settings.service.max_concurrent_requests = 10
    mock_settings.analytics.holding_periods = [5, 10, 20]
    mock_settings.scan.filters.options = MagicMock()
    mock_settings_cls.return_value = mock_settings

    return mock_repo


class TestOutcomesScoringHook:
    """Tests for prediction scoring hook wired into outcomes collect."""

    @pytest.mark.asyncio
    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.run_prediction_scoring", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.OutcomeCollector")
    @patch("options_arena.cli.outcomes.OptionsDataService")
    @patch("options_arena.cli.outcomes.MarketDataService")
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    @patch("options_arena.cli.outcomes.AppSettings")
    async def test_scoring_called_after_collection(
        self,
        mock_settings_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_collector_cls: MagicMock,
        mock_scoring: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """run_prediction_scoring is called after collect_outcomes returns."""
        mock_repo = _setup_mocks(
            mock_settings_cls,
            mock_db_cls,
            mock_repo_cls,
            mock_market_cls,
            mock_options_cls,
            mock_collector_cls,
        )

        await _outcomes_collect_async(holding_days=None)

        mock_scoring.assert_called_once_with(mock_repo)

    @pytest.mark.asyncio
    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.run_prediction_scoring", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.OutcomeCollector")
    @patch("options_arena.cli.outcomes.OptionsDataService")
    @patch("options_arena.cli.outcomes.MarketDataService")
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    @patch("options_arena.cli.outcomes.AppSettings")
    async def test_scoring_before_confidence_decay(
        self,
        mock_settings_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_collector_cls: MagicMock,
        mock_scoring: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Scoring runs before run_confidence_decay in call order."""
        call_order: list[str] = []

        async def track_scoring(repo: object) -> None:
            call_order.append("scoring")

        async def track_decay(repo: object) -> None:
            call_order.append("decay")

        mock_scoring.side_effect = track_scoring
        mock_decay.side_effect = track_decay

        _setup_mocks(
            mock_settings_cls,
            mock_db_cls,
            mock_repo_cls,
            mock_market_cls,
            mock_options_cls,
            mock_collector_cls,
        )

        await _outcomes_collect_async(holding_days=None)

        assert call_order == ["scoring", "decay"]

    @pytest.mark.asyncio
    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.run_prediction_scoring", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.OutcomeCollector")
    @patch("options_arena.cli.outcomes.OptionsDataService")
    @patch("options_arena.cli.outcomes.MarketDataService")
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    @patch("options_arena.cli.outcomes.AppSettings")
    async def test_scoring_failure_doesnt_block_decay(
        self,
        mock_settings_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_collector_cls: MagicMock,
        mock_scoring: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """If scoring raises unexpectedly, confidence decay still runs.

        ``run_prediction_scoring`` is already never-raises, but the CLI wraps
        it in a try/except as belt-and-suspenders.  This test verifies that
        even if the function somehow raises, confidence decay is not blocked.
        """
        mock_scoring.side_effect = RuntimeError("unexpected scoring failure")

        mock_repo = _setup_mocks(
            mock_settings_cls,
            mock_db_cls,
            mock_repo_cls,
            mock_market_cls,
            mock_options_cls,
            mock_collector_cls,
        )

        await _outcomes_collect_async(holding_days=None)

        # Scoring was attempted
        mock_scoring.assert_called_once_with(mock_repo)
        # Confidence decay still ran despite scoring failure
        mock_decay.assert_called_once_with(mock_repo)

    @pytest.mark.asyncio
    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.run_prediction_scoring", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.OutcomeCollector")
    @patch("options_arena.cli.outcomes.OptionsDataService")
    @patch("options_arena.cli.outcomes.MarketDataService")
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    @patch("options_arena.cli.outcomes.AppSettings")
    async def test_scoring_not_called_when_no_outcomes(
        self,
        mock_settings_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_collector_cls: MagicMock,
        mock_scoring: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Scoring is not called when no outcomes are collected (early return)."""
        _setup_mocks(
            mock_settings_cls,
            mock_db_cls,
            mock_repo_cls,
            mock_market_cls,
            mock_options_cls,
            mock_collector_cls,
            outcomes=[],
        )

        await _outcomes_collect_async(holding_days=None)

        mock_scoring.assert_not_called()
        mock_decay.assert_not_called()
