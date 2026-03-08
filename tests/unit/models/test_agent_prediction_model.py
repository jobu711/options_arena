"""Tests for the AgentPrediction model — frozen, UTC, confidence validators."""

import math
from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import AgentPrediction, SignalDirection


class TestAgentPredictionModel:
    """Validate AgentPrediction field constraints and immutability."""

    def _make(self, **overrides: object) -> AgentPrediction:
        """Build an AgentPrediction with sensible defaults."""
        defaults: dict[str, object] = {
            "debate_id": 1,
            "agent_name": "bull",
            "direction": SignalDirection.BULLISH,
            "confidence": 0.75,
            "created_at": datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return AgentPrediction(**defaults)  # type: ignore[arg-type]

    def test_happy_path(self) -> None:
        """Construct with valid data — all fields accessible."""
        pred = self._make()
        assert pred.debate_id == 1
        assert pred.agent_name == "bull"
        assert pred.direction == SignalDirection.BULLISH
        assert pred.confidence == pytest.approx(0.75)
        assert pred.created_at == datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

    def test_frozen(self) -> None:
        """Verify AgentPrediction is immutable after construction."""
        pred = self._make()
        with pytest.raises(ValidationError):
            pred.confidence = 0.5  # type: ignore[misc]

    def test_utc_validator_rejects_naive(self) -> None:
        """Verify created_at rejects naive (timezone-unaware) datetime."""
        with pytest.raises(ValidationError, match="created_at must be UTC"):
            self._make(created_at=datetime(2026, 3, 7, 12, 0, 0))

    def test_utc_validator_rejects_non_utc(self) -> None:
        """Verify created_at rejects non-UTC timezone."""
        est = timezone(offset=__import__("datetime").timedelta(hours=-5))
        with pytest.raises(ValidationError, match="created_at must be UTC"):
            self._make(created_at=datetime(2026, 3, 7, 12, 0, 0, tzinfo=est))

    def test_utc_validator_accepts_utc(self) -> None:
        """Verify created_at accepts UTC datetime."""
        pred = self._make(created_at=datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC))
        assert pred.created_at.tzinfo is not None

    def test_confidence_validator_lower_bound(self) -> None:
        """Verify confidence rejects values below 0.0."""
        with pytest.raises(ValidationError, match="confidence"):
            self._make(confidence=-0.1)

    def test_confidence_validator_upper_bound(self) -> None:
        """Verify confidence rejects values above 1.0."""
        with pytest.raises(ValidationError, match="confidence"):
            self._make(confidence=1.1)

    def test_confidence_validator_accepts_bounds(self) -> None:
        """Verify confidence accepts boundary values 0.0 and 1.0."""
        pred_low = self._make(confidence=0.0)
        assert pred_low.confidence == pytest.approx(0.0)
        pred_high = self._make(confidence=1.0)
        assert pred_high.confidence == pytest.approx(1.0)

    def test_confidence_rejects_nan(self) -> None:
        """Verify NaN rejected by isfinite() guard."""
        with pytest.raises(ValidationError, match="finite"):
            self._make(confidence=float("nan"))

    def test_confidence_rejects_inf(self) -> None:
        """Verify Inf rejected by isfinite() guard."""
        with pytest.raises(ValidationError, match="finite"):
            self._make(confidence=math.inf)

    def test_direction_optional(self) -> None:
        """Verify direction can be None (risk agent has no direction)."""
        pred = self._make(direction=None)
        assert pred.direction is None

    def test_direction_accepts_all_values(self) -> None:
        """Verify direction accepts all SignalDirection enum members."""
        for d in SignalDirection:
            pred = self._make(direction=d)
            assert pred.direction == d

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization roundtrip preserves all fields."""
        pred = self._make()
        roundtripped = AgentPrediction.model_validate_json(pred.model_dump_json())
        assert roundtripped == pred
        assert roundtripped.direction == pred.direction
        assert roundtripped.confidence == pytest.approx(pred.confidence)

    def test_json_roundtrip_none_direction(self) -> None:
        """Verify JSON roundtrip preserves None direction."""
        pred = self._make(direction=None)
        roundtripped = AgentPrediction.model_validate_json(pred.model_dump_json())
        assert roundtripped.direction is None
