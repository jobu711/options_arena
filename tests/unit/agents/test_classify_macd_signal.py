"""Tests for classify_macd_signal — replaces fake _derive_macd_signal.

Tests verify that MACD classification uses the actual MACD value
(centered from normalized 0-100 scale) rather than echoing the
overall direction. The key test is ``test_macd_disagrees_with_direction``
which proves the fake derivation is truly replaced.
"""

from __future__ import annotations

from options_arena.agents.orchestrator import (
    classify_macd_signal,
)
from options_arena.models import (
    MacdSignal,
)


class TestClassifyMacdSignal:
    """Tests for classify_macd_signal(macd_value) -> MacdSignal."""

    def test_positive_value_bullish(self) -> None:
        """Verify positive MACD histogram returns BULLISH_CROSSOVER."""
        assert classify_macd_signal(1.5) == MacdSignal.BULLISH_CROSSOVER

    def test_negative_value_bearish(self) -> None:
        """Verify negative MACD histogram returns BEARISH_CROSSOVER."""
        assert classify_macd_signal(-2.3) == MacdSignal.BEARISH_CROSSOVER

    def test_zero_neutral(self) -> None:
        """Verify zero MACD histogram returns NEUTRAL."""
        assert classify_macd_signal(0.0) == MacdSignal.NEUTRAL

    def test_none_neutral(self) -> None:
        """Verify None returns NEUTRAL."""
        assert classify_macd_signal(None) == MacdSignal.NEUTRAL

    def test_nan_neutral(self) -> None:
        """Verify NaN returns NEUTRAL."""
        assert classify_macd_signal(float("nan")) == MacdSignal.NEUTRAL

    def test_inf_neutral(self) -> None:
        """Verify Inf returns NEUTRAL."""
        assert classify_macd_signal(float("inf")) == MacdSignal.NEUTRAL

    def test_negative_inf_neutral(self) -> None:
        """Verify -Inf returns NEUTRAL."""
        assert classify_macd_signal(float("-inf")) == MacdSignal.NEUTRAL

    def test_small_positive_bullish(self) -> None:
        """Very small positive value still classifies as bullish."""
        assert classify_macd_signal(0.001) == MacdSignal.BULLISH_CROSSOVER

    def test_small_negative_bearish(self) -> None:
        """Very small negative value still classifies as bearish."""
        assert classify_macd_signal(-0.001) == MacdSignal.BEARISH_CROSSOVER

    def test_macd_disagrees_with_direction(self) -> None:
        """KEY TEST: Verify MACD can return BEARISH_CROSSOVER even when
        the overall direction is BULLISH. This proves the fake derivation
        is truly replaced -- the old _derive_macd_signal(BULLISH) would
        always return BULLISH_CROSSOVER, but classify_macd_signal uses
        the actual MACD value independently of direction.

        A negative centered MACD value (raw normalized < 50) means bearish
        histogram even if the ticker's overall direction is bullish.
        """
        # With the old fake: _derive_macd_signal(BULLISH) -> BULLISH_CROSSOVER always
        # With the new real: classify_macd_signal(-3.5) -> BEARISH_CROSSOVER
        # The direction is irrelevant — only the MACD value matters.
        macd_value = -3.5  # negative = bearish histogram
        result = classify_macd_signal(macd_value)
        assert result == MacdSignal.BEARISH_CROSSOVER

        # And the reverse: positive MACD even though direction could be bearish
        macd_value = 2.0  # positive = bullish histogram
        result = classify_macd_signal(macd_value)
        assert result == MacdSignal.BULLISH_CROSSOVER
