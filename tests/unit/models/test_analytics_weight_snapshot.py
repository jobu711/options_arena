"""Unit tests for WeightSnapshot analytics model.

Tests cover:
- Happy-path construction with valid data
- Frozen enforcement (attribute reassignment raises ValidationError)
- UTC datetime validator rejects naive datetimes
- UTC datetime validator rejects non-UTC timezones
- window_days validator rejects zero
- weights validator rejects empty list
- JSON serialization roundtrip fidelity
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import AgentWeightsComparison, WeightSnapshot

NOW_UTC = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)


def _make_weights() -> list[AgentWeightsComparison]:
    """Create a sample list of AgentWeightsComparison for reuse."""
    return [
        AgentWeightsComparison(
            agent_name="trend",
            manual_weight=0.17,
            auto_weight=0.22,
            brier_score=0.18,
            sample_size=50,
        ),
        AgentWeightsComparison(
            agent_name="volatility",
            manual_weight=0.17,
            auto_weight=0.15,
            brier_score=0.25,
            sample_size=30,
        ),
    ]


class TestWeightSnapshot:
    """Tests for the WeightSnapshot frozen model."""

    def test_construction_valid(self) -> None:
        """Verify WeightSnapshot constructs with all required fields."""
        weights = _make_weights()
        snap = WeightSnapshot(
            computed_at=NOW_UTC,
            window_days=90,
            weights=weights,
        )
        assert snap.computed_at == NOW_UTC
        assert snap.window_days == 90
        assert len(snap.weights) == 2
        assert snap.weights[0].agent_name == "trend"
        assert snap.weights[1].agent_name == "volatility"

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        snap = WeightSnapshot(
            computed_at=NOW_UTC,
            window_days=90,
            weights=_make_weights(),
        )
        with pytest.raises(ValidationError):
            snap.window_days = 30  # type: ignore[misc]

    def test_computed_at_rejects_naive_datetime(self) -> None:
        """Verify computed_at rejects timezone-naive datetimes."""
        with pytest.raises(ValidationError, match="computed_at must be UTC"):
            WeightSnapshot(
                computed_at=datetime(2026, 3, 7, 12, 0, 0),  # naive
                window_days=90,
                weights=_make_weights(),
            )

    def test_computed_at_rejects_non_utc(self) -> None:
        """Verify computed_at rejects non-UTC timezone."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="computed_at must be UTC"):
            WeightSnapshot(
                computed_at=datetime(2026, 3, 7, 12, 0, 0, tzinfo=est),
                window_days=90,
                weights=_make_weights(),
            )

    def test_window_days_rejects_zero(self) -> None:
        """Verify window_days rejects zero (must be >= 1)."""
        with pytest.raises(ValidationError, match="window_days must be >= 1"):
            WeightSnapshot(
                computed_at=NOW_UTC,
                window_days=0,
                weights=_make_weights(),
            )

    def test_weights_rejects_empty_list(self) -> None:
        """Verify weights rejects an empty list."""
        with pytest.raises(ValidationError, match="weights must not be empty"):
            WeightSnapshot(
                computed_at=NOW_UTC,
                window_days=90,
                weights=[],
            )

    @pytest.mark.parametrize(
        ("manual_weight", "auto_weight", "brier_score"),
        [
            (float("nan"), 0.22, 0.18),
            (0.17, float("inf"), 0.18),
            (0.17, 0.22, float("-inf")),
        ],
        ids=["nan-manual", "inf-auto", "neginf-brier"],
    )
    def test_weights_reject_non_finite_values(
        self, manual_weight: float, auto_weight: float, brier_score: float
    ) -> None:
        """Verify isfinite validators reject NaN/inf on weight fields."""
        with pytest.raises(ValidationError):
            WeightSnapshot(
                computed_at=NOW_UTC,
                window_days=90,
                weights=[
                    AgentWeightsComparison(
                        agent_name="trend",
                        manual_weight=manual_weight,
                        auto_weight=auto_weight,
                        brier_score=brier_score,
                        sample_size=50,
                    )
                ],
            )

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization/deserialization fidelity."""
        snap = WeightSnapshot(
            computed_at=NOW_UTC,
            window_days=90,
            weights=_make_weights(),
        )
        json_str = snap.model_dump_json()
        restored = WeightSnapshot.model_validate_json(json_str)
        assert restored == snap
        assert restored.computed_at == NOW_UTC
        assert restored.window_days == 90
        assert len(restored.weights) == 2
        assert restored.weights[0].agent_name == "trend"
        assert restored.weights[0].auto_weight == pytest.approx(0.22)
