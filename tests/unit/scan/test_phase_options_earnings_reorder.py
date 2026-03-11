"""Tests for Phase 3 earnings check reorder optimization.

Covers:
  - Earnings proximity check runs before chain fetch.
  - Near-earnings ticker does not trigger chain fetch.
  - exclude_near_earnings_days=None skips check.
  - Ticker with distant earnings proceeds to chain fetch.
  - Ticker with no earnings date proceeds to chain fetch.
  - Earnings date returned even when ticker is skipped.
  - Earnings on today (0 days) triggers filter.
  - Past earnings dates do not trigger filter.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    IndicatorSignals,
    PricingConfig,
    SignalDirection,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters, UniverseFilters
from options_arena.scan.phase_options import process_ticker_options

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=80.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
    )


def _make_mocks() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Create mocked services."""
    mock_market_data = AsyncMock()
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)
    mock_market_data.fetch_ticker_info = AsyncMock()

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    mock_repository = AsyncMock()
    return mock_market_data, mock_options_data, mock_repository


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEarningsReorder:
    """Phase 3 earnings check reorder tests."""

    async def test_near_earnings_skips_chain_fetch(self) -> None:
        """Verify ticker near earnings does not trigger chain fetch."""
        mock_market, mock_options, mock_repo = _make_mocks()
        # Earnings tomorrow
        tomorrow = date.today() + timedelta(days=1)
        mock_market.fetch_earnings_date = AsyncMock(return_value=tomorrow)

        result = await process_ticker_options(
            _make_ticker_score(),
            risk_free_rate=0.05,
            ohlcv_map={},
            spx_close=None,
            market_data=mock_market,
            options_data=mock_options,
            repository=mock_repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            pricing_config=PricingConfig(),
        )

        ticker, contracts, earnings, _price = result
        assert ticker == "AAPL"
        assert contracts == []
        assert earnings == tomorrow
        # Chain fetch should NOT have been called
        mock_options.fetch_chain_all_expirations.assert_not_awaited()

    async def test_no_earnings_filter_when_none(self) -> None:
        """Verify exclude_near_earnings_days=None skips check."""
        mock_market, mock_options, mock_repo = _make_mocks()
        # Earnings tomorrow — but filter is disabled
        tomorrow = date.today() + timedelta(days=1)
        mock_market.fetch_earnings_date = AsyncMock(return_value=tomorrow)
        mock_market.fetch_ticker_info = AsyncMock(
            side_effect=Exception("should reach chain fetch")
        )

        # With filter disabled, should proceed to chain+info fetch (which will raise)
        with pytest.raises(Exception, match="should reach chain fetch"):
            await process_ticker_options(
                _make_ticker_score(),
                risk_free_rate=0.05,
                ohlcv_map={},
                spx_close=None,
                market_data=mock_market,
                options_data=mock_options,
                repository=mock_repo,
                options_filters=OptionsFilters(exclude_near_earnings_days=None),
                universe_filters=UniverseFilters(),
                pricing_config=PricingConfig(),
            )

    async def test_earnings_far_away_proceeds(self) -> None:
        """Verify ticker with distant earnings proceeds to chain fetch."""
        mock_market, mock_options, mock_repo = _make_mocks()
        # Earnings 30 days out — beyond the 7-day filter
        far_date = date.today() + timedelta(days=30)
        mock_market.fetch_earnings_date = AsyncMock(return_value=far_date)
        mock_market.fetch_ticker_info = AsyncMock(side_effect=Exception("reached chain fetch"))

        # Should proceed past earnings check to chain+info fetch
        with pytest.raises(Exception, match="reached chain fetch"):
            await process_ticker_options(
                _make_ticker_score(),
                risk_free_rate=0.05,
                ohlcv_map={},
                spx_close=None,
                market_data=mock_market,
                options_data=mock_options,
                repository=mock_repo,
                options_filters=OptionsFilters(exclude_near_earnings_days=7),
                universe_filters=UniverseFilters(),
                pricing_config=PricingConfig(),
            )

    async def test_no_earnings_date_proceeds(self) -> None:
        """Verify ticker with no earnings date proceeds to chain fetch."""
        mock_market, mock_options, mock_repo = _make_mocks()
        mock_market.fetch_earnings_date = AsyncMock(return_value=None)
        mock_market.fetch_ticker_info = AsyncMock(side_effect=Exception("reached chain fetch"))

        with pytest.raises(Exception, match="reached chain fetch"):
            await process_ticker_options(
                _make_ticker_score(),
                risk_free_rate=0.05,
                ohlcv_map={},
                spx_close=None,
                market_data=mock_market,
                options_data=mock_options,
                repository=mock_repo,
                options_filters=OptionsFilters(exclude_near_earnings_days=7),
                universe_filters=UniverseFilters(),
                pricing_config=PricingConfig(),
            )

    async def test_earnings_date_returned_when_skipped(self) -> None:
        """Verify earnings date is still captured for propagation."""
        mock_market, mock_options, mock_repo = _make_mocks()
        tomorrow = date.today() + timedelta(days=1)
        mock_market.fetch_earnings_date = AsyncMock(return_value=tomorrow)

        result = await process_ticker_options(
            _make_ticker_score(),
            risk_free_rate=0.05,
            ohlcv_map={},
            spx_close=None,
            market_data=mock_market,
            options_data=mock_options,
            repository=mock_repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            pricing_config=PricingConfig(),
        )

        _ticker, _contracts, earnings, _price = result
        assert earnings == tomorrow

    async def test_zero_days_to_earnings(self) -> None:
        """Verify earnings on today triggers filter."""
        mock_market, mock_options, mock_repo = _make_mocks()
        mock_market.fetch_earnings_date = AsyncMock(return_value=date.today())

        result = await process_ticker_options(
            _make_ticker_score(),
            risk_free_rate=0.05,
            ohlcv_map={},
            spx_close=None,
            market_data=mock_market,
            options_data=mock_options,
            repository=mock_repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            pricing_config=PricingConfig(),
        )

        _ticker, contracts, earnings, _price = result
        assert contracts == []
        assert earnings == date.today()
        mock_options.fetch_chain_all_expirations.assert_not_awaited()

    async def test_negative_days_to_earnings(self) -> None:
        """Verify past earnings dates do not trigger filter."""
        mock_market, mock_options, mock_repo = _make_mocks()
        past_date = date.today() - timedelta(days=5)
        mock_market.fetch_earnings_date = AsyncMock(return_value=past_date)
        mock_market.fetch_ticker_info = AsyncMock(side_effect=Exception("reached chain fetch"))

        # Past earnings should not trigger filter — proceeds to chain fetch
        with pytest.raises(Exception, match="reached chain fetch"):
            await process_ticker_options(
                _make_ticker_score(),
                risk_free_rate=0.05,
                ohlcv_map={},
                spx_close=None,
                market_data=mock_market,
                options_data=mock_options,
                repository=mock_repo,
                options_filters=OptionsFilters(exclude_near_earnings_days=7),
                universe_filters=UniverseFilters(),
                pricing_config=PricingConfig(),
            )
