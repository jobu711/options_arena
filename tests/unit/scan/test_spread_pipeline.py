"""Tests for spread strategy integration into scan pipeline Phase 3.

Covers:
  - Spread constructed when select_strategy returns a result.
  - No spread when select_strategy returns None.
  - Graceful fallback when select_strategy raises.
  - Spread disabled via SpreadConfig.enabled=False.
  - Spread populated alongside single-contract recommendation.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models import (
    IndicatorSignals,
    SignalDirection,
    SpreadConfig,
    TickerScore,
)
from options_arena.models.enums import (
    OptionType,
    SpreadType,
)
from options_arena.models.filters import OptionsFilters, UniverseFilters
from options_arena.models.market_data import TickerInfo
from options_arena.scan.phase_options import process_ticker_options
from tests.factories import make_option_contract, make_spread_analysis

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(
    ticker: str = "AAPL",
    score: float = 75.0,
    direction: SignalDirection = SignalDirection.BULLISH,
    iv_rank: float | None = 65.0,
) -> TickerScore:
    """Create a TickerScore with sensible defaults."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.0, adx=25.0, iv_rank=iv_rank),
    )


def _make_ticker_info(
    ticker: str = "AAPL",
    current_price: Decimal = Decimal("185.50"),
) -> TickerInfo:
    """Create a minimal TickerInfo for testing."""
    return TickerInfo(
        ticker=ticker,
        company_name="Apple Inc.",
        sector="Information Technology",
        current_price=current_price,
        fifty_two_week_high=Decimal("200.00"),
        fifty_two_week_low=Decimal("140.00"),
    )


def _make_chain_result(
    ticker: str = "AAPL",
) -> list[MagicMock]:
    """Create a mock chain result with enough contracts for spread construction."""
    contracts = [
        make_option_contract(
            ticker=ticker,
            option_type=OptionType.CALL,
            strike=Decimal(str(strike)),
            expiration=date.today() + timedelta(days=45),
        )
        for strike in [145, 150, 155, 160, 165]
    ] + [
        make_option_contract(
            ticker=ticker,
            option_type=OptionType.PUT,
            strike=Decimal(str(strike)),
            expiration=date.today() + timedelta(days=45),
        )
        for strike in [145, 150, 155, 160, 165]
    ]
    chain = MagicMock()
    chain.contracts = contracts
    return [chain]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpreadPipelineIntegration:
    """Tests for spread construction integration in Phase 3."""

    @pytest.mark.asyncio
    async def test_spread_constructed_for_high_iv_ticker(self) -> None:
        """Verify spread appears when select_strategy returns a result."""
        ticker_score = _make_ticker_score(iv_rank=65.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()
        spread = make_spread_analysis()

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        spread_config = SpreadConfig(enabled=True)

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=spread,
        ) as mock_select:
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=spread_config,
            )

        _ticker, _contracts, _earnings, _entry, spread_result = result
        assert spread_result is not None
        assert spread_result.spread.spread_type == SpreadType.VERTICAL
        mock_select.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_spread_when_select_strategy_returns_none(self) -> None:
        """Verify no spread when select_strategy returns None (e.g., mid IV)."""
        ticker_score = _make_ticker_score(iv_rank=35.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        spread_config = SpreadConfig(enabled=True)

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=None,
        ):
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=spread_config,
            )

        _ticker, _contracts, _earnings, _entry, spread_result = result
        assert spread_result is None

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_exception(self) -> None:
        """Verify pipeline continues normally when select_strategy raises."""
        ticker_score = _make_ticker_score(iv_rank=65.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        spread_config = SpreadConfig(enabled=True)

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            side_effect=ValueError("Spread construction failed"),
        ):
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=spread_config,
            )

        _ticker, _contracts, _earnings, _entry, spread_result = result
        # Spread fails gracefully — None returned, pipeline not broken
        assert spread_result is None

    @pytest.mark.asyncio
    async def test_spread_disabled_via_config(self) -> None:
        """Verify SpreadConfig.enabled=False skips spread construction entirely."""
        ticker_score = _make_ticker_score(iv_rank=65.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        spread_config = SpreadConfig(enabled=False)

        with patch(
            "options_arena.scan.phase_options.select_strategy",
        ) as mock_select:
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=spread_config,
            )

        _ticker, _contracts, _earnings, _entry, spread_result = result
        assert spread_result is None
        mock_select.assert_not_called()

    @pytest.mark.asyncio
    async def test_spread_skipped_when_config_none(self) -> None:
        """Verify spread_config=None skips spread construction."""
        ticker_score = _make_ticker_score(iv_rank=65.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        with patch(
            "options_arena.scan.phase_options.select_strategy",
        ) as mock_select:
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=None,
            )

        _ticker, _contracts, _earnings, _entry, spread_result = result
        assert spread_result is None
        mock_select.assert_not_called()

    @pytest.mark.asyncio
    async def test_spread_alongside_single_contract(self) -> None:
        """Verify both single contract and spread populate simultaneously."""
        ticker_score = _make_ticker_score(iv_rank=65.0)
        ticker_info = _make_ticker_info()
        chain_result = _make_chain_result()
        spread = make_spread_analysis()

        # Mock recommend_contracts to return a contract
        recommended_contract = make_option_contract(ticker="AAPL")

        market_data = AsyncMock()
        market_data.fetch_ticker_info.return_value = ticker_info
        market_data.fetch_earnings_date.return_value = None

        options_data = AsyncMock()
        options_data.fetch_chain_all_expirations.return_value = chain_result

        repository = AsyncMock()

        spread_config = SpreadConfig(enabled=True)

        with (
            patch(
                "options_arena.scan.phase_options.select_strategy",
                return_value=spread,
            ),
            patch(
                "options_arena.scan.phase_options.recommend_contracts",
                return_value=[recommended_contract],
            ),
        ):
            result = await process_ticker_options(
                ticker_score=ticker_score,
                risk_free_rate=0.045,
                ohlcv_map={},
                spx_close=None,
                market_data=market_data,
                options_data=options_data,
                repository=repository,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                pricing_config=MagicMock(),
                spread_config=spread_config,
            )

        _ticker, contracts, _earnings, _entry, spread_result = result
        # Both single contract and spread are populated
        assert len(contracts) == 1
        assert spread_result is not None
        assert spread_result.spread.spread_type == SpreadType.VERTICAL
