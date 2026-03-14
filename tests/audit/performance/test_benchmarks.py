"""Performance benchmarks for all 87 mathematical functions.

pytest-benchmark tests grouped by module:
- Pricing (14): BSM price/greeks/vega/iv/second_order, BAW price/greeks/iv/second_order,
  dispatch price/greeks/iv/second_order, intrinsic_value
- Indicators (57): oscillators, trend, volatility, volume, moving_averages,
  options_specific, iv_analytics, hv_estimators, flow_analytics, regime, vol_surface
- Scoring (16): normalization, composite, direction, contracts, dimensional
- Orchestration (5): agreement_score, vote_entropy, log_odds_pool, citation_density,
  _get_majority_direction

All tests use ``@pytest.mark.audit_performance`` and ``benchmark(func, *args)``.
No mocking — real function execution for accurate timing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from options_arena.models.enums import (
    ExerciseStyle,
    MarketRegime,
    OptionType,
    SignalDirection,
)
from options_arena.models.scan import IndicatorSignals

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from options_arena.models.options import OptionContract


# ===========================================================================
# Pricing Benchmarks (14 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestPricingBSMBenchmarks:
    """BSM pricing function benchmarks (5 functions)."""

    @pytest.mark.benchmark(group="pricing")
    def test_bsm_price(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BSM European call pricing."""
        from options_arena.pricing.bsm import bsm_price

        p = atm_pricing_params
        benchmark(bsm_price, p["S"], p["K"], p["T"], p["r"], p["q"], p["sigma"], OptionType.CALL)

    @pytest.mark.benchmark(group="pricing")
    def test_bsm_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BSM Greeks computation."""
        from options_arena.pricing.bsm import bsm_greeks

        p = atm_pricing_params
        benchmark(bsm_greeks, p["S"], p["K"], p["T"], p["r"], p["q"], p["sigma"], OptionType.CALL)

    @pytest.mark.benchmark(group="pricing")
    def test_bsm_vega(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BSM standalone vega."""
        from options_arena.pricing.bsm import bsm_vega

        p = atm_pricing_params
        benchmark(bsm_vega, p["S"], p["K"], p["T"], p["r"], p["q"], p["sigma"])

    @pytest.mark.benchmark(group="pricing")
    def test_bsm_iv(
        self,
        benchmark: BenchmarkFixture,
        atm_pricing_params: dict[str, float],
        iv_market_price: float,
    ) -> None:
        """Benchmark BSM Newton-Raphson IV solver."""
        from options_arena.pricing.bsm import bsm_iv

        p = atm_pricing_params
        benchmark(bsm_iv, iv_market_price, p["S"], p["K"], p["T"], p["r"], p["q"], OptionType.CALL)

    @pytest.mark.benchmark(group="pricing")
    def test_bsm_second_order_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BSM second-order Greeks (vanna, charm, vomma)."""
        from options_arena.pricing.bsm import bsm_second_order_greeks

        p = atm_pricing_params
        benchmark(
            bsm_second_order_greeks,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            p["q"],
            p["sigma"],
            OptionType.CALL,
        )


@pytest.mark.audit_performance
class TestPricingAmericanBenchmarks:
    """BAW American pricing function benchmarks (4 functions)."""

    @pytest.mark.benchmark(group="pricing")
    def test_american_price(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BAW American put pricing (has early exercise premium)."""
        from options_arena.pricing.american import american_price

        p = atm_pricing_params
        benchmark(american_price, p["S"], p["K"], p["T"], p["r"], 0.02, p["sigma"], OptionType.PUT)

    @pytest.mark.benchmark(group="pricing")
    def test_american_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BAW finite-difference Greeks."""
        from options_arena.pricing.american import american_greeks

        p = atm_pricing_params
        benchmark(
            american_greeks, p["S"], p["K"], p["T"], p["r"], 0.02, p["sigma"], OptionType.PUT
        )

    @pytest.mark.benchmark(group="pricing")
    def test_american_iv(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BAW brentq IV solver."""
        from options_arena.pricing.american import american_iv, american_price

        p = atm_pricing_params
        # Compute a valid market price for the solver
        market_price = american_price(
            p["S"], p["K"], p["T"], p["r"], 0.02, p["sigma"], OptionType.PUT
        )
        benchmark(american_iv, market_price, p["S"], p["K"], p["T"], p["r"], 0.02, OptionType.PUT)

    @pytest.mark.benchmark(group="pricing")
    def test_american_second_order_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark BAW second-order Greeks (finite-difference cross-bumps)."""
        from options_arena.pricing.american import american_second_order_greeks

        p = atm_pricing_params
        benchmark(
            american_second_order_greeks,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            0.02,
            p["sigma"],
            OptionType.PUT,
        )


@pytest.mark.audit_performance
class TestPricingDispatchBenchmarks:
    """Dispatch routing benchmarks (4 functions)."""

    @pytest.mark.benchmark(group="pricing")
    def test_option_price(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark dispatch option_price (AMERICAN routing)."""
        from options_arena.pricing.dispatch import option_price

        p = atm_pricing_params
        benchmark(
            option_price,
            ExerciseStyle.AMERICAN,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            0.02,
            p["sigma"],
            OptionType.CALL,
        )

    @pytest.mark.benchmark(group="pricing")
    def test_option_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark dispatch option_greeks (AMERICAN routing)."""
        from options_arena.pricing.dispatch import option_greeks

        p = atm_pricing_params
        benchmark(
            option_greeks,
            ExerciseStyle.AMERICAN,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            0.02,
            p["sigma"],
            OptionType.CALL,
        )

    @pytest.mark.benchmark(group="pricing")
    def test_option_iv(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark dispatch option_iv (AMERICAN routing)."""
        from options_arena.pricing.american import american_price
        from options_arena.pricing.dispatch import option_iv

        p = atm_pricing_params
        market_price = american_price(
            p["S"], p["K"], p["T"], p["r"], 0.02, p["sigma"], OptionType.CALL
        )
        benchmark(
            option_iv,
            ExerciseStyle.AMERICAN,
            market_price,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            0.02,
            OptionType.CALL,
        )

    @pytest.mark.benchmark(group="pricing")
    def test_option_second_order_greeks(
        self, benchmark: BenchmarkFixture, atm_pricing_params: dict[str, float]
    ) -> None:
        """Benchmark dispatch option_second_order_greeks (AMERICAN routing)."""
        from options_arena.pricing.dispatch import option_second_order_greeks

        p = atm_pricing_params
        benchmark(
            option_second_order_greeks,
            ExerciseStyle.AMERICAN,
            p["S"],
            p["K"],
            p["T"],
            p["r"],
            0.02,
            p["sigma"],
            OptionType.CALL,
        )


@pytest.mark.audit_performance
class TestPricingCommonBenchmarks:
    """Common pricing helper benchmarks (1 function)."""

    @pytest.mark.benchmark(group="pricing")
    def test_intrinsic_value(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark intrinsic_value computation."""
        from options_arena.pricing._common import intrinsic_value

        benchmark(intrinsic_value, 105.0, 100.0, OptionType.CALL)


# ===========================================================================
# Indicator Benchmarks — Oscillators (3 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestOscillatorBenchmarks:
    """Oscillator indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_rsi(self, benchmark: BenchmarkFixture, sample_close_series: pd.Series) -> None:
        """Benchmark RSI on 250-row Series."""
        from options_arena.indicators.oscillators import rsi

        benchmark(rsi, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_stoch_rsi(self, benchmark: BenchmarkFixture, sample_close_series: pd.Series) -> None:
        """Benchmark Stochastic RSI on 250-row Series."""
        from options_arena.indicators.oscillators import stoch_rsi

        benchmark(stoch_rsi, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_williams_r(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark Williams %R on 250-row Series."""
        from options_arena.indicators.oscillators import williams_r

        benchmark(williams_r, sample_high_series, sample_low_series, sample_close_series)


# ===========================================================================
# Indicator Benchmarks — Trend (7 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestTrendBenchmarks:
    """Trend indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_roc(self, benchmark: BenchmarkFixture, sample_close_series: pd.Series) -> None:
        """Benchmark Rate of Change on 250-row Series."""
        from options_arena.indicators.trend import roc

        benchmark(roc, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_adx(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark ADX on 250-row Series."""
        from options_arena.indicators.trend import adx

        benchmark(adx, sample_high_series, sample_low_series, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_supertrend(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark Supertrend on 250-row Series."""
        from options_arena.indicators.trend import supertrend

        benchmark(supertrend, sample_high_series, sample_low_series, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_macd(self, benchmark: BenchmarkFixture, sample_close_series: pd.Series) -> None:
        """Benchmark MACD on 250-row Series."""
        from options_arena.indicators.trend import macd

        benchmark(macd, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_multi_tf_alignment(
        self, benchmark: BenchmarkFixture, sample_close_series: pd.Series
    ) -> None:
        """Benchmark multi-timeframe alignment."""
        from options_arena.indicators.trend import compute_multi_tf_alignment, supertrend

        # Pre-compute daily supertrend and use close as weekly proxy
        daily_st = supertrend(
            sample_close_series * 1.01,  # proxy high
            sample_close_series * 0.99,  # proxy low
            sample_close_series,
        )
        weekly_close = sample_close_series.iloc[::5]  # downsample
        benchmark(compute_multi_tf_alignment, daily_st, weekly_close)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_rsi_divergence(
        self, benchmark: BenchmarkFixture, sample_close_series: pd.Series
    ) -> None:
        """Benchmark RSI divergence detection."""
        from options_arena.indicators.oscillators import rsi as rsi_fn
        from options_arena.indicators.trend import compute_rsi_divergence

        rsi_series = rsi_fn(sample_close_series)
        benchmark(compute_rsi_divergence, sample_close_series, rsi_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_adx_exhaustion(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark ADX exhaustion signal."""
        from options_arena.indicators.trend import adx as adx_fn
        from options_arena.indicators.trend import compute_adx_exhaustion

        adx_series = adx_fn(sample_high_series, sample_low_series, sample_close_series)
        benchmark(compute_adx_exhaustion, adx_series)


# ===========================================================================
# Indicator Benchmarks — Volatility (3 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestVolatilityBenchmarks:
    """Volatility indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_bb_width(self, benchmark: BenchmarkFixture, sample_close_series: pd.Series) -> None:
        """Benchmark Bollinger Band width on 250-row Series."""
        from options_arena.indicators.volatility import bb_width

        benchmark(bb_width, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_atr_percent(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark ATR% on 250-row Series."""
        from options_arena.indicators.volatility import atr_percent

        benchmark(atr_percent, sample_high_series, sample_low_series, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_keltner_width(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark Keltner Channel width on 250-row Series."""
        from options_arena.indicators.volatility import keltner_width

        benchmark(keltner_width, sample_high_series, sample_low_series, sample_close_series)


# ===========================================================================
# Indicator Benchmarks — Volume (3 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestVolumeBenchmarks:
    """Volume indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_obv_trend(
        self,
        benchmark: BenchmarkFixture,
        sample_close_series: pd.Series,
        sample_volume_series: pd.Series,
    ) -> None:
        """Benchmark OBV trend on 250-row Series."""
        from options_arena.indicators.volume import obv_trend

        benchmark(obv_trend, sample_close_series, sample_volume_series)

    @pytest.mark.benchmark(group="indicators")
    def test_relative_volume(
        self, benchmark: BenchmarkFixture, sample_volume_series: pd.Series
    ) -> None:
        """Benchmark relative volume on 250-row Series."""
        from options_arena.indicators.volume import relative_volume

        benchmark(relative_volume, sample_volume_series)

    @pytest.mark.benchmark(group="indicators")
    def test_ad_trend(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
        sample_volume_series: pd.Series,
    ) -> None:
        """Benchmark A/D trend on 250-row Series."""
        from options_arena.indicators.volume import ad_trend

        benchmark(
            ad_trend,
            sample_high_series,
            sample_low_series,
            sample_close_series,
            sample_volume_series,
        )


# ===========================================================================
# Indicator Benchmarks — Moving Averages (2 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestMovingAverageBenchmarks:
    """Moving average indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_sma_alignment(
        self, benchmark: BenchmarkFixture, sample_close_series: pd.Series
    ) -> None:
        """Benchmark SMA alignment on 250-row Series."""
        from options_arena.indicators.moving_averages import sma_alignment

        benchmark(sma_alignment, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_vwap_deviation(
        self,
        benchmark: BenchmarkFixture,
        sample_close_series: pd.Series,
        sample_volume_series: pd.Series,
    ) -> None:
        """Benchmark VWAP deviation on 250-row Series."""
        from options_arena.indicators.moving_averages import vwap_deviation

        benchmark(vwap_deviation, sample_close_series, sample_volume_series)


# ===========================================================================
# Indicator Benchmarks — Options Specific (9 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestOptionsSpecificBenchmarks:
    """Options-specific indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_iv_rank(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark IV rank scalar computation."""
        from options_arena.indicators.options_specific import iv_rank

        benchmark(iv_rank, 0.30, 0.50, 0.15)

    @pytest.mark.benchmark(group="indicators")
    def test_iv_percentile(
        self, benchmark: BenchmarkFixture, sample_iv_history: pd.Series
    ) -> None:
        """Benchmark IV percentile on 250-point history."""
        from options_arena.indicators.options_specific import iv_percentile

        benchmark(iv_percentile, sample_iv_history, 0.30)

    @pytest.mark.benchmark(group="indicators")
    def test_put_call_ratio_volume(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark put/call ratio by volume."""
        from options_arena.indicators.options_specific import put_call_ratio_volume

        benchmark(put_call_ratio_volume, 15000, 20000)

    @pytest.mark.benchmark(group="indicators")
    def test_put_call_ratio_oi(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark put/call ratio by open interest."""
        from options_arena.indicators.options_specific import put_call_ratio_oi

        benchmark(put_call_ratio_oi, 50000, 60000)

    @pytest.mark.benchmark(group="indicators")
    def test_max_pain(
        self, benchmark: BenchmarkFixture, sample_option_chain_df: pd.DataFrame
    ) -> None:
        """Benchmark max pain computation on 20-strike chain."""
        from options_arena.indicators.options_specific import max_pain

        df = sample_option_chain_df
        benchmark(max_pain, df["strike"], df["openInterest"], df["openInterest"])

    @pytest.mark.benchmark(group="indicators")
    def test_compute_pop(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark Probability of Profit."""
        from options_arena.indicators.options_specific import compute_pop

        benchmark(compute_pop, 0.35, OptionType.CALL)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_optimal_dte(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark optimal DTE score."""
        from options_arena.indicators.options_specific import compute_optimal_dte

        benchmark(compute_optimal_dte, -0.05, 2.50)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_spread_quality(
        self, benchmark: BenchmarkFixture, sample_option_chain_df: pd.DataFrame
    ) -> None:
        """Benchmark spread quality on 20-strike chain."""
        from options_arena.indicators.options_specific import compute_spread_quality

        benchmark(compute_spread_quality, sample_option_chain_df)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_max_loss_ratio(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark max loss ratio."""
        from options_arena.indicators.options_specific import compute_max_loss_ratio

        benchmark(compute_max_loss_ratio, 250.0, 5000.0)


# ===========================================================================
# Indicator Benchmarks — IV Analytics (13 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestIVAnalyticsBenchmarks:
    """IV analytics indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_compute_iv_hv_spread(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark IV-HV spread."""
        from options_arena.indicators.iv_analytics import compute_iv_hv_spread

        benchmark(compute_iv_hv_spread, 0.30, 0.22)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_hv_20d(
        self, benchmark: BenchmarkFixture, sample_close_series: pd.Series
    ) -> None:
        """Benchmark 20-day historical volatility."""
        from options_arena.indicators.iv_analytics import compute_hv_20d

        benchmark(compute_hv_20d, sample_close_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_iv_term_slope(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark IV term structure slope."""
        from options_arena.indicators.iv_analytics import compute_iv_term_slope

        benchmark(compute_iv_term_slope, 0.32, 0.28)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_iv_term_shape(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark IV term structure shape classification."""
        from options_arena.indicators.iv_analytics import compute_iv_term_shape

        benchmark(compute_iv_term_shape, 0.05)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_put_skew(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark put skew index."""
        from options_arena.indicators.iv_analytics import compute_put_skew

        benchmark(compute_put_skew, 0.35, 0.28)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_call_skew(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark call skew index."""
        from options_arena.indicators.iv_analytics import compute_call_skew

        benchmark(compute_call_skew, 0.22, 0.28)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_skew_ratio(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark skew ratio."""
        from options_arena.indicators.iv_analytics import compute_skew_ratio

        benchmark(compute_skew_ratio, 0.35, 0.22)

    @pytest.mark.benchmark(group="indicators")
    def test_classify_vol_regime(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark volatility regime classification."""
        from options_arena.indicators.iv_analytics import classify_vol_regime

        benchmark(classify_vol_regime, 45.0)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_ewma_vol_forecast(
        self, benchmark: BenchmarkFixture, sample_returns_series: pd.Series
    ) -> None:
        """Benchmark EWMA volatility forecast."""
        from options_arena.indicators.iv_analytics import compute_ewma_vol_forecast

        benchmark(compute_ewma_vol_forecast, sample_returns_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_vol_cone_pctl(
        self, benchmark: BenchmarkFixture, sample_iv_history: pd.Series
    ) -> None:
        """Benchmark volatility cone percentile."""
        from options_arena.indicators.iv_analytics import compute_vol_cone_pctl

        benchmark(compute_vol_cone_pctl, 0.25, sample_iv_history)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_vix_correlation(
        self, benchmark: BenchmarkFixture, sample_returns_series: pd.Series
    ) -> None:
        """Benchmark VIX correlation."""
        from options_arena.indicators.iv_analytics import compute_vix_correlation

        # Use shifted returns as proxy for VIX changes
        vix_changes = sample_returns_series * -1.2 + np.random.default_rng(42).normal(
            0, 0.01, len(sample_returns_series)
        )
        vix_series = pd.Series(vix_changes, index=sample_returns_series.index)
        benchmark(compute_vix_correlation, sample_returns_series, vix_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_expected_move(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark expected move."""
        from options_arena.indicators.iv_analytics import compute_expected_move

        benchmark(compute_expected_move, 100.0, 0.30, 30)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_expected_move_ratio(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark expected move ratio."""
        from options_arena.indicators.iv_analytics import compute_expected_move_ratio

        benchmark(compute_expected_move_ratio, 8.5, 7.2)


# ===========================================================================
# Indicator Benchmarks — HV Estimators (3 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestHVEstimatorBenchmarks:
    """Historical volatility estimator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_compute_hv_parkinson(
        self,
        benchmark: BenchmarkFixture,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
    ) -> None:
        """Benchmark Parkinson HV estimator."""
        from options_arena.indicators.hv_estimators import compute_hv_parkinson

        benchmark(compute_hv_parkinson, sample_high_series, sample_low_series)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_hv_rogers_satchell(
        self,
        benchmark: BenchmarkFixture,
        sample_open_series: pd.Series,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark Rogers-Satchell HV estimator."""
        from options_arena.indicators.hv_estimators import compute_hv_rogers_satchell

        benchmark(
            compute_hv_rogers_satchell,
            sample_open_series,
            sample_high_series,
            sample_low_series,
            sample_close_series,
        )

    @pytest.mark.benchmark(group="indicators")
    def test_compute_hv_yang_zhang(
        self,
        benchmark: BenchmarkFixture,
        sample_open_series: pd.Series,
        sample_high_series: pd.Series,
        sample_low_series: pd.Series,
        sample_close_series: pd.Series,
    ) -> None:
        """Benchmark Yang-Zhang HV estimator."""
        from options_arena.indicators.hv_estimators import compute_hv_yang_zhang

        benchmark(
            compute_hv_yang_zhang,
            sample_open_series,
            sample_high_series,
            sample_low_series,
            sample_close_series,
        )


# ===========================================================================
# Indicator Benchmarks — Flow Analytics (5 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestFlowAnalyticsBenchmarks:
    """Flow analytics indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_compute_gex(
        self, benchmark: BenchmarkFixture, sample_option_chain_df: pd.DataFrame
    ) -> None:
        """Benchmark Gamma Exposure computation."""
        from options_arena.indicators.flow_analytics import compute_gex

        chain = sample_option_chain_df.copy()
        chain["strike"] = chain["strike"]
        benchmark(compute_gex, chain, chain, 100.0)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_oi_concentration(
        self, benchmark: BenchmarkFixture, sample_option_chain_df: pd.DataFrame
    ) -> None:
        """Benchmark OI concentration."""
        from options_arena.indicators.flow_analytics import compute_oi_concentration

        benchmark(compute_oi_concentration, sample_option_chain_df)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_unusual_activity(
        self, benchmark: BenchmarkFixture, sample_option_chain_df: pd.DataFrame
    ) -> None:
        """Benchmark unusual activity detection."""
        from options_arena.indicators.flow_analytics import compute_unusual_activity

        benchmark(compute_unusual_activity, sample_option_chain_df)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_max_pain_magnet(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark max pain magnet strength."""
        from options_arena.indicators.flow_analytics import compute_max_pain_magnet

        benchmark(compute_max_pain_magnet, 100.0, 98.5)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_dollar_volume_trend(
        self,
        benchmark: BenchmarkFixture,
        sample_close_series: pd.Series,
        sample_volume_series: pd.Series,
    ) -> None:
        """Benchmark dollar volume trend."""
        from options_arena.indicators.flow_analytics import compute_dollar_volume_trend

        benchmark(compute_dollar_volume_trend, sample_close_series, sample_volume_series)


# ===========================================================================
# Indicator Benchmarks — Regime (7 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestRegimeBenchmarks:
    """Regime and macro indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_classify_market_regime(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark market regime classification."""
        from options_arena.indicators.regime import classify_market_regime

        benchmark(classify_market_regime, 22.0, 20.0, 0.04, 0.5)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_vix_term_structure(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark VIX term structure."""
        from options_arena.indicators.regime import compute_vix_term_structure

        benchmark(compute_vix_term_structure, 20.0, 22.0)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_risk_on_off(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark risk-on/off score."""
        from options_arena.indicators.regime import compute_risk_on_off

        benchmark(compute_risk_on_off, 0.02, 0.005)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_sector_momentum(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark sector momentum."""
        from options_arena.indicators.regime import compute_sector_momentum

        benchmark(compute_sector_momentum, 0.06, 0.03)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_rs_vs_spx(
        self, benchmark: BenchmarkFixture, sample_returns_series: pd.Series
    ) -> None:
        """Benchmark relative strength vs SPX."""
        from options_arena.indicators.regime import compute_rs_vs_spx

        rng = np.random.default_rng(88)
        spx_returns = pd.Series(
            rng.normal(0.0003, 0.01, len(sample_returns_series)),
            index=sample_returns_series.index,
        )
        benchmark(compute_rs_vs_spx, sample_returns_series, spx_returns)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_correlation_regime_shift(
        self, benchmark: BenchmarkFixture, sample_returns_series: pd.Series
    ) -> None:
        """Benchmark correlation regime shift."""
        from options_arena.indicators.regime import compute_correlation_regime_shift

        rng = np.random.default_rng(88)
        spx_returns = pd.Series(
            rng.normal(0.0003, 0.01, len(sample_returns_series)),
            index=sample_returns_series.index,
        )
        benchmark(compute_correlation_regime_shift, sample_returns_series, spx_returns)

    @pytest.mark.benchmark(group="indicators")
    def test_compute_volume_profile_skew(
        self,
        benchmark: BenchmarkFixture,
        sample_close_series: pd.Series,
        sample_volume_series: pd.Series,
    ) -> None:
        """Benchmark volume profile skew."""
        from options_arena.indicators.regime import compute_volume_profile_skew

        benchmark(compute_volume_profile_skew, sample_close_series, sample_volume_series)


# ===========================================================================
# Indicator Benchmarks — Vol Surface (2 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestVolSurfaceBenchmarks:
    """Volatility surface indicator benchmarks."""

    @pytest.mark.benchmark(group="indicators")
    def test_compute_vol_surface(
        self, benchmark: BenchmarkFixture, vol_surface_arrays: dict[str, np.ndarray | float]
    ) -> None:
        """Benchmark vol surface computation (30 contracts)."""
        from options_arena.indicators.vol_surface import compute_vol_surface

        d = vol_surface_arrays
        benchmark(
            compute_vol_surface,
            d["strikes"],
            d["ivs"],
            d["dtes"],
            d["option_types"],
            d["spot"],
        )

    @pytest.mark.benchmark(group="indicators")
    def test_compute_surface_indicators(
        self, benchmark: BenchmarkFixture, vol_surface_arrays: dict[str, np.ndarray | float]
    ) -> None:
        """Benchmark surface indicators extraction."""
        from options_arena.indicators.vol_surface import (
            compute_surface_indicators,
            compute_vol_surface,
        )

        d = vol_surface_arrays
        strikes = d["strikes"]
        dtes = d["dtes"]
        assert isinstance(strikes, np.ndarray)
        assert isinstance(dtes, np.ndarray)
        surface_result = compute_vol_surface(
            strikes,
            d["ivs"],
            dtes,
            d["option_types"],
            d["spot"],
        )
        # Pick a representative contract strike/DTE from the arrays
        contract_strike = float(strikes[len(strikes) // 2])
        contract_dte = float(dtes[len(dtes) // 2])
        benchmark(
            compute_surface_indicators,
            surface_result,
            contract_strike,
            contract_dte,
            strikes,
            dtes,
        )


# ===========================================================================
# Scoring Benchmarks — Normalization (5 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestNormalizationBenchmarks:
    """Normalization scoring benchmarks."""

    @pytest.mark.benchmark(group="scoring")
    def test_percentile_rank_normalize(
        self, benchmark: BenchmarkFixture, scoring_universe: dict[str, IndicatorSignals]
    ) -> None:
        """Benchmark percentile rank normalization on 50-ticker universe."""
        from options_arena.scoring.normalization import percentile_rank_normalize

        benchmark(percentile_rank_normalize, scoring_universe)

    @pytest.mark.benchmark(group="scoring")
    def test_invert_indicators(
        self, benchmark: BenchmarkFixture, scoring_universe: dict[str, IndicatorSignals]
    ) -> None:
        """Benchmark indicator inversion on 50-ticker universe."""
        from options_arena.scoring.normalization import (
            invert_indicators,
            percentile_rank_normalize,
        )

        normalized = percentile_rank_normalize(scoring_universe)
        benchmark(invert_indicators, normalized)

    @pytest.mark.benchmark(group="scoring")
    def test_normalize_single_ticker(
        self, benchmark: BenchmarkFixture, single_ticker_signals: IndicatorSignals
    ) -> None:
        """Benchmark single-ticker domain-bound normalization."""
        from options_arena.scoring.normalization import normalize_single_ticker

        benchmark(normalize_single_ticker, single_ticker_signals)

    @pytest.mark.benchmark(group="scoring")
    def test_get_active_indicators(
        self, benchmark: BenchmarkFixture, scoring_universe: dict[str, IndicatorSignals]
    ) -> None:
        """Benchmark active indicator detection on 50-ticker universe."""
        from options_arena.scoring.normalization import get_active_indicators

        benchmark(get_active_indicators, scoring_universe)

    @pytest.mark.benchmark(group="scoring")
    def test_compute_normalization_stats(
        self, benchmark: BenchmarkFixture, scoring_universe: dict[str, IndicatorSignals]
    ) -> None:
        """Benchmark normalization statistics computation on 50-ticker universe."""
        from options_arena.scoring.normalization import compute_normalization_stats

        benchmark(compute_normalization_stats, scoring_universe)


# ===========================================================================
# Scoring Benchmarks — Composite (2 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestCompositeBenchmarks:
    """Composite scoring benchmarks."""

    @pytest.mark.benchmark(group="scoring")
    def test_composite_score(
        self, benchmark: BenchmarkFixture, single_ticker_signals: IndicatorSignals
    ) -> None:
        """Benchmark single-ticker composite score."""
        from options_arena.scoring.composite import composite_score

        benchmark(composite_score, single_ticker_signals)

    @pytest.mark.benchmark(group="scoring")
    def test_score_universe(
        self, benchmark: BenchmarkFixture, scoring_universe: dict[str, IndicatorSignals]
    ) -> None:
        """Benchmark full universe scoring pipeline (50 tickers)."""
        from options_arena.scoring.composite import score_universe

        benchmark(score_universe, scoring_universe)


# ===========================================================================
# Scoring Benchmarks — Direction (1 function)
# ===========================================================================


@pytest.mark.audit_performance
class TestDirectionBenchmarks:
    """Direction classification benchmarks."""

    @pytest.mark.benchmark(group="scoring")
    def test_determine_direction(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark direction classification."""
        from options_arena.scoring.direction import determine_direction

        benchmark(determine_direction, 28.0, 65.0, 0.3, supertrend=1.0, roc=6.0)


# ===========================================================================
# Scoring Benchmarks — Dimensional (3 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestDimensionalBenchmarks:
    """Dimensional scoring benchmarks."""

    @pytest.mark.benchmark(group="scoring")
    def test_compute_dimensional_scores(
        self, benchmark: BenchmarkFixture, single_ticker_signals: IndicatorSignals
    ) -> None:
        """Benchmark dimensional scores computation."""
        from options_arena.scoring.dimensional import compute_dimensional_scores

        benchmark(compute_dimensional_scores, single_ticker_signals)

    @pytest.mark.benchmark(group="scoring")
    def test_apply_regime_weights(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark regime weight application."""
        from options_arena.models.scoring import DimensionalScores
        from options_arena.scoring.dimensional import apply_regime_weights

        scores = DimensionalScores(
            trend=65.0,
            iv_vol=55.0,
            hv_vol=40.0,
            flow=50.0,
            microstructure=45.0,
            fundamental=60.0,
            regime=55.0,
            risk=70.0,
        )
        benchmark(apply_regime_weights, scores, MarketRegime.TRENDING, True)

    @pytest.mark.benchmark(group="scoring")
    def test_compute_direction_signal(
        self, benchmark: BenchmarkFixture, single_ticker_signals: IndicatorSignals
    ) -> None:
        """Benchmark continuous direction signal computation."""
        from options_arena.scoring.dimensional import compute_direction_signal

        benchmark(compute_direction_signal, single_ticker_signals, SignalDirection.BULLISH)


# ===========================================================================
# Scoring Benchmarks — Contracts (5 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestContractBenchmarks:
    """Contract selection benchmarks."""

    @pytest.mark.benchmark(group="scoring")
    def test_filter_contracts(
        self, benchmark: BenchmarkFixture, sample_contracts: list[OptionContract]
    ) -> None:
        """Benchmark contract filtering."""
        from options_arena.scoring.contracts import filter_contracts

        benchmark(filter_contracts, sample_contracts, SignalDirection.BULLISH)

    @pytest.mark.benchmark(group="scoring")
    def test_select_expiration(
        self, benchmark: BenchmarkFixture, sample_contracts: list[OptionContract]
    ) -> None:
        """Benchmark expiration selection."""
        from options_arena.scoring.contracts import select_expiration

        benchmark(select_expiration, sample_contracts)

    @pytest.mark.benchmark(group="scoring")
    def test_compute_greeks(
        self, benchmark: BenchmarkFixture, sample_contracts_no_greeks: list[OptionContract]
    ) -> None:
        """Benchmark Greeks computation for 5 contracts."""
        from options_arena.scoring.contracts import compute_greeks

        benchmark(compute_greeks, sample_contracts_no_greeks, 100.0, 0.05, 0.02)

    @pytest.mark.benchmark(group="scoring")
    def test_select_by_delta(
        self, benchmark: BenchmarkFixture, sample_contracts: list[OptionContract]
    ) -> None:
        """Benchmark delta-targeted contract selection."""
        from options_arena.scoring.contracts import select_by_delta

        benchmark(select_by_delta, sample_contracts)

    @pytest.mark.benchmark(group="scoring")
    def test_recommend_contracts(
        self, benchmark: BenchmarkFixture, sample_contracts_no_greeks: list[OptionContract]
    ) -> None:
        """Benchmark full recommendation pipeline."""
        from options_arena.scoring.contracts import recommend_contracts

        benchmark(
            recommend_contracts,
            sample_contracts_no_greeks,
            SignalDirection.BULLISH,
            100.0,
            0.05,
            0.02,
        )


# ===========================================================================
# Orchestration Benchmarks (5 functions)
# ===========================================================================


@pytest.mark.audit_performance
class TestOrchestrationBenchmarks:
    """Orchestration math function benchmarks."""

    @pytest.mark.benchmark(group="orchestration")
    def test_compute_agreement_score(
        self, benchmark: BenchmarkFixture, agent_directions: dict[str, SignalDirection]
    ) -> None:
        """Benchmark agreement score computation."""
        from options_arena.agents.orchestrator import compute_agreement_score

        benchmark(compute_agreement_score, agent_directions)

    @pytest.mark.benchmark(group="orchestration")
    def test_vote_entropy(
        self, benchmark: BenchmarkFixture, agent_directions: dict[str, SignalDirection]
    ) -> None:
        """Benchmark vote entropy computation."""
        from options_arena.agents.orchestrator import _vote_entropy

        benchmark(_vote_entropy, agent_directions)

    @pytest.mark.benchmark(group="orchestration")
    def test_log_odds_pool(
        self,
        benchmark: BenchmarkFixture,
        agent_probabilities: list[float],
        agent_weights: list[float],
    ) -> None:
        """Benchmark log-odds pooling (Bordley 1982)."""
        from options_arena.agents.orchestrator import _log_odds_pool

        benchmark(_log_odds_pool, agent_probabilities, agent_weights)

    @pytest.mark.benchmark(group="orchestration")
    def test_compute_citation_density(
        self,
        benchmark: BenchmarkFixture,
        citation_context_block: str,
        citation_agent_text: str,
    ) -> None:
        """Benchmark citation density computation."""
        from options_arena.agents._parsing import compute_citation_density

        benchmark(compute_citation_density, citation_context_block, citation_agent_text)

    @pytest.mark.benchmark(group="orchestration")
    def test_get_majority_direction(
        self, benchmark: BenchmarkFixture, agent_directions: dict[str, SignalDirection]
    ) -> None:
        """Benchmark majority direction determination."""
        from options_arena.agents.orchestrator import _get_majority_direction

        benchmark(_get_majority_direction, agent_directions)
