"""Tests for ``_select_and_score_contracts`` and ``_build_spread`` helpers.

Extracted from ``process_ticker_options`` in issue #734.

Covers:
  _select_and_score_contracts:
  - Happy path: contracts recommended, surface indicators merged.
  - No vol surface: recommend_fn called without surface_residuals.
  - Empty contract list: returns empty list.
  - Surface indicator failure: non-fatal, recommended contracts still returned.
  - Surface indicators skipped when no recommended contracts.
  - Surface residuals built only when vol_result has z_scores.
  - Non-finite z_scores skipped in surface residuals.

  _build_spread:
  - Happy path: spread constructed from recommended contracts.
  - Spread config None: returns None.
  - Spread config disabled: returns None.
  - Empty contracts: returns None.
  - No recommended contracts: fallback to closest expiration.
  - select_strategy failure: non-fatal, returns None.
  - select_strategy returns None: returns None.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from options_arena.models import (
    IndicatorSignals,
    OptionContract,
    OptionType,
    PricingConfig,
    SignalDirection,
    SpreadConfig,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters
from options_arena.scan.phase_options import _build_spread, _select_and_score_contracts
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


def _make_contracts(
    ticker: str = "AAPL",
    n: int = 5,
    *,
    expiration: date | None = None,
) -> list[OptionContract]:
    """Create a list of option contracts with sensible defaults."""
    exp = expiration or (date.today() + timedelta(days=45))
    return [
        make_option_contract(
            ticker=ticker,
            expiration=exp,
            strike=Decimal(str(150 + i * 5)),
            option_type=OptionType.CALL if i % 2 == 0 else OptionType.PUT,
        )
        for i in range(n)
    ]


class _FakeVolSurfaceResult(NamedTuple):
    """Minimal stand-in for VolSurfaceResult used in tests."""

    z_scores: np.ndarray | None
    fitted_strikes: np.ndarray | None
    fitted_dtes: np.ndarray | None
    skew_25d: float | None = None
    smile_curvature: float | None = None
    prob_above_current: float | None = None
    atm_iv_30d: float | None = None
    atm_iv_60d: float | None = None
    fitted_ivs: np.ndarray | None = None
    residuals: np.ndarray | None = None
    r_squared: float | None = None
    is_1d_fallback: bool = False


class _FakeSurfaceIndicators(NamedTuple):
    """Minimal stand-in for VolSurfaceIndicators."""

    iv_surface_residual: float | None = None
    surface_fit_r2: float | None = None
    surface_is_1d: bool | None = None


# ---------------------------------------------------------------------------
# _select_and_score_contracts tests
# ---------------------------------------------------------------------------


class TestSelectAndScoreContractsHappyPath:
    """Happy path: contracts recommended with surface indicators merged."""

    def test_returns_recommended_contracts(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return recommended

        result = _select_and_score_contracts(
            all_contracts=contracts,
            direction=SignalDirection.BULLISH,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            pricing_config=PricingConfig(),
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            ticker_signals=IndicatorSignals(),
            recommend_fn=mock_recommend,
        )

        assert result == recommended

    def test_surface_indicators_merged(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return recommended

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([0.5]),
            fitted_strikes=np.array([float(contracts[0].strike)]),
            fitted_dtes=np.array([float(contracts[0].dte)]),
        )
        vs_strikes = np.array([float(c.strike) for c in contracts])
        vs_dtes = np.array([float(c.dte) for c in contracts])

        signals = IndicatorSignals()
        fake_surf_ind = _FakeSurfaceIndicators(
            iv_surface_residual=0.12,
            surface_fit_r2=0.95,
            surface_is_1d=False,
        )

        with patch(
            "options_arena.scan.phase_options.compute_surface_indicators",
            return_value=fake_surf_ind,
        ):
            _select_and_score_contracts(
                all_contracts=contracts,
                direction=SignalDirection.BULLISH,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                pricing_config=PricingConfig(),
                vol_result=fake_vol,
                vs_strikes=vs_strikes,
                vs_dtes=vs_dtes,
                ticker_signals=signals,
                recommend_fn=mock_recommend,
            )

        assert signals.iv_surface_residual == pytest.approx(0.12)
        assert signals.surface_fit_r2 == pytest.approx(0.95)
        assert signals.surface_is_1d == pytest.approx(0.0)  # False -> 0.0

    def test_surface_is_1d_true_maps_to_one(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return recommended

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([0.5]),
            fitted_strikes=np.array([float(contracts[0].strike)]),
            fitted_dtes=np.array([float(contracts[0].dte)]),
        )
        vs_strikes = np.array([float(c.strike) for c in contracts])
        vs_dtes = np.array([float(c.dte) for c in contracts])

        signals = IndicatorSignals()
        fake_surf_ind = _FakeSurfaceIndicators(surface_is_1d=True)

        with patch(
            "options_arena.scan.phase_options.compute_surface_indicators",
            return_value=fake_surf_ind,
        ):
            _select_and_score_contracts(
                all_contracts=contracts,
                direction=SignalDirection.BULLISH,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                pricing_config=PricingConfig(),
                vol_result=fake_vol,
                vs_strikes=vs_strikes,
                vs_dtes=vs_dtes,
                ticker_signals=signals,
                recommend_fn=mock_recommend,
            )

        assert signals.surface_is_1d == pytest.approx(1.0)


class TestSelectAndScoreContractsNoVolSurface:
    """No vol surface: recommend_fn called without surface residuals."""

    def test_no_vol_result_passes_none_residuals(self) -> None:
        contracts = _make_contracts()
        captured_kwargs: dict[str, object] = {}

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            captured_kwargs.update(kwargs)
            return [contracts[0]]

        _select_and_score_contracts(
            all_contracts=contracts,
            direction=SignalDirection.BULLISH,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            pricing_config=PricingConfig(),
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            ticker_signals=IndicatorSignals(),
            recommend_fn=mock_recommend,
        )

        assert captured_kwargs["surface_residuals"] is None


class TestSelectAndScoreContractsEdgeCases:
    """Edge cases: empty contracts, failures, non-finite z-scores."""

    def test_empty_contracts_returns_empty(self) -> None:
        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return []

        result = _select_and_score_contracts(
            all_contracts=[],
            direction=SignalDirection.BULLISH,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            pricing_config=PricingConfig(),
            vol_result=None,
            vs_strikes=None,
            vs_dtes=None,
            ticker_signals=IndicatorSignals(),
            recommend_fn=mock_recommend,
        )

        assert result == []

    def test_surface_indicator_failure_non_fatal(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return recommended

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([0.5]),
            fitted_strikes=np.array([float(contracts[0].strike)]),
            fitted_dtes=np.array([float(contracts[0].dte)]),
        )
        vs_strikes = np.array([float(c.strike) for c in contracts])
        vs_dtes = np.array([float(c.dte) for c in contracts])

        with patch(
            "options_arena.scan.phase_options.compute_surface_indicators",
            side_effect=RuntimeError("surface boom"),
        ):
            result = _select_and_score_contracts(
                all_contracts=contracts,
                direction=SignalDirection.BULLISH,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                pricing_config=PricingConfig(),
                vol_result=fake_vol,
                vs_strikes=vs_strikes,
                vs_dtes=vs_dtes,
                ticker_signals=IndicatorSignals(),
                recommend_fn=mock_recommend,
            )

        # Contracts still returned despite surface indicator failure
        assert result == recommended

    def test_surface_indicators_skipped_when_no_recommended(self) -> None:
        contracts = _make_contracts()

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            return []

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([0.5]),
            fitted_strikes=np.array([150.0]),
            fitted_dtes=np.array([45.0]),
        )
        vs_strikes = np.array([float(c.strike) for c in contracts])
        vs_dtes = np.array([float(c.dte) for c in contracts])

        signals = IndicatorSignals()

        with patch(
            "options_arena.scan.phase_options.compute_surface_indicators",
        ) as mock_surf:
            _select_and_score_contracts(
                all_contracts=contracts,
                direction=SignalDirection.BULLISH,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                pricing_config=PricingConfig(),
                vol_result=fake_vol,
                vs_strikes=vs_strikes,
                vs_dtes=vs_dtes,
                ticker_signals=signals,
                recommend_fn=mock_recommend,
            )

            # compute_surface_indicators not called when no recommended
            mock_surf.assert_not_called()

    def test_non_finite_z_scores_skipped(self) -> None:
        contracts = _make_contracts(n=2)
        captured_kwargs: dict[str, object] = {}

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            captured_kwargs.update(kwargs)
            return []

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([float("nan"), float("inf")]),
            fitted_strikes=np.array([float(contracts[0].strike), float(contracts[1].strike)]),
            fitted_dtes=np.array([float(contracts[0].dte), float(contracts[1].dte)]),
        )

        _select_and_score_contracts(
            all_contracts=contracts,
            direction=SignalDirection.BULLISH,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            pricing_config=PricingConfig(),
            vol_result=fake_vol,
            vs_strikes=None,
            vs_dtes=None,
            ticker_signals=IndicatorSignals(),
            recommend_fn=mock_recommend,
        )

        # Surface residuals should be empty dict (non-finite z-scores skipped)
        residuals = captured_kwargs["surface_residuals"]
        assert residuals is not None
        assert len(residuals) == 0  # type: ignore[arg-type]

    def test_surface_residuals_built_from_vol_result(self) -> None:
        """Verify surface residuals mapping matches z_scores to contracts."""
        contracts = _make_contracts(n=2)
        captured_kwargs: dict[str, object] = {}

        def mock_recommend(**kwargs: object) -> list[OptionContract]:
            captured_kwargs.update(kwargs)
            return []

        fake_vol = _FakeVolSurfaceResult(
            z_scores=np.array([1.5, -0.3]),
            fitted_strikes=np.array([float(contracts[0].strike), float(contracts[1].strike)]),
            fitted_dtes=np.array([float(contracts[0].dte), float(contracts[1].dte)]),
        )

        _select_and_score_contracts(
            all_contracts=contracts,
            direction=SignalDirection.BULLISH,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            pricing_config=PricingConfig(),
            vol_result=fake_vol,
            vs_strikes=None,
            vs_dtes=None,
            ticker_signals=IndicatorSignals(),
            recommend_fn=mock_recommend,
        )

        residuals = captured_kwargs["surface_residuals"]
        assert residuals is not None
        assert len(residuals) == 2  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_spread tests
# ---------------------------------------------------------------------------


class TestBuildSpreadHappyPath:
    """Happy path: spread constructed from recommended contracts."""

    def test_returns_spread_analysis(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        mock_spread = MagicMock()
        mock_spread.spread.spread_type.value = "bull_call_spread"
        mock_spread.strategy_rationale = "Test rationale for bull call spread strategy"

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=mock_spread,
        ):
            result = _build_spread(
                ticker="AAPL",
                all_contracts=contracts,
                recommended=recommended,
                direction=SignalDirection.BULLISH,
                composite_score=80.0,
                iv_rank=0.5,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                spread_config=SpreadConfig(enabled=True),
            )

        assert result is mock_spread

    def test_passes_correct_args_to_select_strategy(self) -> None:
        exp = date.today() + timedelta(days=45)
        contracts = _make_contracts(expiration=exp)
        recommended = [contracts[0]]

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=None,
        ) as mock_select:
            _build_spread(
                ticker="AAPL",
                all_contracts=contracts,
                recommended=recommended,
                direction=SignalDirection.BULLISH,
                composite_score=80.0,
                iv_rank=0.5,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                spread_config=SpreadConfig(enabled=True),
            )

        mock_select.assert_called_once()
        call_kwargs = mock_select.call_args
        assert call_kwargs.kwargs["direction"] == SignalDirection.BULLISH
        assert call_kwargs.kwargs["confidence"] == pytest.approx(0.8)
        assert call_kwargs.kwargs["iv_rank"] == pytest.approx(0.5)
        assert call_kwargs.kwargs["spot_price"] == pytest.approx(185.0)
        assert call_kwargs.kwargs["risk_free_rate"] == pytest.approx(0.05)
        assert call_kwargs.kwargs["dividend_yield"] == pytest.approx(0.005)


class TestBuildSpreadGuards:
    """Guard conditions: None config, disabled, empty contracts."""

    def test_spread_config_none_returns_none(self) -> None:
        result = _build_spread(
            ticker="AAPL",
            all_contracts=_make_contracts(),
            recommended=[],
            direction=SignalDirection.BULLISH,
            composite_score=80.0,
            iv_rank=0.5,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            spread_config=None,
        )
        assert result is None

    def test_spread_config_disabled_returns_none(self) -> None:
        result = _build_spread(
            ticker="AAPL",
            all_contracts=_make_contracts(),
            recommended=[],
            direction=SignalDirection.BULLISH,
            composite_score=80.0,
            iv_rank=0.5,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            spread_config=SpreadConfig(enabled=False),
        )
        assert result is None

    def test_empty_contracts_returns_none(self) -> None:
        result = _build_spread(
            ticker="AAPL",
            all_contracts=[],
            recommended=[],
            direction=SignalDirection.BULLISH,
            composite_score=80.0,
            iv_rank=0.5,
            spot=185.0,
            risk_free_rate=0.05,
            dividend_yield=0.005,
            options_filters=OptionsFilters(),
            spread_config=SpreadConfig(enabled=True),
        )
        assert result is None


class TestBuildSpreadNoRecommended:
    """Fallback to closest expiration when no recommended contracts."""

    def test_fallback_to_closest_expiration(self) -> None:
        exp = date.today() + timedelta(days=45)
        contracts = _make_contracts(expiration=exp)

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=None,
        ) as mock_select:
            _build_spread(
                ticker="AAPL",
                all_contracts=contracts,
                recommended=[],
                direction=SignalDirection.BEARISH,
                composite_score=60.0,
                iv_rank=None,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                spread_config=SpreadConfig(enabled=True),
            )

        # select_strategy called even with no recommended contracts
        mock_select.assert_called_once()
        call_kwargs = mock_select.call_args
        # Confidence derived from composite_score / 100
        assert call_kwargs.kwargs["confidence"] == pytest.approx(0.6)


class TestBuildSpreadFailures:
    """select_strategy failure is non-fatal."""

    def test_select_strategy_exception_returns_none(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            side_effect=RuntimeError("strategy boom"),
        ):
            result = _build_spread(
                ticker="AAPL",
                all_contracts=contracts,
                recommended=recommended,
                direction=SignalDirection.BULLISH,
                composite_score=80.0,
                iv_rank=0.5,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                spread_config=SpreadConfig(enabled=True),
            )

        assert result is None

    def test_select_strategy_returns_none(self) -> None:
        contracts = _make_contracts()
        recommended = [contracts[0]]

        with patch(
            "options_arena.scan.phase_options.select_strategy",
            return_value=None,
        ):
            result = _build_spread(
                ticker="AAPL",
                all_contracts=contracts,
                recommended=recommended,
                direction=SignalDirection.BULLISH,
                composite_score=80.0,
                iv_rank=0.5,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
                options_filters=OptionsFilters(),
                spread_config=SpreadConfig(enabled=True),
            )

        assert result is None
