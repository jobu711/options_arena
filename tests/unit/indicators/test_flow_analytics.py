"""Tests for flow analytics indicators: compute_gex, compute_oi_concentration,
compute_unusual_activity, compute_max_pain_magnet, compute_dollar_volume_trend.

Every indicator is tested with:
1. Known-value test (with calculation in docstring)
2. Minimum data test
3. Insufficient/empty data test (returns None)
4. Edge cases (zero values, division guards)
"""

import pandas as pd
import pytest

from options_arena.indicators.flow_analytics import (
    compute_dollar_volume_trend,
    compute_gex,
    compute_max_pain_magnet,
    compute_oi_concentration,
    compute_unusual_activity,
)

# ---------------------------------------------------------------------------
# compute_gex tests
# ---------------------------------------------------------------------------


class TestComputeGEX:
    """Tests for Net Gamma Exposure (GEX) calculation."""

    def test_known_value(self) -> None:
        """Known-value: GEX = call_gex - put_gex.

        calls: OI=100, gamma=0.05, spot=100
        puts: OI=80, gamma=0.04, spot=100
        call_gex = 100 * 0.05 * 100 * 100 = 50000
        put_gex = 80 * 0.04 * 100 * 100 = 32000
        GEX = 50000 - 32000 = 18000
        """
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        result = compute_gex(calls, puts, spot=100.0)
        assert result is not None
        assert result == pytest.approx(18000.0, rel=1e-4)

    def test_multiple_strikes(self) -> None:
        """GEX with multiple strikes sums across all ATM-range contracts."""
        calls = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "openInterest": [50, 100, 30],
                "gamma": [0.03, 0.05, 0.02],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "openInterest": [40, 80, 60],
                "gamma": [0.02, 0.04, 0.03],
            }
        )
        spot = 100.0
        # call_gex = (50*0.03 + 100*0.05 + 30*0.02) * 100 * 100
        #          = (1.5 + 5.0 + 0.6) * 10000 = 71000
        # put_gex = (40*0.02 + 80*0.04 + 60*0.03) * 100 * 100
        #         = (0.8 + 3.2 + 1.8) * 10000 = 58000
        result = compute_gex(calls, puts, spot)
        assert result is not None
        assert result == pytest.approx(71000.0 - 58000.0, rel=1e-4)

    def test_negative_gex(self) -> None:
        """Put-dominated flow produces negative GEX."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [10], "gamma": [0.01]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [500], "gamma": [0.05]})
        result = compute_gex(calls, puts, spot=100.0)
        assert result is not None
        assert result < 0

    def test_empty_calls_returns_none(self) -> None:
        """Empty call chain returns None."""
        calls = pd.DataFrame(columns=["strike", "openInterest", "gamma"])
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        result = compute_gex(calls, puts, spot=100.0)
        assert result is None

    def test_empty_puts_returns_none(self) -> None:
        """Empty put chain returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame(columns=["strike", "openInterest", "gamma"])
        result = compute_gex(calls, puts, spot=100.0)
        assert result is None

    def test_missing_columns_returns_none(self) -> None:
        """Missing required columns returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80]})
        result = compute_gex(calls, puts, spot=100.0)
        assert result is None

    def test_nan_spot_returns_none(self) -> None:
        """NaN spot returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        assert compute_gex(calls, puts, spot=float("nan")) is None

    def test_inf_spot_returns_none(self) -> None:
        """Inf spot returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        assert compute_gex(calls, puts, spot=float("inf")) is None

    def test_zero_spot_returns_none(self) -> None:
        """Zero spot returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        assert compute_gex(calls, puts, spot=0.0) is None

    def test_negative_spot_returns_none(self) -> None:
        """Negative spot returns None."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        assert compute_gex(calls, puts, spot=-100.0) is None

    def test_result_finiteness(self) -> None:
        """Result is always finite when returned (not None)."""
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"strike": [100.0], "openInterest": [80], "gamma": [0.04]})
        import math

        result = compute_gex(calls, puts, spot=100.0)
        assert result is not None
        assert math.isfinite(result)

    def test_filters_to_atm_range(self) -> None:
        """Strikes far from spot (>10%) are excluded from GEX calculation."""
        calls = pd.DataFrame(
            {
                "strike": [50.0, 100.0, 200.0],
                "openInterest": [1000, 100, 1000],
                "gamma": [0.05, 0.05, 0.05],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [50.0, 100.0, 200.0],
                "openInterest": [0, 0, 0],
                "gamma": [0.0, 0.0, 0.0],
            }
        )
        spot = 100.0
        result = compute_gex(calls, puts, spot)
        assert result is not None
        # Only the 100 strike should be included (90-110 range)
        # call_gex = 100 * 0.05 * 100 * 100 = 50000
        assert result == pytest.approx(50000.0, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_oi_concentration tests
# ---------------------------------------------------------------------------


class TestComputeOIConcentration:
    """Tests for OI concentration ratio."""

    def test_known_value(self) -> None:
        """Known-value: max_OI/total_OI = 500/1000 = 0.5.

        Reference: standard concentration ratio.
        """
        chain = pd.DataFrame({"openInterest": [200, 300, 500]})
        result = compute_oi_concentration(chain)
        assert result is not None
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_all_at_one_strike(self) -> None:
        """All OI at one strike: concentration = 1.0."""
        chain = pd.DataFrame({"openInterest": [0, 0, 1000]})
        result = compute_oi_concentration(chain)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-4)

    def test_evenly_distributed(self) -> None:
        """Evenly distributed OI: concentration = 1/N."""
        chain = pd.DataFrame({"openInterest": [100, 100, 100, 100]})
        result = compute_oi_concentration(chain)
        assert result is not None
        assert result == pytest.approx(0.25, rel=1e-4)

    def test_zero_total_oi_returns_none(self) -> None:
        """All zero OI returns None (no positioning)."""
        chain = pd.DataFrame({"openInterest": [0, 0, 0]})
        result = compute_oi_concentration(chain)
        assert result is None

    def test_empty_chain_returns_none(self) -> None:
        """Empty DataFrame returns None."""
        chain = pd.DataFrame(columns=["openInterest"])
        result = compute_oi_concentration(chain)
        assert result is None

    def test_missing_column_returns_none(self) -> None:
        """Missing openInterest column returns None."""
        chain = pd.DataFrame({"volume": [100, 200]})
        result = compute_oi_concentration(chain)
        assert result is None


# ---------------------------------------------------------------------------
# compute_unusual_activity tests
# ---------------------------------------------------------------------------


class TestComputeUnusualActivity:
    """Tests for unusual activity score."""

    def test_known_value(self) -> None:
        """Known-value: one unusual strike, premium-weighted score.

        Strike 1: vol=100, OI=200 (not unusual)
        Strike 2: vol=500, OI=100 (unusual: 500 > 2*100=200)
          mid = (2.0 + 3.0) / 2 = 2.5
          ratio = 500/100 = 5.0

        Weighted score = (5.0 * 2.5) / 2.5 = 5.0
        """
        chain = pd.DataFrame(
            {
                "volume": [100, 500],
                "openInterest": [200, 100],
                "bid": [1.0, 2.0],
                "ask": [1.5, 3.0],
            }
        )
        result = compute_unusual_activity(chain)
        assert result is not None
        assert result == pytest.approx(5.0, rel=1e-4)

    def test_no_unusual_activity(self) -> None:
        """No strikes with vol > 2*OI: score = 0.0."""
        chain = pd.DataFrame(
            {
                "volume": [50, 100],
                "openInterest": [200, 300],
                "bid": [1.0, 2.0],
                "ask": [1.5, 3.0],
            }
        )
        result = compute_unusual_activity(chain)
        assert result is not None
        assert result == pytest.approx(0.0, rel=1e-4)

    def test_multiple_unusual_strikes(self) -> None:
        """Multiple unusual strikes produce premium-weighted average."""
        chain = pd.DataFrame(
            {
                "volume": [600, 400],
                "openInterest": [100, 100],
                "bid": [1.0, 3.0],
                "ask": [1.0, 3.0],
            }
        )
        result = compute_unusual_activity(chain)
        assert result is not None
        # Strike 1: ratio=6.0, mid=1.0
        # Strike 2: ratio=4.0, mid=3.0
        # weighted = (6*1 + 4*3) / (1+3) = (6+12)/4 = 4.5
        assert result == pytest.approx(4.5, rel=1e-4)

    def test_empty_chain_returns_none(self) -> None:
        """Empty DataFrame returns None."""
        chain = pd.DataFrame(columns=["volume", "openInterest", "bid", "ask"])
        result = compute_unusual_activity(chain)
        assert result is None

    def test_missing_columns_returns_none(self) -> None:
        """Missing required columns returns None."""
        chain = pd.DataFrame({"volume": [100], "openInterest": [200]})
        result = compute_unusual_activity(chain)
        assert result is None

    def test_zero_oi_excluded(self) -> None:
        """Strikes with zero OI are excluded from unusual detection."""
        chain = pd.DataFrame(
            {
                "volume": [500, 100],
                "openInterest": [0, 200],
                "bid": [1.0, 2.0],
                "ask": [1.5, 3.0],
            }
        )
        result = compute_unusual_activity(chain)
        assert result is not None
        # vol=500 > 2*0=0 is True but OI=0 so excluded
        assert result == pytest.approx(0.0, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_max_pain_magnet tests
# ---------------------------------------------------------------------------


class TestComputeMaxPainMagnet:
    """Tests for max pain magnet strength."""

    def test_at_max_pain(self) -> None:
        """Spot exactly at max pain: magnet = 1.0."""
        result = compute_max_pain_magnet(spot=100.0, max_pain=100.0)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-4)

    def test_known_distance(self) -> None:
        """Known distance: spot=100, max_pain=95.

        magnet = 1 - (|100-95|/100) = 1 - 0.05 = 0.95
        """
        result = compute_max_pain_magnet(spot=100.0, max_pain=95.0)
        assert result is not None
        assert result == pytest.approx(0.95, rel=1e-4)

    def test_above_max_pain(self) -> None:
        """Spot above max pain."""
        result = compute_max_pain_magnet(spot=110.0, max_pain=100.0)
        assert result is not None
        expected = 1.0 - (10.0 / 110.0)
        assert result == pytest.approx(expected, rel=1e-4)

    def test_far_from_max_pain(self) -> None:
        """Spot very far from max pain produces low or negative magnet."""
        result = compute_max_pain_magnet(spot=50.0, max_pain=200.0)
        assert result is not None
        # 1 - (150/50) = 1 - 3.0 = -2.0
        assert result < 0

    def test_none_max_pain_returns_none(self) -> None:
        """None max_pain returns None."""
        result = compute_max_pain_magnet(spot=100.0, max_pain=None)
        assert result is None

    def test_zero_spot_returns_none(self) -> None:
        """Zero spot returns None (div-by-zero guard)."""
        result = compute_max_pain_magnet(spot=0.0, max_pain=100.0)
        assert result is None

    def test_nan_spot_returns_none(self) -> None:
        """NaN spot returns None."""
        assert compute_max_pain_magnet(spot=float("nan"), max_pain=100.0) is None

    def test_inf_spot_returns_none(self) -> None:
        """Inf spot returns None."""
        assert compute_max_pain_magnet(spot=float("inf"), max_pain=100.0) is None

    def test_negative_spot_returns_none(self) -> None:
        """Negative spot returns None."""
        assert compute_max_pain_magnet(spot=-100.0, max_pain=100.0) is None

    def test_nan_max_pain_returns_none(self) -> None:
        """NaN max_pain returns None."""
        assert compute_max_pain_magnet(spot=100.0, max_pain=float("nan")) is None

    def test_inf_max_pain_returns_none(self) -> None:
        """Inf max_pain returns None."""
        assert compute_max_pain_magnet(spot=100.0, max_pain=float("inf")) is None


# ---------------------------------------------------------------------------
# compute_dollar_volume_trend tests
# ---------------------------------------------------------------------------


class TestComputeDollarVolumeTrend:
    """Tests for dollar volume trend (slope)."""

    def test_increasing_trend(self) -> None:
        """Monotonically increasing dollar volume has positive slope."""
        close = pd.Series([10.0] * 20)
        volume = pd.Series(range(1, 21), dtype=float)  # 1,2,...,20
        result = compute_dollar_volume_trend(close, volume, period=20)
        assert result is not None
        assert result > 0

    def test_decreasing_trend(self) -> None:
        """Monotonically decreasing dollar volume has negative slope."""
        close = pd.Series([10.0] * 20)
        volume = pd.Series(range(20, 0, -1), dtype=float)  # 20,19,...,1
        result = compute_dollar_volume_trend(close, volume, period=20)
        assert result is not None
        assert result < 0

    def test_flat_trend(self) -> None:
        """Constant dollar volume has zero slope."""
        close = pd.Series([10.0] * 20)
        volume = pd.Series([100.0] * 20)
        result = compute_dollar_volume_trend(close, volume, period=20)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_insufficient_data_returns_none(self) -> None:
        """Fewer than period bars returns None."""
        close = pd.Series([10.0] * 5)
        volume = pd.Series([100.0] * 5)
        result = compute_dollar_volume_trend(close, volume, period=20)
        assert result is None

    def test_mismatched_lengths_raises(self) -> None:
        """Mismatched lengths raises ValueError."""
        close = pd.Series([10.0] * 20)
        volume = pd.Series([100.0] * 15)
        with pytest.raises(ValueError, match="equal length"):
            compute_dollar_volume_trend(close, volume, period=20)

    def test_uses_last_n_bars(self) -> None:
        """Only the last `period` bars are used for slope calculation."""
        # First 10 bars: increasing, last 20 bars: flat
        close = pd.Series([10.0] * 30)
        volume_data = list(range(1, 11)) + [100.0] * 20
        volume = pd.Series(volume_data, dtype=float)
        result = compute_dollar_volume_trend(close, volume, period=20)
        assert result is not None
        # Last 20 bars are all 100*10=1000, so slope ~ 0
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_custom_period(self) -> None:
        """Custom period works correctly."""
        close = pd.Series([10.0] * 10)
        volume = pd.Series(range(1, 11), dtype=float)
        result = compute_dollar_volume_trend(close, volume, period=10)
        assert result is not None
        assert result > 0
