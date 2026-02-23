"""Tests for options-specific indicators: iv_rank, iv_percentile,
put_call_ratio_volume, put_call_ratio_oi, max_pain.

Every indicator is tested with all five required test types:
1. Known-value test (with source citation)
2. Minimum data test
3. Insufficient data test
4. NaN warmup test (where applicable)
5. Edge cases (div-by-zero, flat, etc.)
"""

import math

import pandas as pd
import pytest

from options_arena.indicators.options_specific import (
    iv_percentile,
    iv_rank,
    max_pain,
    put_call_ratio_oi,
    put_call_ratio_volume,
)
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# iv_rank tests
# ---------------------------------------------------------------------------


class TestIVRank:
    """Tests for IV Rank calculation."""

    def test_known_value(self) -> None:
        """Known-value test: IV Rank = (current - low) / (high - low) * 100.

        Reference: tastytrade IV Rank definition.
        current=30, high=50, low=10 => (30-10)/(50-10)*100 = 50.0
        """
        result = iv_rank(current_iv=30.0, iv_high=50.0, iv_low=10.0)
        assert result == pytest.approx(50.0, rel=1e-4)

    def test_at_high(self) -> None:
        """IV at high: rank = 100."""
        result = iv_rank(current_iv=50.0, iv_high=50.0, iv_low=10.0)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_at_low(self) -> None:
        """IV at low: rank = 0."""
        result = iv_rank(current_iv=10.0, iv_high=50.0, iv_low=10.0)
        assert result == pytest.approx(0.0, rel=1e-4)

    def test_high_equals_low_guard(self) -> None:
        """When high == low (no range), return 50."""
        result = iv_rank(current_iv=30.0, iv_high=30.0, iv_low=30.0)
        assert result == pytest.approx(50.0, rel=1e-4)

    def test_above_high(self) -> None:
        """IV above historical high: rank > 100 (valid, not clamped)."""
        result = iv_rank(current_iv=60.0, iv_high=50.0, iv_low=10.0)
        assert result == pytest.approx(125.0, rel=1e-4)

    def test_below_low(self) -> None:
        """IV below historical low: rank < 0 (valid, not clamped)."""
        result = iv_rank(current_iv=5.0, iv_high=50.0, iv_low=10.0)
        assert result == pytest.approx(-12.5, rel=1e-4)


# ---------------------------------------------------------------------------
# iv_percentile tests
# ---------------------------------------------------------------------------


class TestIVPercentile:
    """Tests for IV Percentile calculation."""

    def test_known_value(self) -> None:
        """Known-value test: count-based percentile.

        Reference: CBOE IV Percentile methodology.
        History: [10, 20, 30, 40, 50], current=35
        Days lower: 3 (10, 20, 30), total: 5
        Percentile = 3/5 * 100 = 60.0
        """
        history = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = iv_percentile(history, current_iv=35.0)
        assert result == pytest.approx(60.0, rel=1e-4)

    def test_all_lower(self) -> None:
        """All history values lower than current: percentile = 100."""
        history = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = iv_percentile(history, current_iv=60.0)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_none_lower(self) -> None:
        """No history values lower than current: percentile = 0."""
        history = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = iv_percentile(history, current_iv=5.0)
        assert result == pytest.approx(0.0, rel=1e-4)

    def test_minimum_data(self) -> None:
        """Single history value: either 0% or 100%."""
        history = pd.Series([20.0])
        result = iv_percentile(history, current_iv=25.0)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_insufficient_data(self) -> None:
        """Empty history raises InsufficientDataError."""
        history = pd.Series([], dtype=float)
        with pytest.raises(InsufficientDataError):
            iv_percentile(history, current_iv=30.0)

    def test_not_same_as_iv_rank(self) -> None:
        """IV Percentile != IV Rank for typical data.

        Reference: tastytrade distinction between rank and percentile.
        """
        # Skewed distribution: mostly low IV with a few spikes
        history = pd.Series([10.0, 11.0, 12.0, 10.5, 11.5, 50.0])
        current = 30.0

        rank = iv_rank(current, iv_high=50.0, iv_low=10.0)  # (30-10)/(50-10)*100 = 50
        percentile = iv_percentile(history, current)  # 5/6 * 100 = 83.33

        # They should differ
        assert rank != pytest.approx(percentile, abs=5.0)

    def test_equal_values(self) -> None:
        """When current equals some history values, they are NOT counted as lower."""
        history = pd.Series([10.0, 20.0, 30.0, 30.0, 30.0])
        result = iv_percentile(history, current_iv=30.0)
        # Only 10.0 and 20.0 are strictly lower: 2/5 * 100 = 40.0
        assert result == pytest.approx(40.0, rel=1e-4)


# ---------------------------------------------------------------------------
# put_call_ratio_volume tests
# ---------------------------------------------------------------------------


class TestPutCallRatioVolume:
    """Tests for Put/Call ratio by volume."""

    def test_known_value(self) -> None:
        """Known-value: 1000 put vol / 2000 call vol = 0.5.

        Reference: Standard P/C ratio calculation.
        """
        result = put_call_ratio_volume(put_volume=1000, call_volume=2000)
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_equal_volume(self) -> None:
        """Equal volume: ratio = 1.0."""
        result = put_call_ratio_volume(put_volume=1000, call_volume=1000)
        assert result == pytest.approx(1.0, rel=1e-4)

    def test_zero_call_volume_guard(self) -> None:
        """Zero call volume: returns NaN (ratio undefined)."""
        result = put_call_ratio_volume(put_volume=1000, call_volume=0)
        assert math.isnan(result)

    def test_zero_put_volume(self) -> None:
        """Zero put volume: ratio = 0."""
        result = put_call_ratio_volume(put_volume=0, call_volume=1000)
        assert result == pytest.approx(0.0, rel=1e-4)

    def test_bearish_signal(self) -> None:
        """High put volume relative to call: ratio > 1 (bearish sentiment)."""
        result = put_call_ratio_volume(put_volume=5000, call_volume=2000)
        assert result > 1.0


# ---------------------------------------------------------------------------
# put_call_ratio_oi tests
# ---------------------------------------------------------------------------


class TestPutCallRatioOI:
    """Tests for Put/Call ratio by open interest."""

    def test_known_value(self) -> None:
        """Known-value: 3000 put OI / 6000 call OI = 0.5.

        Reference: Standard P/C ratio calculation.
        """
        result = put_call_ratio_oi(put_oi=3000, call_oi=6000)
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_equal_oi(self) -> None:
        """Equal OI: ratio = 1.0."""
        result = put_call_ratio_oi(put_oi=5000, call_oi=5000)
        assert result == pytest.approx(1.0, rel=1e-4)

    def test_zero_call_oi_guard(self) -> None:
        """Zero call OI: returns NaN (ratio undefined)."""
        result = put_call_ratio_oi(put_oi=1000, call_oi=0)
        assert math.isnan(result)

    def test_zero_put_oi(self) -> None:
        """Zero put OI: ratio = 0."""
        result = put_call_ratio_oi(put_oi=0, call_oi=1000)
        assert result == pytest.approx(0.0, rel=1e-4)


# ---------------------------------------------------------------------------
# max_pain tests
# ---------------------------------------------------------------------------


class TestMaxPain:
    """Tests for Max Pain calculation."""

    def test_known_value(self) -> None:
        """Known-value test: max pain at strike with minimum total ITM value.

        Reference: Options max pain theory.
        Strikes: 95, 100, 105
        Call OI: 100, 200, 50
        Put OI: 50, 200, 100

        At candidate 95:
          Call ITM pain: none (no strikes < 95)
          Put ITM pain: (100-95)*200 + (105-95)*100 = 1000 + 1000 = 2000
          Total: 2000

        At candidate 100:
          Call ITM pain: (100-95)*100 = 500
          Put ITM pain: (105-100)*100 = 500
          Total: 1000

        At candidate 105:
          Call ITM pain: (105-95)*100 + (105-100)*200 = 1000 + 1000 = 2000
          Put ITM pain: none
          Total: 2000

        Min pain at strike 100.
        """
        strikes = pd.Series([95.0, 100.0, 105.0])
        call_oi = pd.Series([100.0, 200.0, 50.0])
        put_oi = pd.Series([50.0, 200.0, 100.0])
        result = max_pain(strikes, call_oi, put_oi)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_single_strike(self) -> None:
        """Single strike: max pain is that strike."""
        strikes = pd.Series([100.0])
        call_oi = pd.Series([500.0])
        put_oi = pd.Series([300.0])
        result = max_pain(strikes, call_oi, put_oi)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_insufficient_data(self) -> None:
        """Empty strikes raises InsufficientDataError."""
        strikes = pd.Series([], dtype=float)
        call_oi = pd.Series([], dtype=float)
        put_oi = pd.Series([], dtype=float)
        with pytest.raises(InsufficientDataError):
            max_pain(strikes, call_oi, put_oi)

    def test_mismatched_lengths_raises(self) -> None:
        """Mismatched input lengths should raise ValueError."""
        strikes = pd.Series([90.0, 95.0, 100.0])
        call_oi = pd.Series([100.0, 200.0])  # wrong length
        put_oi = pd.Series([50.0, 200.0, 100.0])
        with pytest.raises(ValueError, match="equal length"):
            max_pain(strikes, call_oi, put_oi)

    def test_all_oi_at_one_strike(self) -> None:
        """All OI concentrated at one strike: max pain gravitates there."""
        strikes = pd.Series([90.0, 95.0, 100.0, 105.0, 110.0])
        call_oi = pd.Series([0.0, 0.0, 10000.0, 0.0, 0.0])
        put_oi = pd.Series([0.0, 0.0, 10000.0, 0.0, 0.0])
        result = max_pain(strikes, call_oi, put_oi)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_heavy_call_oi_pulls_pain_up(self) -> None:
        """Heavy call OI at low strikes pulls max pain upward.

        When calls have heavy OI at low strikes, moving the candidate
        price higher makes those calls ITM (more pain for call holders),
        so max pain shifts toward higher strikes where those calls are
        NOT yet ITM. But put OI at high strikes counterbalances.

        Setup: Heavy call OI at strikes 90 and 95, heavy put OI at 105 and 110.
        Max pain should be near the middle (100) where total pain is minimized.
        """
        strikes = pd.Series([90.0, 95.0, 100.0, 105.0, 110.0])
        call_oi = pd.Series([5000.0, 5000.0, 0.0, 0.0, 0.0])
        put_oi = pd.Series([0.0, 0.0, 0.0, 5000.0, 5000.0])
        result = max_pain(strikes, call_oi, put_oi)

        # candidate 90: call=0, put=175000 => 175000
        # candidate 95: call=25000, put=125000 => 150000
        # candidate 100: call=75000, put=75000 => 150000
        # candidate 105: call=125000, put=25000 => 150000
        # candidate 110: call=175000, put=0 => 175000
        # Min pain at 95/100/105 (all 150000). First wins: 95.
        assert result == pytest.approx(95.0, rel=1e-4)

    def test_zero_oi(self) -> None:
        """All zero OI: any strike is valid (pain=0 everywhere). Returns first."""
        strikes = pd.Series([90.0, 95.0, 100.0])
        call_oi = pd.Series([0.0, 0.0, 0.0])
        put_oi = pd.Series([0.0, 0.0, 0.0])
        result = max_pain(strikes, call_oi, put_oi)
        # All have pain=0, first strike wins
        assert result == pytest.approx(90.0, rel=1e-4)
