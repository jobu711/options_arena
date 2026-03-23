"""Tests for ``process_ticker_options`` coordinator pattern.

Verifies that the coordinator delegates to its four extracted helpers in
the correct order and handles early-return checkpoints:

  - ``_fetch_ticker_data()`` → filtered_out early return
  - ``_compute_dse_indicators()`` → iv_filtered_out early return
  - ``_select_and_score_contracts()`` → contract recommendation
  - ``_build_spread()`` → spread construction

All four helpers are mocked; no business logic is tested here (that
belongs to the individual helper test files).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models import (
    IndicatorSignals,
    OptionContract,
    PricingConfig,
    SignalDirection,
    SpreadAnalysis,
    SpreadConfig,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters, UniverseFilters
from options_arena.models.market_data import TickerInfo
from options_arena.scan.phase_options import (
    _DSEResult,
    _TickerData,
    process_ticker_options,
)
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MODULE = "options_arena.scan.phase_options"


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a minimal TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=75.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
    )


def _make_ticker_info(ticker: str = "AAPL") -> TickerInfo:
    """Create a TickerInfo with sensible defaults."""
    return TickerInfo(
        ticker=ticker,
        company_name="Apple Inc.",
        sector="Information Technology",
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("200.00"),
        fifty_two_week_low=Decimal("140.00"),
        dividend_yield=0.005,
    )


def _make_contracts(n: int = 2) -> list[OptionContract]:
    """Create a list of option contracts."""
    return [make_option_contract() for _ in range(n)]


def _base_kwargs() -> dict:
    """Common keyword arguments for ``process_ticker_options``."""
    return {
        "market_data": AsyncMock(),
        "options_data": AsyncMock(),
        "repository": AsyncMock(),
        "options_filters": OptionsFilters(),
        "universe_filters": UniverseFilters(),
        "pricing_config": PricingConfig(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessTickerOptionsCoordinator:
    """Test the coordinator delegates to helpers and handles early returns."""

    @pytest.mark.critical
    def test_normal_flow_calls_all_helpers(self) -> None:
        """Happy path: all 4 helpers called in order, result tuple assembled."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()
        contracts = _make_contracts(2)
        recommended = [contracts[0]]
        earnings = date.today() + timedelta(days=30)
        entry_price = Decimal("185.50")

        td = _TickerData(
            all_contracts=contracts,
            ticker_info=ticker_info,
            earnings_date=earnings,
            entry_stock_price=entry_price,
            filtered_out=False,
        )
        dse = _DSEResult(
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            mp_strike=None,
            iv_filtered_out=False,
        )

        with (
            patch(
                f"{MODULE}._fetch_ticker_data",
                new_callable=AsyncMock,
                return_value=td,
            ) as m_fetch,
            patch(f"{MODULE}._compute_dse_indicators", return_value=dse) as m_dse,
            patch(f"{MODULE}._select_and_score_contracts", return_value=recommended) as m_select,
            patch(f"{MODULE}._build_spread", return_value=None) as m_spread,
        ):
            result = asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    **_base_kwargs(),
                )
            )

        # All 4 helpers called exactly once
        m_fetch.assert_called_once()
        m_dse.assert_called_once()
        m_select.assert_called_once()
        m_spread.assert_called_once()

        # Result tuple structure
        ticker, recs, earn, price, spread = result
        assert ticker == "AAPL"
        assert recs == recommended
        assert earn == earnings
        assert price == entry_price
        assert spread is None

    def test_fetch_filtered_returns_early(self) -> None:
        """When _fetch_ticker_data sets filtered_out=True, skip remaining helpers."""
        ts = _make_ticker_score()
        td = _TickerData(
            all_contracts=[],
            ticker_info=None,
            earnings_date=date.today() + timedelta(days=5),
            entry_stock_price=None,
            filtered_out=True,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators") as m_dse,
            patch(f"{MODULE}._select_and_score_contracts") as m_select,
            patch(f"{MODULE}._build_spread") as m_spread,
        ):
            result = asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    **_base_kwargs(),
                )
            )

        # Remaining helpers NOT called
        m_dse.assert_not_called()
        m_select.assert_not_called()
        m_spread.assert_not_called()

        ticker, recs, earn, price, spread = result
        assert ticker == "AAPL"
        assert recs == []
        assert earn == td.earnings_date
        assert price is None
        assert spread is None

    def test_iv_filtered_returns_early(self) -> None:
        """When _compute_dse_indicators sets iv_filtered_out=True, skip contract selection."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()
        contracts = _make_contracts(2)
        entry_price = Decimal("185.50")

        td = _TickerData(
            all_contracts=contracts,
            ticker_info=ticker_info,
            earnings_date=None,
            entry_stock_price=entry_price,
            filtered_out=False,
        )
        dse = _DSEResult(
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            mp_strike=None,
            iv_filtered_out=True,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators", return_value=dse),
            patch(f"{MODULE}._select_and_score_contracts") as m_select,
            patch(f"{MODULE}._build_spread") as m_spread,
        ):
            result = asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    **_base_kwargs(),
                )
            )

        # Contract selection and spread NOT called
        m_select.assert_not_called()
        m_spread.assert_not_called()

        ticker, recs, earn, price, spread = result
        assert ticker == "AAPL"
        assert recs == []
        assert earn is None
        assert price == entry_price
        assert spread is None

    def test_empty_contracts_returns_early(self) -> None:
        """When _fetch_ticker_data returns empty contracts, skip DSE and later helpers."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()

        td = _TickerData(
            all_contracts=[],
            ticker_info=ticker_info,
            earnings_date=None,
            entry_stock_price=Decimal("185.50"),
            filtered_out=False,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators") as m_dse,
            patch(f"{MODULE}._select_and_score_contracts") as m_select,
            patch(f"{MODULE}._build_spread") as m_spread,
        ):
            result = asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    **_base_kwargs(),
                )
            )

        # All downstream helpers NOT called
        m_dse.assert_not_called()
        m_select.assert_not_called()
        m_spread.assert_not_called()

        ticker, recs, earn, price, spread = result
        assert ticker == "AAPL"
        assert recs == []
        assert earn is None
        assert price == Decimal("185.50")
        assert spread is None

    def test_return_tuple_structure(self) -> None:
        """Verify the 5-element return tuple has correct types in happy path."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()
        contracts = _make_contracts(1)
        recommended = [contracts[0]]
        earnings = date.today() + timedelta(days=20)
        entry_price = Decimal("185.50")

        # Create a mock SpreadAnalysis
        mock_spread = MagicMock(spec=SpreadAnalysis)

        td = _TickerData(
            all_contracts=contracts,
            ticker_info=ticker_info,
            earnings_date=earnings,
            entry_stock_price=entry_price,
            filtered_out=False,
        )
        dse = _DSEResult(
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            mp_strike=None,
            iv_filtered_out=False,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators", return_value=dse),
            patch(f"{MODULE}._select_and_score_contracts", return_value=recommended),
            patch(f"{MODULE}._build_spread", return_value=mock_spread),
        ):
            result = asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    **_base_kwargs(),
                )
            )

        # Verify tuple length and types
        assert len(result) == 5
        ticker, recs, earn, price, spread = result
        assert isinstance(ticker, str)
        assert isinstance(recs, list)
        assert isinstance(earn, date)
        assert isinstance(price, Decimal)
        assert spread is mock_spread

    def test_spread_config_passed_to_build_spread(self) -> None:
        """Verify spread_config is threaded through to _build_spread."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()
        contracts = _make_contracts(1)
        spread_cfg = SpreadConfig(enabled=True)

        td = _TickerData(
            all_contracts=contracts,
            ticker_info=ticker_info,
            earnings_date=None,
            entry_stock_price=Decimal("185.50"),
            filtered_out=False,
        )
        dse = _DSEResult(
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            mp_strike=None,
            iv_filtered_out=False,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators", return_value=dse),
            patch(f"{MODULE}._select_and_score_contracts", return_value=[contracts[0]]),
            patch(f"{MODULE}._build_spread", return_value=None) as m_spread,
        ):
            asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    spread_config=spread_cfg,
                    **_base_kwargs(),
                )
            )

        # Verify spread_config was passed through
        call_kwargs = m_spread.call_args
        assert call_kwargs.kwargs["spread_config"] is spread_cfg

    def test_custom_recommend_fn_used(self) -> None:
        """Verify recommend_contracts_fn override is passed to _select_and_score_contracts."""
        ts = _make_ticker_score()
        ticker_info = _make_ticker_info()
        contracts = _make_contracts(1)
        custom_recommend = MagicMock()

        td = _TickerData(
            all_contracts=contracts,
            ticker_info=ticker_info,
            earnings_date=None,
            entry_stock_price=Decimal("185.50"),
            filtered_out=False,
        )
        dse = _DSEResult(
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            mp_strike=None,
            iv_filtered_out=False,
        )

        with (
            patch(f"{MODULE}._fetch_ticker_data", new_callable=AsyncMock, return_value=td),
            patch(f"{MODULE}._compute_dse_indicators", return_value=dse),
            patch(f"{MODULE}._select_and_score_contracts", return_value=[]) as m_select,
            patch(f"{MODULE}._build_spread", return_value=None),
        ):
            asyncio.run(
                process_ticker_options(
                    ticker_score=ts,
                    risk_free_rate=0.04,
                    ohlcv_map={},
                    spx_close=None,
                    recommend_contracts_fn=custom_recommend,
                    **_base_kwargs(),
                )
            )

        # The custom recommend fn should have been passed as recommend_fn
        call_kwargs = m_select.call_args
        assert call_kwargs.kwargs["recommend_fn"] is custom_recommend
