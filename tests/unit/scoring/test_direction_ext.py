"""Unit tests for continuous direction confidence via compute_direction_signal.

Tests the extended direction signal functionality added by the DSE
(Deep Signal Engine), which provides continuous confidence (0-1) and
contributing signal breakdowns on top of the discrete 3-class direction.
"""

import pytest

from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals
from options_arena.models.scoring import DirectionSignal
from options_arena.scoring.dimensional import compute_direction_signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_INDICATOR_FIELDS: set[str] = set(IndicatorSignals.model_fields.keys())


def _make_signals(**kwargs: float | None) -> IndicatorSignals:
    """Build IndicatorSignals with specified fields; unspecified remain None."""
    return IndicatorSignals(**kwargs)


def _make_full_signals(value: float = 60.0) -> IndicatorSignals:
    """Build IndicatorSignals with ALL 58 fields set to *value*."""
    return IndicatorSignals(**{f: value for f in ALL_INDICATOR_FIELDS})


# ---------------------------------------------------------------------------
# DirectionSignal model construction tests
# ---------------------------------------------------------------------------


class TestDirectionSignalConstruction:
    """Tests for DirectionSignal model itself."""

    def test_basic_construction(self) -> None:
        """DirectionSignal can be constructed with valid data."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=0.75,
            contributing_signals=["rsi", "adx"],
        )
        assert ds.direction is SignalDirection.BULLISH
        assert ds.confidence == pytest.approx(0.75, abs=0.001)
        assert ds.contributing_signals == ["rsi", "adx"]

    def test_frozen_immutable(self) -> None:
        """DirectionSignal is frozen and rejects attribute mutation."""
        ds = DirectionSignal(
            direction=SignalDirection.BEARISH,
            confidence=0.5,
            contributing_signals=["rsi"],
        )
        with pytest.raises(Exception):  # noqa: B017
            ds.direction = SignalDirection.BULLISH  # type: ignore[misc]

    def test_confidence_rejects_negative(self) -> None:
        """Confidence below 0.0 raises ValidationError."""
        with pytest.raises(Exception):  # noqa: B017
            DirectionSignal(
                direction=SignalDirection.NEUTRAL,
                confidence=-0.1,
                contributing_signals=["rsi"],
            )

    def test_confidence_rejects_above_one(self) -> None:
        """Confidence above 1.0 raises ValidationError."""
        with pytest.raises(Exception):  # noqa: B017
            DirectionSignal(
                direction=SignalDirection.NEUTRAL,
                confidence=1.1,
                contributing_signals=["rsi"],
            )

    def test_contributing_signals_rejects_empty(self) -> None:
        """Empty contributing_signals list raises ValidationError."""
        with pytest.raises(Exception):  # noqa: B017
            DirectionSignal(
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
                contributing_signals=[],
            )

    def test_confidence_boundary_zero(self) -> None:
        """Confidence == 0.0 is valid."""
        ds = DirectionSignal(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            contributing_signals=["rsi"],
        )
        assert ds.confidence == pytest.approx(0.0, abs=1e-9)

    def test_confidence_boundary_one(self) -> None:
        """Confidence == 1.0 is valid."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            contributing_signals=["rsi"],
        )
        assert ds.confidence == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# compute_direction_signal edge cases
# ---------------------------------------------------------------------------


class TestComputeDirectionSignalEdgeCases:
    """Edge cases for compute_direction_signal()."""

    def test_all_indicators_none_neutral_low_confidence(self) -> None:
        """All None indicators produce NEUTRAL with minimum confidence."""
        signals = IndicatorSignals()
        result = compute_direction_signal(signals, 50.0, SignalDirection.NEUTRAL)

        assert result.direction is SignalDirection.NEUTRAL
        assert result.confidence == pytest.approx(0.1, abs=0.01)
        assert "no_valid_indicators" in result.contributing_signals

    def test_single_bullish_indicator(self) -> None:
        """A single high indicator with bullish direction produces valid signal."""
        signals = _make_signals(rsi=90.0)
        result = compute_direction_signal(signals, 70.0, SignalDirection.BULLISH)

        assert result.direction is SignalDirection.BULLISH
        assert result.confidence >= 0.1
        assert "rsi" in result.contributing_signals

    def test_single_bearish_indicator(self) -> None:
        """A single low indicator with bearish direction produces valid signal."""
        signals = _make_signals(rsi=10.0)
        result = compute_direction_signal(signals, 30.0, SignalDirection.BEARISH)

        assert result.direction is SignalDirection.BEARISH
        assert result.confidence >= 0.1
        assert "rsi" in result.contributing_signals

    def test_mixed_signals_bullish(self) -> None:
        """Mixed high/low signals with bullish direction still works."""
        signals = _make_signals(rsi=80.0, adx=20.0, obv=90.0, bb_width=10.0)
        result = compute_direction_signal(signals, 55.0, SignalDirection.BULLISH)

        assert result.direction is SignalDirection.BULLISH
        # Should have rsi and obv as bullish contributors
        assert any(s in result.contributing_signals for s in ["rsi", "obv"])

    def test_extreme_high_composite_score(self) -> None:
        """Composite score at 100.0 contributes to high confidence."""
        signals = _make_full_signals(90.0)
        result = compute_direction_signal(signals, 100.0, SignalDirection.BULLISH)

        assert result.confidence > 0.5

    def test_extreme_low_composite_score(self) -> None:
        """Composite score at 0.0 with bearish direction."""
        signals = _make_full_signals(10.0)
        result = compute_direction_signal(signals, 0.0, SignalDirection.BEARISH)

        assert result.confidence > 0.5

    def test_neutral_at_midpoint(self) -> None:
        """Score at exactly 50.0 with all indicators at 50 (no directional signal)."""
        signals = _make_full_signals(50.0)
        result = compute_direction_signal(signals, 50.0, SignalDirection.NEUTRAL)

        # With everything at 50, nothing is > 60 (bullish) or < 40 (bearish)
        # Score magnitude is 0 (at 50). Should produce low confidence.
        assert result.direction is SignalDirection.NEUTRAL
        assert result.confidence <= 0.5

    def test_nan_indicator_ignored(self) -> None:
        """NaN indicator values are excluded from analysis."""
        signals = _make_signals(rsi=float("nan"), adx=80.0)
        result = compute_direction_signal(signals, 65.0, SignalDirection.BULLISH)

        # NaN rsi should be ignored; only adx (80 > 60) should contribute
        assert "rsi" not in result.contributing_signals
        assert "adx" in result.contributing_signals

    def test_inf_indicator_ignored(self) -> None:
        """Infinity indicator values are excluded from analysis."""
        signals = _make_signals(rsi=float("inf"), adx=80.0)
        result = compute_direction_signal(signals, 65.0, SignalDirection.BULLISH)

        assert "rsi" not in result.contributing_signals
        assert "adx" in result.contributing_signals

    def test_fallback_contributing_signal_when_none_agree(self) -> None:
        """When no indicators agree with direction, fallback to 'composite_score'."""
        # All indicators at 50 (between 40-60, neither bullish nor bearish)
        signals = _make_signals(rsi=50.0, adx=50.0)
        result = compute_direction_signal(signals, 70.0, SignalDirection.BULLISH)

        # No indicators > 60 → no bullish contributing signals
        # Fallback should be "composite_score"
        assert "composite_score" in result.contributing_signals

    def test_all_three_directions(self) -> None:
        """Each direction value produces a valid result."""
        signals = _make_signals(rsi=70.0, adx=65.0)
        for direction in SignalDirection:
            result = compute_direction_signal(signals, 60.0, direction)
            assert result.direction is direction
            assert 0.1 <= result.confidence <= 1.0
            assert len(result.contributing_signals) >= 1

    def test_confidence_monotonic_with_score_distance_from_50(self) -> None:
        """Higher distance from 50 in composite score increases confidence."""
        signals = _make_full_signals(80.0)

        result_near_50 = compute_direction_signal(signals, 55.0, SignalDirection.BULLISH)
        result_far_from_50 = compute_direction_signal(signals, 95.0, SignalDirection.BULLISH)

        assert result_far_from_50.confidence >= result_near_50.confidence
