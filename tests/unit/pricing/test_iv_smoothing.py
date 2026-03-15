"""Unit tests for IV smoothing via put-call parity spread weighting.

Tests cover:
- Equal-spread weighting (simple average).
- Tighter-call-spread weighting (result closer to call_iv).
- Single-valid IV fallback (NaN put or call).
- Both-invalid returns NaN.
- Zero IV treated as invalid.
- Negative IV treated as invalid.
- Zero spreads (bid == ask) produce simple average.
- Zero bid with positive ask uses ask-based spread.
- Wildly different IVs (ratio > 2.0) logs warning, still averages.
- Parametrized known-value matrix.
"""

import logging
import math

import pytest

from options_arena.pricing.iv_smoothing import smooth_iv_parity

# ---------------------------------------------------------------------------
# 1. Basic weighting behavior
# ---------------------------------------------------------------------------


class TestBasicWeighting:
    """Tests for core weighting logic with valid inputs."""

    def test_both_valid_equal_spreads(self) -> None:
        """Equal spreads on both sides produce a simple average."""
        result = smooth_iv_parity(
            call_iv=0.30,
            put_iv=0.40,
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert result == pytest.approx(0.35, rel=1e-6)

    def test_tighter_call_spread_weights_call(self) -> None:
        """Tighter call spread gives call_iv more weight."""
        result = smooth_iv_parity(
            call_iv=0.30,
            put_iv=0.40,
            call_bid=5.00,
            call_ask=5.10,  # tight call spread (1.98%)
            put_bid=4.00,
            put_ask=6.00,  # wide put spread (40%)
        )
        # Call has much tighter spread, so result should be closer to 0.30
        assert result < 0.35
        assert result > 0.30

    def test_tighter_put_spread_weights_put(self) -> None:
        """Tighter put spread gives put_iv more weight."""
        result = smooth_iv_parity(
            call_iv=0.30,
            put_iv=0.40,
            call_bid=4.00,
            call_ask=6.00,  # wide call spread
            put_bid=5.00,
            put_ask=5.10,  # tight put spread
        )
        # Put has much tighter spread, so result should be closer to 0.40
        assert result > 0.35
        assert result < 0.40


# ---------------------------------------------------------------------------
# 2. Single-valid IV fallback
# ---------------------------------------------------------------------------


class TestSingleValidFallback:
    """Tests for cases where only one IV is valid."""

    def test_only_call_iv_valid(self) -> None:
        """Put IV is NaN -> returns call_iv."""
        result = smooth_iv_parity(
            call_iv=0.30,
            put_iv=float("nan"),
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert result == pytest.approx(0.30, rel=1e-6)

    def test_only_put_iv_valid(self) -> None:
        """Call IV is NaN -> returns put_iv."""
        result = smooth_iv_parity(
            call_iv=float("nan"),
            put_iv=0.40,
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert result == pytest.approx(0.40, rel=1e-6)


# ---------------------------------------------------------------------------
# 3. Both invalid -> NaN
# ---------------------------------------------------------------------------


class TestBothInvalid:
    """Tests for cases where both IVs are invalid."""

    def test_both_nan_returns_nan(self) -> None:
        """Both IVs NaN -> returns NaN."""
        result = smooth_iv_parity(
            call_iv=float("nan"),
            put_iv=float("nan"),
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert math.isnan(result)

    def test_both_inf_returns_nan(self) -> None:
        """Both IVs Inf -> returns NaN."""
        result = smooth_iv_parity(
            call_iv=float("inf"),
            put_iv=float("inf"),
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# 4. Zero / negative IV treated as invalid
# ---------------------------------------------------------------------------


class TestInvalidIV:
    """Tests for zero and negative IV values."""

    def test_zero_iv_treated_as_invalid(self) -> None:
        """IV of 0.0 is not positive -> returns valid side."""
        result = smooth_iv_parity(
            call_iv=0.0,
            put_iv=0.40,
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert result == pytest.approx(0.40, rel=1e-6)

    def test_negative_iv_treated_as_invalid(self) -> None:
        """Negative IV -> returns valid side."""
        result = smooth_iv_parity(
            call_iv=-0.10,
            put_iv=0.35,
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert result == pytest.approx(0.35, rel=1e-6)

    def test_zero_call_iv_and_nan_put_iv(self) -> None:
        """Both invalid (zero call, NaN put) -> returns NaN."""
        result = smooth_iv_parity(
            call_iv=0.0,
            put_iv=float("nan"),
            call_bid=5.0,
            call_ask=6.0,
            put_bid=5.0,
            put_ask=6.0,
        )
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# 5. Zero-spread edge cases
# ---------------------------------------------------------------------------


class TestZeroSpread:
    """Tests for zero-spread (bid == ask) scenarios."""

    def test_zero_spreads_simple_average(self) -> None:
        """bid == ask on both sides -> simple average."""
        result = smooth_iv_parity(
            call_iv=0.20,
            put_iv=0.30,
            call_bid=5.0,
            call_ask=5.0,
            put_bid=5.0,
            put_ask=5.0,
        )
        assert result == pytest.approx(0.25, rel=1e-6)

    def test_zero_bid_uses_ask_spread(self) -> None:
        """bid=0, ask>0 -> spread computed from ask, still produces valid result."""
        result = smooth_iv_parity(
            call_iv=0.30,
            put_iv=0.40,
            call_bid=0.0,
            call_ask=1.0,  # spread_pct = 1.0/0.5 = 2.0  (but mid=0.5)
            put_bid=5.0,
            put_ask=6.0,  # spread_pct = 1.0/5.5 ~= 0.182
        )
        # Put has tighter relative spread -> result closer to put_iv
        assert math.isfinite(result)
        assert result > 0.30
        assert result < 0.40


# ---------------------------------------------------------------------------
# 6. Wildly different IVs -> warning
# ---------------------------------------------------------------------------


class TestWarningOnLargeDiscrepancy:
    """Tests for IV ratio > 2.0 warning behavior."""

    def test_wildly_different_ivs_still_averages(self, caplog: pytest.LogCaptureFixture) -> None:
        """IV ratio > 2.0 -> logs warning, still returns a valid weighted average."""
        with caplog.at_level(logging.WARNING, logger="options_arena.pricing.iv_smoothing"):
            result = smooth_iv_parity(
                call_iv=0.10,
                put_iv=0.50,
                call_bid=5.0,
                call_ask=6.0,
                put_bid=5.0,
                put_ask=6.0,
            )
        # Equal spreads -> simple average despite warning
        assert result == pytest.approx(0.30, rel=1e-6)
        assert "IV ratio" in caplog.text
        assert "exceeds" in caplog.text

    def test_ratio_below_threshold_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """IV ratio < 2.0 -> no warning logged."""
        with caplog.at_level(logging.WARNING, logger="options_arena.pricing.iv_smoothing"):
            smooth_iv_parity(
                call_iv=0.25,
                put_iv=0.35,
                call_bid=5.0,
                call_ask=6.0,
                put_bid=5.0,
                put_ask=6.0,
            )
        assert "IV ratio" not in caplog.text


# ---------------------------------------------------------------------------
# 7. Parametrized known-value matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "call_iv",
        "put_iv",
        "call_bid",
        "call_ask",
        "put_bid",
        "put_ask",
        "expected",
        "description",
    ),
    [
        # Equal IVs, any spreads -> exact IV
        (0.25, 0.25, 3.0, 4.0, 3.0, 4.0, 0.25, "equal_ivs"),
        # Equal spreads -> simple average
        (0.20, 0.40, 5.0, 6.0, 5.0, 6.0, 0.30, "equal_spreads_avg"),
        # One NaN -> other side
        (0.30, float("nan"), 5.0, 6.0, 5.0, 6.0, 0.30, "nan_put_returns_call"),
        (float("nan"), 0.40, 5.0, 6.0, 5.0, 6.0, 0.40, "nan_call_returns_put"),
        # Both zero spreads -> simple average
        (0.20, 0.30, 5.0, 5.0, 5.0, 5.0, 0.25, "zero_spread_avg"),
        # Zero IV -> returns valid side
        (0.0, 0.50, 5.0, 6.0, 5.0, 6.0, 0.50, "zero_call_returns_put"),
        (0.50, 0.0, 5.0, 6.0, 5.0, 6.0, 0.50, "zero_put_returns_call"),
    ],
    ids=lambda x: x if isinstance(x, str) else "",
)
def test_parametrized_smoothing(
    call_iv: float,
    put_iv: float,
    call_bid: float,
    call_ask: float,
    put_bid: float,
    put_ask: float,
    expected: float,
    description: str,
) -> None:
    """Known-value test matrix for smooth_iv_parity."""
    result = smooth_iv_parity(call_iv, put_iv, call_bid, call_ask, put_bid, put_ask)
    if math.isnan(expected):
        assert math.isnan(result), f"{description}: expected NaN, got {result}"
    else:
        assert result == pytest.approx(expected, rel=1e-6), description


# ---------------------------------------------------------------------------
# 8. Re-export verification
# ---------------------------------------------------------------------------


class TestReExport:
    """Verify smooth_iv_parity is accessible from the pricing package."""

    def test_importable_from_package(self) -> None:
        """smooth_iv_parity must be importable from options_arena.pricing."""
        from options_arena.pricing import smooth_iv_parity as fn

        assert callable(fn)
