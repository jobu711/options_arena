"""Unit tests for DimensionalScores and DirectionSignal models.

Tests cover:
  - DimensionalScores: all-None construction, partial fill, frozen, score range validation,
    NaN/Inf rejection, JSON roundtrip
  - DirectionSignal: construction, frozen, confidence validation, contributing_signals
    at-least-1 validation, JSON roundtrip
"""

import pytest
from pydantic import ValidationError

from options_arena.models import (
    DimensionalScores,
    DirectionSignal,
    SignalDirection,
)

# ===========================================================================
# DimensionalScores
# ===========================================================================


class TestDimensionalScores:
    def test_all_none_construction(self) -> None:
        """DimensionalScores() constructs with all fields defaulting to None."""
        ds = DimensionalScores()
        assert ds.trend is None
        assert ds.iv_vol is None
        assert ds.hv_vol is None
        assert ds.flow is None
        assert ds.microstructure is None
        assert ds.fundamental is None
        assert ds.regime is None
        assert ds.risk is None

    def test_partial_fill(self) -> None:
        """DimensionalScores accepts partial field population."""
        ds = DimensionalScores(trend=72.5, iv_vol=65.0, flow=80.0)
        assert ds.trend == pytest.approx(72.5)
        assert ds.iv_vol == pytest.approx(65.0)
        assert ds.flow == pytest.approx(80.0)
        assert ds.hv_vol is None
        assert ds.microstructure is None
        assert ds.fundamental is None
        assert ds.regime is None
        assert ds.risk is None

    def test_all_populated(self) -> None:
        """DimensionalScores with all 8 fields populated."""
        ds = DimensionalScores(
            trend=50.0,
            iv_vol=60.0,
            hv_vol=55.0,
            flow=70.0,
            microstructure=45.0,
            fundamental=65.0,
            regime=40.0,
            risk=75.0,
        )
        assert ds.trend == pytest.approx(50.0)
        assert ds.iv_vol == pytest.approx(60.0)
        assert ds.hv_vol == pytest.approx(55.0)
        assert ds.flow == pytest.approx(70.0)
        assert ds.microstructure == pytest.approx(45.0)
        assert ds.fundamental == pytest.approx(65.0)
        assert ds.regime == pytest.approx(40.0)
        assert ds.risk == pytest.approx(75.0)

    def test_frozen(self) -> None:
        """DimensionalScores is frozen: attribute reassignment raises ValidationError."""
        ds = DimensionalScores(trend=50.0)
        with pytest.raises(ValidationError):
            ds.trend = 60.0  # type: ignore[misc]

    def test_score_boundary_zero(self) -> None:
        """DimensionalScores accepts score = 0.0 (lower boundary)."""
        ds = DimensionalScores(trend=0.0)
        assert ds.trend == pytest.approx(0.0)

    def test_score_boundary_hundred(self) -> None:
        """DimensionalScores accepts score = 100.0 (upper boundary)."""
        ds = DimensionalScores(trend=100.0)
        assert ds.trend == pytest.approx(100.0)

    def test_score_below_zero_raises(self) -> None:
        """DimensionalScores rejects score < 0."""
        with pytest.raises(ValidationError, match="score must be in"):
            DimensionalScores(trend=-1.0)

    def test_score_above_hundred_raises(self) -> None:
        """DimensionalScores rejects score > 100."""
        with pytest.raises(ValidationError, match="score must be in"):
            DimensionalScores(iv_vol=101.0)

    def test_score_nan_raises(self) -> None:
        """DimensionalScores rejects NaN score."""
        with pytest.raises(ValidationError, match="score must be finite"):
            DimensionalScores(flow=float("nan"))

    def test_score_inf_raises(self) -> None:
        """DimensionalScores rejects Inf score."""
        with pytest.raises(ValidationError, match="score must be finite"):
            DimensionalScores(regime=float("inf"))

    def test_score_neg_inf_raises(self) -> None:
        """DimensionalScores rejects -Inf score."""
        with pytest.raises(ValidationError, match="score must be finite"):
            DimensionalScores(risk=float("-inf"))

    def test_multiple_invalid_scores(self) -> None:
        """DimensionalScores rejects multiple invalid scores (Pydantic collects all errors)."""
        with pytest.raises(ValidationError):
            DimensionalScores(trend=-5.0, iv_vol=150.0)

    def test_json_roundtrip_all_none(self) -> None:
        """DimensionalScores with all None survives JSON roundtrip."""
        ds = DimensionalScores()
        json_str = ds.model_dump_json()
        restored = DimensionalScores.model_validate_json(json_str)
        assert restored == ds

    def test_json_roundtrip_partial(self) -> None:
        """DimensionalScores with partial fields survives JSON roundtrip."""
        ds = DimensionalScores(trend=72.5, flow=80.0, risk=55.0)
        json_str = ds.model_dump_json()
        restored = DimensionalScores.model_validate_json(json_str)
        assert restored == ds

    def test_json_roundtrip_full(self) -> None:
        """DimensionalScores with all 8 fields survives JSON roundtrip."""
        ds = DimensionalScores(
            trend=50.0,
            iv_vol=60.0,
            hv_vol=55.0,
            flow=70.0,
            microstructure=45.0,
            fundamental=65.0,
            regime=40.0,
            risk=75.0,
        )
        json_str = ds.model_dump_json()
        restored = DimensionalScores.model_validate_json(json_str)
        assert restored == ds

    def test_each_field_validates_independently(self) -> None:
        """Each of the 8 score fields is independently validated."""
        fields = [
            "trend",
            "iv_vol",
            "hv_vol",
            "flow",
            "microstructure",
            "fundamental",
            "regime",
            "risk",
        ]
        for field in fields:
            with pytest.raises(ValidationError):
                DimensionalScores(**{field: float("nan")})
            with pytest.raises(ValidationError):
                DimensionalScores(**{field: -1.0})
            with pytest.raises(ValidationError):
                DimensionalScores(**{field: 101.0})


# ===========================================================================
# DirectionSignal
# ===========================================================================


class TestDirectionSignal:
    def test_construction(self) -> None:
        """DirectionSignal constructs with all fields correctly assigned."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            contributing_signals=["RSI oversold", "SMA alignment", "Volume confirmation"],
        )
        assert ds.direction == SignalDirection.BULLISH
        assert ds.confidence == pytest.approx(0.85)
        assert len(ds.contributing_signals) == 3
        assert "RSI oversold" in ds.contributing_signals

    def test_frozen(self) -> None:
        """DirectionSignal is frozen: attribute reassignment raises ValidationError."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            contributing_signals=["signal"],
        )
        with pytest.raises(ValidationError):
            ds.confidence = 0.5  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """DirectionSignal rejects confidence > 1.0."""
        with pytest.raises(ValidationError, match="confidence"):
            DirectionSignal(
                direction=SignalDirection.BULLISH,
                confidence=1.5,
                contributing_signals=["signal"],
            )

    def test_confidence_too_low_raises(self) -> None:
        """DirectionSignal rejects confidence < 0.0."""
        with pytest.raises(ValidationError, match="confidence"):
            DirectionSignal(
                direction=SignalDirection.BEARISH,
                confidence=-0.1,
                contributing_signals=["signal"],
            )

    def test_confidence_nan_raises(self) -> None:
        """DirectionSignal rejects NaN confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            DirectionSignal(
                direction=SignalDirection.NEUTRAL,
                confidence=float("nan"),
                contributing_signals=["signal"],
            )

    def test_confidence_inf_raises(self) -> None:
        """DirectionSignal rejects Inf confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            DirectionSignal(
                direction=SignalDirection.NEUTRAL,
                confidence=float("inf"),
                contributing_signals=["signal"],
            )

    def test_confidence_boundary_zero(self) -> None:
        """DirectionSignal accepts confidence = 0.0."""
        ds = DirectionSignal(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            contributing_signals=["weak signal"],
        )
        assert ds.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self) -> None:
        """DirectionSignal accepts confidence = 1.0."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            contributing_signals=["strong signal"],
        )
        assert ds.confidence == pytest.approx(1.0)

    def test_empty_contributing_signals_raises(self) -> None:
        """DirectionSignal rejects empty contributing_signals list."""
        with pytest.raises(
            ValidationError, match="contributing_signals must have at least 1 item"
        ):
            DirectionSignal(
                direction=SignalDirection.BULLISH,
                confidence=0.5,
                contributing_signals=[],
            )

    def test_single_contributing_signal(self) -> None:
        """DirectionSignal accepts a single contributing signal."""
        ds = DirectionSignal(
            direction=SignalDirection.BEARISH,
            confidence=0.6,
            contributing_signals=["RSI overbought"],
        )
        assert len(ds.contributing_signals) == 1

    def test_json_roundtrip(self) -> None:
        """DirectionSignal survives JSON serialization/deserialization unchanged."""
        ds = DirectionSignal(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            contributing_signals=["RSI oversold", "SMA alignment", "Volume confirmation"],
        )
        json_str = ds.model_dump_json()
        restored = DirectionSignal.model_validate_json(json_str)
        assert restored == ds

    def test_all_directions(self) -> None:
        """DirectionSignal accepts all SignalDirection values."""
        for direction in SignalDirection:
            ds = DirectionSignal(
                direction=direction,
                confidence=0.5,
                contributing_signals=["test"],
            )
            assert ds.direction == direction
