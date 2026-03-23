"""Tests for ``_compute_dse_indicators`` helper extracted from ``process_ticker_options``.

Covers:
  - Happy path: DSE indicators computed, signals mutated, ``iv_filtered_out=False``.
  - IV rank filter: ``iv_filtered_out=True`` when iv_rank < min_iv_rank.
  - IV rank filter: ``iv_filtered_out=False`` when iv_rank >= min_iv_rank.
  - IV rank filter disabled (``min_iv_rank=None``): always passes.
  - No OHLCV data: vol surface and Phase 3 indicators skipped gracefully.
  - Empty OHLCV list: treated same as missing.
  - Vol surface failure: non-fatal, Phase 3 indicators still computed.
  - Phase 3 indicators failure: non-fatal, signals partially populated.
  - Options-specific signals merged (put_call_ratio, max_pain_distance).
  - Vol surface arrays populated when >= 3 contracts.
  - Return type is ``_DSEResult`` with correct fields.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from options_arena.models import (
    IndicatorSignals,
    OptionType,
    SignalDirection,
    SurfaceMethod,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.phase_options import _compute_dse_indicators, _DSEResult
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a minimal TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=80.0,
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


def _make_ohlcv_list(ticker: str = "AAPL", n_bars: int = 5) -> list[OHLCV]:
    """Create a list of OHLCV bars for testing."""
    base_date = date.today() - timedelta(days=n_bars)
    return [
        OHLCV(
            ticker=ticker,
            date=base_date + timedelta(days=i),
            open=Decimal("180.00"),
            high=Decimal("186.00"),
            low=Decimal("179.00"),
            close=Decimal("185.00"),
            adjusted_close=Decimal("185.00"),
            volume=1000000,
        )
        for i in range(n_bars)
    ]


def _make_contracts(
    ticker: str = "AAPL",
    n_contracts: int = 5,
) -> list:
    """Create a list of option contracts for testing."""
    expiration = date.today() + timedelta(days=45)
    contracts = []
    for i in range(n_contracts):
        contracts.append(
            make_option_contract(
                ticker=ticker,
                expiration=expiration,
                strike=Decimal(str(150 + i * 5)),
                option_type=OptionType.CALL if i % 2 == 0 else OptionType.PUT,
                market_iv=0.25 + i * 0.02,
            )
        )
    return contracts


# ---------------------------------------------------------------------------
# Patch paths — target where functions are looked up, not where they're defined.
# ---------------------------------------------------------------------------

_MODULE = "options_arena.scan.phase_options"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeDSEIndicatorsHappyPath:
    """Happy-path tests for _compute_dse_indicators."""

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_returns_dse_result(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify happy path: returns _DSEResult with correct fields."""
        mock_options_ind.return_value = IndicatorSignals(put_call_ratio=0.8, max_pain_distance=2.5)
        mock_vol_surface.return_value = MagicMock(
            skew_25d=0.1, smile_curvature=0.05, prob_above_current=0.6
        )
        mock_phase3.return_value = IndicatorSignals(iv_hv_spread=0.15, gex=50000.0)

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert isinstance(result, _DSEResult)
        assert result.iv_filtered_out is False
        assert result.mp_strike == 185.0
        assert result.vol_result is not None
        assert result.vs_strikes is not None
        assert result.vs_dtes is not None

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_merges_options_signals(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify put_call_ratio and max_pain_distance are merged into signals."""
        mock_options_ind.return_value = IndicatorSignals(put_call_ratio=0.8, max_pain_distance=2.5)
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert ts.signals.put_call_ratio == pytest.approx(0.8, rel=1e-4)
        assert ts.signals.max_pain_distance == pytest.approx(2.5, rel=1e-4)

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_merges_dse_signals(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify Phase 3 DSE signals are merged into ticker_score.signals."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals(iv_hv_spread=0.15, gex=50000.0)

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert ts.signals.iv_hv_spread == pytest.approx(0.15, rel=1e-4)
        assert ts.signals.gex == pytest.approx(50000.0, rel=1e-4)

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_vol_surface_arrays_populated(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify vs_strikes and vs_dtes arrays are populated when >= 3 contracts."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.vs_strikes is not None
        assert result.vs_dtes is not None
        assert len(result.vs_strikes) == 5
        assert len(result.vs_dtes) == 5
        # Verify compute_vol_surface was called
        mock_vol_surface.assert_called_once()


class TestComputeDSEIndicatorsIVRankFilter:
    """IV rank filtering tests for _compute_dse_indicators."""

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_iv_rank_below_min_filters_out(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify iv_filtered_out=True when iv_rank < min_iv_rank."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        # Pre-populate iv_rank below the threshold
        ts.signals.iv_rank = 20.0
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(min_iv_rank=50.0),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.iv_filtered_out is True

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_iv_rank_above_min_passes(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify iv_filtered_out=False when iv_rank >= min_iv_rank.

        iv_rank is not in _PHASE3_FIELDS (it is an options-specific indicator),
        so _merge_signals does not copy it from compute_phase3_indicators output.
        To test the "passes" path, set iv_rank directly on the ticker signals
        (as would happen in production from earlier pipeline stages or
        normalization).
        """
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        # Pre-populate iv_rank on signals (simulates prior pipeline stage)
        ts.signals.iv_rank = 60.0
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(min_iv_rank=50.0),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.iv_filtered_out is False

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_iv_rank_none_filters_out(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify iv_filtered_out=True when iv_rank is None and min_iv_rank is set."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        # Phase 3 does NOT populate iv_rank — stays None
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(min_iv_rank=50.0),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.iv_filtered_out is True

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_min_iv_rank_none_always_passes(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify iv_filtered_out=False when min_iv_rank is None (disabled)."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(min_iv_rank=None),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.iv_filtered_out is False


class TestComputeDSEIndicatorsEdgeCases:
    """Edge case tests for _compute_dse_indicators."""

    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=None)
    def test_no_ohlcv_data(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
    ) -> None:
        """Verify graceful handling when ticker has no OHLCV data."""
        mock_options_ind.return_value = IndicatorSignals(put_call_ratio=0.8)

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map: dict[str, list[OHLCV]] = {}  # No OHLCV data

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert isinstance(result, _DSEResult)
        assert result.iv_filtered_out is False
        assert result.vol_result is None
        assert result.vs_strikes is None
        assert result.vs_dtes is None
        # Options-specific signals should still be merged
        assert ts.signals.put_call_ratio == pytest.approx(0.8, rel=1e-4)

    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=None)
    def test_empty_ohlcv_list(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
    ) -> None:
        """Verify graceful handling when OHLCV list is empty."""
        mock_options_ind.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map: dict[str, list[OHLCV]] = {"AAPL": []}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        assert result.vol_result is None
        assert result.vs_strikes is None
        assert result.vs_dtes is None

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface", side_effect=RuntimeError("surface failed"))
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_vol_surface_failure_non_fatal(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify vol surface failure is caught and Phase 3 indicators still computed."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_phase3.return_value = IndicatorSignals(gex=10000.0)

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        # Vol surface failed but Phase 3 indicators still computed
        assert result.vol_result is None
        assert result.iv_filtered_out is False
        # Phase 3 signals were still merged
        assert ts.signals.gex == pytest.approx(10000.0, rel=1e-4)
        # compute_phase3_indicators was called with vol_result=None
        mock_phase3.assert_called_once()
        call_kwargs = mock_phase3.call_args
        assert call_kwargs.kwargs.get("vol_result") is None

    @patch(
        f"{_MODULE}.compute_phase3_indicators",
        side_effect=RuntimeError("phase3 failed"),
    )
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_phase3_indicators_failure_non_fatal(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify Phase 3 indicator failure is caught; partial signals preserved."""
        mock_options_ind.return_value = IndicatorSignals(put_call_ratio=0.7)
        mock_vol_surface.return_value = MagicMock()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        # Options-specific signals were merged before phase3 failed
        assert ts.signals.put_call_ratio == pytest.approx(0.7, rel=1e-4)
        assert result.iv_filtered_out is False

    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_fewer_than_3_contracts_skips_vol_surface(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
    ) -> None:
        """Verify vol surface not computed when < 3 contracts."""
        mock_options_ind.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=2)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        with (
            patch(f"{_MODULE}.compute_vol_surface") as mock_vs,
            patch(f"{_MODULE}.compute_phase3_indicators") as mock_p3,
        ):
            mock_p3.return_value = IndicatorSignals()
            result = _compute_dse_indicators(
                ticker_score=ts,
                all_contracts=contracts,
                spot=185.0,
                ohlcv_map=ohlcv_map,
                spx_close=None,
                ticker_info=_make_ticker_info(),
                earnings_date=None,
                risk_free_rate=0.05,
                options_filters=OptionsFilters(),
                surface_method=SurfaceMethod.SPLINE,
                ml_config=None,
            )

            mock_vs.assert_not_called()
            assert result.vol_result is None
            assert result.vs_strikes is None
            assert result.vs_dtes is None

    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=None)
    def test_options_signals_none_not_merged(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
    ) -> None:
        """Verify None values from options_indicators are NOT merged into signals."""
        mock_options_ind.return_value = IndicatorSignals(
            put_call_ratio=None, max_pain_distance=None
        )

        ts = _make_ticker_score()
        # Pre-set a value to verify it's not overwritten
        ts.signals.put_call_ratio = 1.5
        contracts = _make_contracts(n_contracts=2)
        ohlcv_map: dict[str, list[OHLCV]] = {}

        _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        # Existing value should be preserved (None not merged)
        assert ts.signals.put_call_ratio == pytest.approx(1.5, rel=1e-4)

    @patch(f"{_MODULE}.compute_phase3_indicators")
    @patch(f"{_MODULE}.compute_vol_surface")
    @patch(f"{_MODULE}.compute_options_indicators")
    @patch(f"{_MODULE}._extract_mp_strike", return_value=185.0)
    def test_frozen_dataclass_result(
        self,
        mock_mp: MagicMock,
        mock_options_ind: MagicMock,
        mock_vol_surface: MagicMock,
        mock_phase3: MagicMock,
    ) -> None:
        """Verify _DSEResult is frozen (immutable)."""
        mock_options_ind.return_value = IndicatorSignals()
        mock_vol_surface.return_value = MagicMock()
        mock_phase3.return_value = IndicatorSignals()

        ts = _make_ticker_score()
        contracts = _make_contracts(n_contracts=5)
        ohlcv_map = {"AAPL": _make_ohlcv_list()}

        result = _compute_dse_indicators(
            ticker_score=ts,
            all_contracts=contracts,
            spot=185.0,
            ohlcv_map=ohlcv_map,
            spx_close=None,
            ticker_info=_make_ticker_info(),
            earnings_date=None,
            risk_free_rate=0.05,
            options_filters=OptionsFilters(),
            surface_method=SurfaceMethod.SPLINE,
            ml_config=None,
        )

        with pytest.raises(AttributeError):
            result.iv_filtered_out = True  # type: ignore[misc]
