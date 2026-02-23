"""Tests for bug fixes identified in code analysis of commit 61e247d.

Covers:
1. iv_percentile NaN-in-history handling
2. max_pain NaN-in-OI handling
3. ROC division-by-zero when prev_close=0
4. atr_percent division-by-zero when close=0
5. Multi-Series length validation (validate_aligned)
"""

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.moving_averages import vwap_deviation
from options_arena.indicators.options_specific import iv_percentile, max_pain
from options_arena.indicators.oscillators import williams_r
from options_arena.indicators.trend import adx, roc, supertrend
from options_arena.indicators.volatility import atr_percent, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# iv_percentile NaN handling
# ---------------------------------------------------------------------------


class TestIVPercentileNaN:
    """Tests for iv_percentile NaN-in-history fix."""

    def test_nan_in_history_excluded_from_count(self) -> None:
        """NaN values in history should be excluded from both numerator and denominator.

        history=[10, NaN, 30, 40, 50], current=35
        Valid values: [10, 30, 40, 50] (4 values)
        Days lower: 2 (10, 30)
        Percentile = 2/4 * 100 = 50.0
        """
        history = pd.Series([10.0, np.nan, 30.0, 40.0, 50.0])
        result = iv_percentile(history, current_iv=35.0)
        assert result == pytest.approx(50.0, rel=1e-4)

    def test_multiple_nans_excluded(self) -> None:
        """Multiple NaN values excluded correctly."""
        history = pd.Series([np.nan, 10.0, np.nan, 20.0, np.nan, 30.0])
        result = iv_percentile(history, current_iv=25.0)
        # Valid: [10, 20, 30], lower than 25: [10, 20] => 2/3 * 100 = 66.67
        assert result == pytest.approx(66.6667, rel=1e-3)

    def test_all_nan_raises(self) -> None:
        """All-NaN history should raise InsufficientDataError."""
        history = pd.Series([np.nan, np.nan, np.nan])
        with pytest.raises(InsufficientDataError):
            iv_percentile(history, current_iv=30.0)

    def test_no_nan_unchanged(self) -> None:
        """Without NaN, behavior is unchanged from original."""
        history = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = iv_percentile(history, current_iv=35.0)
        assert result == pytest.approx(60.0, rel=1e-4)


# ---------------------------------------------------------------------------
# max_pain NaN handling
# ---------------------------------------------------------------------------


class TestMaxPainNaN:
    """Tests for max_pain NaN-in-OI fix."""

    def test_nan_call_oi_treated_as_zero(self) -> None:
        """NaN in call_oi should be treated as zero (not corrupt the calculation).

        strikes=[95, 100, 105], call_oi=[NaN, 200, 50], put_oi=[50, 200, 100]

        At candidate 95:  call=0, put=(100-95)*200 + (105-95)*100 = 2000. Total: 2000
        At candidate 100: call=(100-95)*0=0, put=(105-100)*100=500. Total: 500
        At candidate 105: call=(105-95)*0+(105-100)*200=1000, put=0. Total: 1000
        Min at 100.
        """
        strikes = pd.Series([95.0, 100.0, 105.0])
        call_oi = pd.Series([np.nan, 200.0, 50.0])
        put_oi = pd.Series([50.0, 200.0, 100.0])
        result = max_pain(strikes, call_oi, put_oi)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_nan_put_oi_treated_as_zero(self) -> None:
        """NaN in put_oi should be treated as zero."""
        strikes = pd.Series([95.0, 100.0, 105.0])
        call_oi = pd.Series([100.0, 200.0, 50.0])
        put_oi = pd.Series([50.0, np.nan, 100.0])
        result = max_pain(strikes, call_oi, put_oi)
        # Should still find a valid min pain strike
        assert np.isfinite(result)

    def test_all_nan_oi_returns_first_strike(self) -> None:
        """All NaN OI: pain=0 everywhere, returns first strike."""
        strikes = pd.Series([90.0, 95.0, 100.0])
        call_oi = pd.Series([np.nan, np.nan, np.nan])
        put_oi = pd.Series([np.nan, np.nan, np.nan])
        result = max_pain(strikes, call_oi, put_oi)
        assert result == pytest.approx(90.0, rel=1e-4)


# ---------------------------------------------------------------------------
# ROC division-by-zero guard
# ---------------------------------------------------------------------------


class TestROCDivByZero:
    """Tests for ROC division-by-zero when prev_close=0."""

    def test_zero_prev_close_produces_nan(self) -> None:
        """When prev_close is 0, ROC should be NaN (not inf).

        close=[0, 1, 2, 3, 4, 5], period=3
        At index 3: prev=close[0]=0 => NaN
        At index 4: prev=close[1]=1 => (4-1)/1*100 = 300
        """
        close = pd.Series([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        result = roc(close, period=3)
        assert pd.isna(result.iloc[3])  # prev_close was 0
        assert result.iloc[4] == pytest.approx(300.0, rel=1e-4)

    def test_no_inf_in_output(self) -> None:
        """ROC output should never contain inf values."""
        close = pd.Series([0.0, 0.0, 0.0, 1.0, 2.0, 3.0])
        result = roc(close, period=3)
        valid = result.dropna()
        assert all(np.isfinite(v) for v in valid)


# ---------------------------------------------------------------------------
# atr_percent division-by-zero guard
# ---------------------------------------------------------------------------


class TestATRPercentDivByZero:
    """Tests for atr_percent division-by-zero when close=0."""

    def test_zero_close_produces_nan(self) -> None:
        """When close is 0, ATR% should be NaN (not inf)."""
        n = 20
        high = pd.Series([1.0] * n)
        low = pd.Series([0.0] * n)
        close = pd.Series([0.0] * n)  # all zeros
        result = atr_percent(high, low, close, period=14)
        # All valid values should be NaN (close=0 everywhere)
        valid = result.iloc[14:]  # skip warmup
        assert valid.isna().all()

    def test_no_inf_in_output(self) -> None:
        """ATR% output should never contain inf values."""
        high = pd.Series([10.0] * 5 + [10.0] * 15)
        low = pd.Series([0.0] * 5 + [9.0] * 15)
        close = pd.Series([0.0] * 5 + [9.5] * 15)
        result = atr_percent(high, low, close, period=14)
        valid = result.dropna()
        assert all(np.isfinite(v) for v in valid)


# ---------------------------------------------------------------------------
# validate_aligned tests (multi-Series length mismatch)
# ---------------------------------------------------------------------------


class TestValidateAligned:
    """Tests for multi-Series length validation across all indicator functions."""

    def test_williams_r_mismatched_lengths(self) -> None:
        """Williams %R rejects mismatched high/low/close lengths."""
        high = pd.Series([101.0] * 20)
        low = pd.Series([99.0] * 15)  # shorter
        close = pd.Series([100.0] * 20)
        with pytest.raises(ValueError, match="equal length"):
            williams_r(high, low, close, period=14)

    def test_adx_mismatched_lengths(self) -> None:
        """ADX rejects mismatched high/low/close lengths."""
        high = pd.Series([101.0] * 30)
        low = pd.Series([99.0] * 25)  # shorter
        close = pd.Series([100.0] * 30)
        with pytest.raises(ValueError, match="equal length"):
            adx(high, low, close, period=14)

    def test_supertrend_mismatched_lengths(self) -> None:
        """Supertrend rejects mismatched high/low/close lengths."""
        high = pd.Series([101.0] * 20)
        low = pd.Series([99.0] * 20)
        close = pd.Series([100.0] * 15)  # shorter
        with pytest.raises(ValueError, match="equal length"):
            supertrend(high, low, close, period=10)

    def test_atr_percent_mismatched_lengths(self) -> None:
        """ATR% rejects mismatched high/low/close lengths."""
        high = pd.Series([101.0] * 20)
        low = pd.Series([99.0] * 20)
        close = pd.Series([100.0] * 15)  # shorter
        with pytest.raises(ValueError, match="equal length"):
            atr_percent(high, low, close, period=14)

    def test_keltner_width_mismatched_lengths(self) -> None:
        """Keltner width rejects mismatched high/low/close lengths."""
        high = pd.Series([101.0] * 25)
        low = pd.Series([99.0] * 20)  # shorter
        close = pd.Series([100.0] * 25)
        with pytest.raises(ValueError, match="equal length"):
            keltner_width(high, low, close, period=10)

    def test_obv_trend_mismatched_lengths(self) -> None:
        """OBV trend rejects mismatched close/volume lengths."""
        close = pd.Series([100.0] * 25)
        volume = pd.Series([1000.0] * 20)  # shorter
        with pytest.raises(ValueError, match="equal length"):
            obv_trend(close, volume, slope_period=5)

    def test_ad_trend_mismatched_lengths(self) -> None:
        """A/D trend rejects mismatched input lengths."""
        high = pd.Series([110.0] * 25)
        low = pd.Series([100.0] * 25)
        close = pd.Series([105.0] * 25)
        volume = pd.Series([1000.0] * 20)  # shorter
        with pytest.raises(ValueError, match="equal length"):
            ad_trend(high, low, close, volume, slope_period=5)

    def test_vwap_deviation_mismatched_lengths(self) -> None:
        """VWAP deviation rejects mismatched close/volume lengths."""
        close = pd.Series([100.0, 101.0, 102.0])
        volume = pd.Series([1000.0, 1500.0])  # shorter
        with pytest.raises(ValueError, match="equal length"):
            vwap_deviation(close, volume)

    def test_equal_lengths_pass(self) -> None:
        """Equal-length inputs should not raise."""
        n = 30
        close = pd.Series(np.linspace(100, 110, n))
        high = close + 1.0
        low = close - 1.0
        # Should not raise
        result = adx(high, low, close, period=14)
        assert len(result) == n
