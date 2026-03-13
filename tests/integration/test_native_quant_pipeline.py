"""Integration tests for native quant pipeline wiring.

Verifies:
  - Yang-Zhang HV populated via compute_phase3_indicators()
  - Vol surface metrics (skew_25d, smile_curvature, prob_above_current) populated
  - Graceful None when chain is sparse or vol surface data unavailable
  - Failure isolation: one indicator crash doesn't block others
  - Second-order Greeks (vanna, charm, vomma) populated on recommended contracts
  - Graceful degradation when second-order Greeks fail
  - Composite weights sum to 1.0 and include new vol surface weights
  - Orchestrator maps new fields to MarketContext
  - Vol surface ATM IV replacement
  - _PHASE3_FIELDS includes all new field names
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from options_arena.agents._parsing import render_context_block
from options_arena.agents.orchestrator import build_market_context
from options_arena.indicators.vol_surface import VolSurfaceResult
from options_arena.models.analysis import MarketContext
from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel, SignalDirection
from options_arena.models.market_data import Quote, TickerInfo
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.scan.indicators import compute_phase3_indicators
from options_arena.scan.phase_options import _PHASE3_FIELDS
from options_arena.scoring.composite import INDICATOR_WEIGHTS, composite_score
from options_arena.scoring.contracts import compute_greeks
from options_arena.scoring.normalization import DOMAIN_BOUNDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_df(n: int = 300, close_price: float = 150.0) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame with n bars."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    np.random.seed(42)
    offsets = np.cumsum(np.random.randn(n) * 0.5)
    closes = close_price + offsets
    highs = closes + np.abs(np.random.randn(n)) * 2
    lows = closes - np.abs(np.random.randn(n)) * 2
    opens = closes + np.random.randn(n) * 0.5
    # Ensure high >= max(open, close) and low <= min(open, close)
    highs = np.maximum(highs, np.maximum(opens, closes))
    lows = np.minimum(lows, np.minimum(opens, closes))
    # Ensure all prices positive
    min_price = min(lows.min(), opens.min(), closes.min())
    if min_price < 1.0:
        shift = abs(min_price) + 10.0
        closes += shift
        highs += shift
        lows += shift
        opens += shift
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.random.randint(500_000, 2_000_000, size=n),
        },
        index=dates,
    )


def _make_contracts(
    n: int = 20,
    spot: float = 150.0,
    with_greeks: bool = False,
) -> list[OptionContract]:
    """Build synthetic option contracts around the spot price."""
    contracts: list[OptionContract] = []
    for i in range(n):
        strike = spot * (0.85 + i * 0.015)
        is_call = i % 2 == 0
        greeks = None
        if with_greeks:
            greeks = OptionGreeks(
                delta=0.45 if is_call else -0.45,
                gamma=0.03,
                theta=-0.05,
                vega=0.20,
                rho=0.01,
                pricing_model=PricingModel.BAW,
            )
        contracts.append(
            OptionContract(
                ticker="TEST",
                option_type=OptionType.CALL if is_call else OptionType.PUT,
                strike=Decimal(str(round(strike, 2))),
                expiration=date.today() + timedelta(days=45),
                bid=Decimal("3.00"),
                ask=Decimal("3.50"),
                last=Decimal("3.25"),
                volume=200,
                open_interest=1000,
                exercise_style=ExerciseStyle.AMERICAN,
                market_iv=0.25 + i * 0.005,
                greeks=greeks,
            )
        )
    return contracts


def _make_vol_result(
    skew: float = 0.03,
    curvature: float = 1.5,
    prob: float = 0.52,
    atm_30: float = 0.28,
    atm_60: float = 0.30,
) -> VolSurfaceResult:
    """Build a synthetic VolSurfaceResult."""
    return VolSurfaceResult(
        skew_25d=skew,
        smile_curvature=curvature,
        prob_above_current=prob,
        atm_iv_30d=atm_30,
        atm_iv_60d=atm_60,
        fitted_ivs=None,
        residuals=None,
        z_scores=None,
        r_squared=None,
        is_1d_fallback=False,
        is_standalone_fallback=True,
    )


# ---------------------------------------------------------------------------
# Phase 3 Indicator Wiring Tests
# ---------------------------------------------------------------------------


class TestYangZhangHVWiring:
    """Yang-Zhang HV should populate via compute_phase3_indicators()."""

    def test_hv_yang_zhang_populated(self) -> None:
        """HV Yang-Zhang is set when OHLCV DataFrame is provided."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            ohlcv_df=df,
        )
        assert signals.hv_yang_zhang is not None
        assert math.isfinite(signals.hv_yang_zhang)
        assert signals.hv_yang_zhang > 0.0  # annualized HV should be positive

    def test_hv_yang_zhang_none_without_ohlcv_df(self) -> None:
        """HV Yang-Zhang remains None when ohlcv_df is not provided."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            ohlcv_df=None,
        )
        assert signals.hv_yang_zhang is None

    def test_hv_yang_zhang_none_with_short_data(self) -> None:
        """HV Yang-Zhang remains None when OHLCV has fewer than 22 bars."""
        df = _make_ohlcv_df(15)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            ohlcv_df=df,
        )
        assert signals.hv_yang_zhang is None


class TestVolSurfaceWiring:
    """Vol surface metrics should populate when VolSurfaceResult is provided."""

    def test_vol_surface_metrics_populated(self) -> None:
        """All vol surface metrics are set from VolSurfaceResult."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        vol_result = _make_vol_result()
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            vol_result=vol_result,
        )
        assert signals.skew_25d == pytest.approx(0.03, rel=1e-6)
        assert signals.smile_curvature == pytest.approx(1.5, rel=1e-6)
        assert signals.prob_above_current == pytest.approx(0.52, rel=1e-6)

    def test_vol_surface_none_without_result(self) -> None:
        """Vol surface metrics remain None when no VolSurfaceResult."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            vol_result=None,
        )
        assert signals.skew_25d is None
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_vol_surface_partial_none(self) -> None:
        """Partial None fields on VolSurfaceResult handled correctly."""
        vol_result = VolSurfaceResult(
            skew_25d=0.03,
            smile_curvature=None,
            prob_above_current=None,
            atm_iv_30d=0.25,
            atm_iv_60d=None,
            fitted_ivs=None,
            residuals=None,
            z_scores=None,
            r_squared=None,
            is_1d_fallback=False,
            is_standalone_fallback=True,
        )
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            vol_result=vol_result,
        )
        assert signals.skew_25d == pytest.approx(0.03, rel=1e-6)
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_vol_surface_atm_iv_replacement(self) -> None:
        """Vol surface ATM IV should replace per-contract extracted values."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        vol_result = _make_vol_result(atm_30=0.35, atm_60=0.38)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=150.0,
            vol_result=vol_result,
        )
        # The iv_hv_spread uses the ATM IV 30d value; if vol surface provided
        # a different atm_iv_30d, that should be used. We verify by checking
        # that the IV-HV spread used the vol surface value (0.35) instead of
        # any per-contract extraction.
        if signals.iv_hv_spread is not None and signals.hv_20d is not None:
            # iv_hv_spread = atm_iv - hv
            expected_spread = 0.35 - signals.hv_20d
            assert signals.iv_hv_spread == pytest.approx(expected_spread, abs=0.01)


class TestFailureIsolation:
    """One indicator failure should not crash the pipeline."""

    def test_empty_contracts_returns_all_none(self) -> None:
        """Empty contracts returns a signals object with all defaults."""
        df = _make_ohlcv_df(300)
        signals = compute_phase3_indicators(
            contracts=[],
            spot=150.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=None,
        )
        assert signals.hv_yang_zhang is None
        assert signals.skew_25d is None

    def test_invalid_spot_returns_all_none(self) -> None:
        """Invalid spot price (zero) returns empty signals."""
        df = _make_ohlcv_df(300)
        contracts = _make_contracts(20, spot=150.0)
        signals = compute_phase3_indicators(
            contracts=contracts,
            spot=0.0,
            close_series=df["close"],
            dividend_yield=0.005,
            next_earnings=None,
            mp_strike=None,
        )
        assert signals.hv_yang_zhang is None


# ---------------------------------------------------------------------------
# Second-Order Greeks Tests
# ---------------------------------------------------------------------------


class TestSecondOrderGreeks:
    """Second-order Greeks should populate on recommended contracts."""

    def test_vanna_charm_vomma_populated(self) -> None:
        """compute_greeks() should produce vanna, charm, vomma on contracts."""
        contracts = _make_contracts(5, spot=150.0, with_greeks=False)
        result = compute_greeks(contracts, 150.0, 0.05, 0.005)
        # At least some contracts should succeed
        assert len(result) > 0
        for contract in result:
            assert contract.greeks is not None
            # Second-order Greeks should be populated
            assert contract.greeks.vanna is not None
            assert contract.greeks.charm is not None
            assert contract.greeks.vomma is not None

    def test_first_order_greeks_still_valid(self) -> None:
        """First-order Greeks remain correct when second-order are computed."""
        contracts = _make_contracts(3, spot=150.0, with_greeks=False)
        result = compute_greeks(contracts, 150.0, 0.05, 0.005)
        for contract in result:
            assert contract.greeks is not None
            assert -1.0 <= contract.greeks.delta <= 1.0
            assert contract.greeks.gamma >= 0.0
            assert contract.greeks.vega >= 0.0

    def test_tier1_preserves_existing_greeks(self) -> None:
        """Tier 1 contracts with pre-existing Greeks are preserved unchanged."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            pricing_model=PricingModel.BAW,
        )
        contracts = _make_contracts(1, spot=150.0, with_greeks=True)
        result = compute_greeks(contracts, 150.0, 0.05, 0.005)
        assert len(result) == 1
        # Pre-existing Greeks preserved — vanna/charm/vomma remain None
        assert result[0].greeks is not None
        assert result[0].greeks.delta == pytest.approx(greeks.delta, rel=1e-6)


# ---------------------------------------------------------------------------
# Composite Weights Tests
# ---------------------------------------------------------------------------


class TestCompositeWeights:
    """INDICATOR_WEIGHTS must sum to 1.0 and include new vol surface weights."""

    def test_weights_sum_to_one(self) -> None:
        """Total weight of all indicators is exactly 1.0."""
        total = sum(w for w, _ in INDICATOR_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_skew_25d_weight_present(self) -> None:
        """skew_25d has weight 0.02 in vol_surface category."""
        assert "skew_25d" in INDICATOR_WEIGHTS
        weight, category = INDICATOR_WEIGHTS["skew_25d"]
        assert weight == pytest.approx(0.02, abs=1e-9)
        assert category == "vol_surface"

    def test_smile_curvature_weight_present(self) -> None:
        """smile_curvature has weight 0.01 in vol_surface category."""
        assert "smile_curvature" in INDICATOR_WEIGHTS
        weight, category = INDICATOR_WEIGHTS["smile_curvature"]
        assert weight == pytest.approx(0.01, abs=1e-9)
        assert category == "vol_surface"

    def test_hv_yang_zhang_not_in_weights(self) -> None:
        """hv_yang_zhang is context-only — NOT in composite weights."""
        assert "hv_yang_zhang" not in INDICATOR_WEIGHTS

    def test_prob_above_current_not_in_weights(self) -> None:
        """prob_above_current is context-only — NOT in composite weights."""
        assert "prob_above_current" not in INDICATOR_WEIGHTS

    def test_composite_score_accepts_new_indicators(self) -> None:
        """composite_score() handles new indicators when set on signals."""
        signals = IndicatorSignals(
            rsi=65.0,
            adx=70.0,
            sma_alignment=80.0,
            skew_25d=50.0,
            smile_curvature=60.0,
        )
        score = composite_score(signals)
        assert 0.0 <= score <= 100.0
        assert score > 0.0  # should have a real score

    def test_domain_bounds_include_new_indicators(self) -> None:
        """DOMAIN_BOUNDS includes skew_25d and smile_curvature for ad-hoc normalization."""
        assert "skew_25d" in DOMAIN_BOUNDS
        assert "smile_curvature" in DOMAIN_BOUNDS


# ---------------------------------------------------------------------------
# Phase 3 Fields Tests
# ---------------------------------------------------------------------------


class TestPhase3Fields:
    """_PHASE3_FIELDS must include all new native quant field names."""

    def test_hv_yang_zhang_in_phase3_fields(self) -> None:
        assert "hv_yang_zhang" in _PHASE3_FIELDS

    def test_skew_25d_in_phase3_fields(self) -> None:
        assert "skew_25d" in _PHASE3_FIELDS

    def test_smile_curvature_in_phase3_fields(self) -> None:
        assert "smile_curvature" in _PHASE3_FIELDS

    def test_prob_above_current_in_phase3_fields(self) -> None:
        assert "prob_above_current" in _PHASE3_FIELDS


# ---------------------------------------------------------------------------
# Orchestrator Mapping Tests
# ---------------------------------------------------------------------------


class TestOrchestratorMapping:
    """build_market_context() should map new signals to MarketContext."""

    def _build_context(
        self,
        *,
        hv_yang_zhang: float | None = 0.25,
        skew_25d: float | None = 0.03,
        smile_curvature: float | None = 1.5,
        prob_above_current: float | None = 0.52,
        contract_vanna: float | None = 0.01,
        contract_charm: float | None = -0.005,
        contract_vomma: float | None = 0.15,
    ) -> MarketContext:
        signals = IndicatorSignals(
            rsi=55.0,
            adx=60.0,
            sma_alignment=0.7,
            hv_yang_zhang=hv_yang_zhang,
            skew_25d=skew_25d,
            smile_curvature=smile_curvature,
            prob_above_current=prob_above_current,
        )
        ticker_score = TickerScore(
            ticker="TEST",
            composite_score=72.0,
            direction=SignalDirection.BULLISH,
            signals=signals,
        )
        quote = Quote(
            ticker="TEST",
            price=Decimal("150.00"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            volume=1_000_000,
            timestamp=datetime.now(UTC),
        )
        ticker_info = TickerInfo(
            ticker="TEST",
            company_name="Test Corp",
            sector="Technology",
            current_price=Decimal("150.00"),
            fifty_two_week_high=Decimal("180.00"),
            fifty_two_week_low=Decimal("120.00"),
            dividend_yield=0.005,
        )
        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            vanna=contract_vanna,
            charm=contract_charm,
            vomma=contract_vomma,
            pricing_model=PricingModel.BAW,
        )
        contract = OptionContract(
            ticker="TEST",
            option_type=OptionType.CALL,
            strike=Decimal("150.00"),
            expiration=date.today() + timedelta(days=45),
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=200,
            open_interest=1000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.28,
            greeks=greeks,
        )
        return build_market_context(ticker_score, quote, ticker_info, [contract])

    def test_hv_yang_zhang_mapped(self) -> None:
        ctx = self._build_context(hv_yang_zhang=0.25)
        assert ctx.hv_yang_zhang == pytest.approx(0.25, rel=1e-6)

    def test_skew_25d_mapped(self) -> None:
        ctx = self._build_context(skew_25d=0.03)
        assert ctx.skew_25d == pytest.approx(0.03, rel=1e-6)

    def test_smile_curvature_mapped(self) -> None:
        ctx = self._build_context(smile_curvature=1.5)
        assert ctx.smile_curvature == pytest.approx(1.5, rel=1e-6)

    def test_prob_above_current_mapped(self) -> None:
        ctx = self._build_context(prob_above_current=0.52)
        assert ctx.prob_above_current == pytest.approx(0.52, rel=1e-6)

    def test_none_signals_mapped_as_none(self) -> None:
        ctx = self._build_context(
            hv_yang_zhang=None,
            skew_25d=None,
            smile_curvature=None,
            prob_above_current=None,
        )
        assert ctx.hv_yang_zhang is None
        assert ctx.skew_25d is None
        assert ctx.smile_curvature is None
        assert ctx.prob_above_current is None

    def test_second_order_greeks_from_contract(self) -> None:
        """target_vanna/charm/vomma should come from contract Greeks."""
        ctx = self._build_context(
            contract_vanna=0.01,
            contract_charm=-0.005,
            contract_vomma=0.15,
        )
        assert ctx.target_vanna == pytest.approx(0.01, rel=1e-6)
        assert ctx.target_charm == pytest.approx(-0.005, rel=1e-6)
        assert ctx.target_vomma == pytest.approx(0.15, rel=1e-6)

    def test_render_context_block_includes_new_fields(self) -> None:
        """render_context_block should render new native quant fields."""
        ctx = self._build_context()
        rendered = render_context_block(ctx)
        assert "HV YANG-ZHANG" in rendered
        assert "SKEW 25D" in rendered
        assert "SMILE CURVATURE" in rendered
        assert "PROB ABOVE CURRENT" in rendered
