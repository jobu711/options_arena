"""Tests for ensemble diversity model fields.

Verifies:
- ``ExtendedTradeThesis.ensemble_entropy`` field with ``isfinite()`` validator
- ``VolatilityThesis.direction`` field with backward-compatible deserialization
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from options_arena.models import SignalDirection, SpreadType
from options_arena.models.analysis import ExtendedTradeThesis, VolatilityThesis

# ---------------------------------------------------------------------------
# ExtendedTradeThesis.ensemble_entropy
# ---------------------------------------------------------------------------


def _make_extended_thesis(**overrides: object) -> ExtendedTradeThesis:
    """Build a minimal ExtendedTradeThesis with overridable fields."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.65,
        "summary": "Test summary.",
        "bull_score": 7.0,
        "bear_score": 4.0,
        "key_factors": ["factor1"],
        "risk_assessment": "Test risk.",
        "agents_completed": 3,
    }
    defaults.update(overrides)
    return ExtendedTradeThesis(**defaults)  # type: ignore[arg-type]


class TestExtendedTradeThesisEntropy:
    """Tests for ExtendedTradeThesis.ensemble_entropy field."""

    def test_default_none(self) -> None:
        """Verify ensemble_entropy defaults to None (backward compat)."""
        thesis = _make_extended_thesis()
        assert thesis.ensemble_entropy is None

    def test_valid_entropy(self) -> None:
        """Verify valid entropy value accepted."""
        thesis = _make_extended_thesis(ensemble_entropy=1.585)
        assert thesis.ensemble_entropy == pytest.approx(1.585, abs=0.001)

    def test_zero_entropy(self) -> None:
        """Verify zero entropy accepted (unanimous vote)."""
        thesis = _make_extended_thesis(ensemble_entropy=0.0)
        assert thesis.ensemble_entropy == pytest.approx(0.0)

    def test_rejects_nan(self) -> None:
        """Verify NaN rejected by isfinite() validator."""
        with pytest.raises(ValidationError, match="ensemble_entropy must be finite"):
            _make_extended_thesis(ensemble_entropy=float("nan"))

    def test_rejects_inf(self) -> None:
        """Verify Inf rejected by isfinite() validator."""
        with pytest.raises(ValidationError, match="ensemble_entropy must be finite"):
            _make_extended_thesis(ensemble_entropy=float("inf"))

    def test_rejects_neg_inf(self) -> None:
        """Verify -Inf rejected by isfinite() validator."""
        with pytest.raises(ValidationError, match="ensemble_entropy must be finite"):
            _make_extended_thesis(ensemble_entropy=float("-inf"))

    def test_rejects_negative(self) -> None:
        """Verify negative entropy rejected — Shannon entropy is non-negative."""
        with pytest.raises(ValidationError, match="ensemble_entropy must be >= 0.0"):
            _make_extended_thesis(ensemble_entropy=-0.1)

    def test_backward_compat_deserialization(self) -> None:
        """Verify existing JSON without ensemble_entropy deserializes."""
        thesis = _make_extended_thesis(agent_agreement_score=0.8)
        data = thesis.model_dump()
        # Remove ensemble_entropy key entirely to simulate old schema data
        del data["ensemble_entropy"]
        restored = ExtendedTradeThesis.model_validate(data)
        assert restored.ensemble_entropy is None

    def test_roundtrip_with_entropy(self) -> None:
        """Verify ensemble_entropy survives JSON roundtrip."""
        thesis = _make_extended_thesis(ensemble_entropy=1.0)
        json_data = thesis.model_dump_json()
        restored = ExtendedTradeThesis.model_validate_json(json_data)
        assert restored.ensemble_entropy == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# VolatilityThesis.direction
# ---------------------------------------------------------------------------


def _make_vol_thesis(**overrides: object) -> VolatilityThesis:
    """Build a minimal VolatilityThesis with overridable fields."""
    defaults: dict[str, object] = {
        "iv_assessment": "overpriced",
        "iv_rank_interpretation": "IV rank at 85.",
        "confidence": 0.75,
        "recommended_strategy": SpreadType.IRON_CONDOR,
        "strategy_rationale": "High IV favors selling premium.",
        "target_iv_entry": 85.0,
        "target_iv_exit": 50.0,
        "suggested_strikes": ["185C", "195C"],
        "key_vol_factors": ["IV rank 85"],
        "model_used": "test-model",
    }
    defaults.update(overrides)
    return VolatilityThesis(**defaults)  # type: ignore[arg-type]


class TestVolatilityThesisDirection:
    """Tests for VolatilityThesis.direction field."""

    def test_default_neutral(self) -> None:
        """Verify direction defaults to NEUTRAL."""
        thesis = _make_vol_thesis()
        assert thesis.direction == SignalDirection.NEUTRAL

    def test_explicit_bullish(self) -> None:
        """Verify explicit bullish direction accepted."""
        thesis = _make_vol_thesis(direction=SignalDirection.BULLISH)
        assert thesis.direction == SignalDirection.BULLISH

    def test_explicit_bearish(self) -> None:
        """Verify explicit bearish direction accepted."""
        thesis = _make_vol_thesis(direction=SignalDirection.BEARISH)
        assert thesis.direction == SignalDirection.BEARISH

    def test_backward_compat_deserialization(self) -> None:
        """Verify existing vol_json without direction deserializes with NEUTRAL default."""
        # Construct without direction (uses default), dump, re-validate
        thesis = _make_vol_thesis()
        data = thesis.model_dump()
        del data["direction"]  # Simulate old serialized data without direction
        restored = VolatilityThesis.model_validate(data)
        assert restored.direction == SignalDirection.NEUTRAL

    def test_direction_roundtrip(self) -> None:
        """Verify direction survives JSON roundtrip."""
        thesis = _make_vol_thesis(direction=SignalDirection.BEARISH)
        json_data = thesis.model_dump_json()
        restored = VolatilityThesis.model_validate_json(json_data)
        assert restored.direction == SignalDirection.BEARISH

    def test_frozen_rejects_assignment(self) -> None:
        """Verify direction cannot be reassigned on frozen model."""
        thesis = _make_vol_thesis(direction=SignalDirection.NEUTRAL)
        with pytest.raises(ValidationError):
            thesis.direction = SignalDirection.BULLISH  # type: ignore[misc]

    def test_string_deserialization(self) -> None:
        """Verify direction can be deserialized from string value."""
        thesis = _make_vol_thesis(direction="bullish")  # type: ignore[arg-type]
        assert thesis.direction == SignalDirection.BULLISH
