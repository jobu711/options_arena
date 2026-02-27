"""Unit tests for diff models: ScoreChange, ScanDiffResult, DebateTrendPoint.

Tests cover:
- Happy path construction with all fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- Score bounds validation (0-100, finite)
- Confidence bounds validation (0-1, finite)
- UTC validator rejects naive and non-UTC timestamps
- NaN/Inf rejection on numeric fields
- JSON serialization roundtrip
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from options_arena.models import (
    DebateTrendPoint,
    ScanDiffResult,
    ScoreChange,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_score_change() -> ScoreChange:
    """Create a valid ScoreChange instance for reuse."""
    return ScoreChange(
        ticker="AAPL",
        old_score=72.5,
        new_score=78.3,
        old_direction=SignalDirection.BULLISH,
        new_direction=SignalDirection.BULLISH,
        direction_changed=False,
        score_delta=5.8,
    )


@pytest.fixture
def sample_scan_diff_result(sample_score_change: ScoreChange) -> ScanDiffResult:
    """Create a valid ScanDiffResult instance for reuse."""
    return ScanDiffResult(
        old_scan_id=1,
        new_scan_id=2,
        changes=[sample_score_change],
        new_entries=["NVDA"],
        removed_entries=["INTC"],
        created_at=datetime(2026, 2, 1, 8, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_debate_trend_point() -> DebateTrendPoint:
    """Create a valid DebateTrendPoint instance for reuse."""
    return DebateTrendPoint(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        is_fallback=False,
        created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# ScoreChange Tests
# ---------------------------------------------------------------------------


class TestScoreChange:
    """Tests for the ScoreChange model."""

    def test_happy_path_construction(self, sample_score_change: ScoreChange) -> None:
        """ScoreChange constructs with all fields correctly assigned."""
        assert sample_score_change.ticker == "AAPL"
        assert sample_score_change.old_score == pytest.approx(72.5)
        assert sample_score_change.new_score == pytest.approx(78.3)
        assert sample_score_change.old_direction == SignalDirection.BULLISH
        assert sample_score_change.new_direction == SignalDirection.BULLISH
        assert sample_score_change.direction_changed is False
        assert sample_score_change.score_delta == pytest.approx(5.8)

    def test_frozen_enforcement(self, sample_score_change: ScoreChange) -> None:
        """ScoreChange is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_score_change.ticker = "MSFT"  # type: ignore[misc]

    def test_old_score_rejects_negative(self) -> None:
        """ScoreChange rejects negative old_score."""
        with pytest.raises(ValidationError, match="score must be in"):
            ScoreChange(
                ticker="AAPL",
                old_score=-1.0,
                new_score=50.0,
                old_direction=SignalDirection.BEARISH,
                new_direction=SignalDirection.NEUTRAL,
                direction_changed=True,
                score_delta=51.0,
            )

    def test_old_score_rejects_above_100(self) -> None:
        """ScoreChange rejects old_score above 100."""
        with pytest.raises(ValidationError, match="score must be in"):
            ScoreChange(
                ticker="AAPL",
                old_score=101.0,
                new_score=50.0,
                old_direction=SignalDirection.BULLISH,
                new_direction=SignalDirection.NEUTRAL,
                direction_changed=True,
                score_delta=-51.0,
            )

    def test_new_score_rejects_nan(self) -> None:
        """ScoreChange rejects NaN for new_score."""
        with pytest.raises(ValidationError, match="finite"):
            ScoreChange(
                ticker="AAPL",
                old_score=50.0,
                new_score=float("nan"),
                old_direction=SignalDirection.NEUTRAL,
                new_direction=SignalDirection.NEUTRAL,
                direction_changed=False,
                score_delta=0.0,
            )

    def test_score_delta_rejects_inf(self) -> None:
        """ScoreChange rejects Inf for score_delta."""
        with pytest.raises(ValidationError, match="finite"):
            ScoreChange(
                ticker="AAPL",
                old_score=50.0,
                new_score=50.0,
                old_direction=SignalDirection.NEUTRAL,
                new_direction=SignalDirection.NEUTRAL,
                direction_changed=False,
                score_delta=float("inf"),
            )

    def test_direction_uses_enum(self, sample_score_change: ScoreChange) -> None:
        """ScoreChange old_direction and new_direction are SignalDirection values."""
        assert isinstance(sample_score_change.old_direction, SignalDirection)
        assert isinstance(sample_score_change.new_direction, SignalDirection)

    def test_json_roundtrip(self, sample_score_change: ScoreChange) -> None:
        """ScoreChange survives JSON roundtrip."""
        json_str = sample_score_change.model_dump_json()
        restored = ScoreChange.model_validate_json(json_str)
        assert restored == sample_score_change


# ---------------------------------------------------------------------------
# ScanDiffResult Tests
# ---------------------------------------------------------------------------


class TestScanDiffResult:
    """Tests for the ScanDiffResult model."""

    def test_happy_path_construction(self, sample_scan_diff_result: ScanDiffResult) -> None:
        """ScanDiffResult constructs with all fields correctly assigned."""
        assert sample_scan_diff_result.old_scan_id == 1
        assert sample_scan_diff_result.new_scan_id == 2
        assert len(sample_scan_diff_result.changes) == 1
        assert sample_scan_diff_result.changes[0].ticker == "AAPL"
        assert sample_scan_diff_result.new_entries == ["NVDA"]
        assert sample_scan_diff_result.removed_entries == ["INTC"]
        assert sample_scan_diff_result.created_at == datetime(2026, 2, 1, 8, 0, 0, tzinfo=UTC)

    def test_frozen_enforcement(self, sample_scan_diff_result: ScanDiffResult) -> None:
        """ScanDiffResult is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_scan_diff_result.old_scan_id = 99  # type: ignore[misc]

    def test_empty_changes_list(self) -> None:
        """ScanDiffResult accepts an empty changes list."""
        diff = ScanDiffResult(
            old_scan_id=1,
            new_scan_id=2,
            changes=[],
            new_entries=[],
            removed_entries=[],
            created_at=datetime(2026, 2, 1, 8, 0, 0, tzinfo=UTC),
        )
        assert diff.changes == []

    def test_naive_created_at_raises(self) -> None:
        """ScanDiffResult rejects naive datetime for created_at."""
        with pytest.raises(ValidationError, match="UTC"):
            ScanDiffResult(
                old_scan_id=1,
                new_scan_id=2,
                changes=[],
                new_entries=[],
                removed_entries=[],
                created_at=datetime(2026, 2, 1, 8, 0, 0),  # naive
            )

    def test_json_roundtrip(self, sample_scan_diff_result: ScanDiffResult) -> None:
        """ScanDiffResult survives JSON roundtrip."""
        json_str = sample_scan_diff_result.model_dump_json()
        restored = ScanDiffResult.model_validate_json(json_str)
        assert restored == sample_scan_diff_result


# ---------------------------------------------------------------------------
# DebateTrendPoint Tests
# ---------------------------------------------------------------------------


class TestDebateTrendPoint:
    """Tests for the DebateTrendPoint model."""

    def test_happy_path_construction(self, sample_debate_trend_point: DebateTrendPoint) -> None:
        """DebateTrendPoint constructs with all fields correctly assigned."""
        assert sample_debate_trend_point.ticker == "AAPL"
        assert sample_debate_trend_point.direction == SignalDirection.BULLISH
        assert sample_debate_trend_point.confidence == pytest.approx(0.75)
        assert sample_debate_trend_point.is_fallback is False
        assert sample_debate_trend_point.created_at == datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC)

    def test_frozen_enforcement(self, sample_debate_trend_point: DebateTrendPoint) -> None:
        """DebateTrendPoint is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_debate_trend_point.confidence = 0.5  # type: ignore[misc]

    def test_confidence_lower_bound(self) -> None:
        """DebateTrendPoint accepts confidence of 0.0."""
        point = DebateTrendPoint(
            ticker="AAPL",
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            is_fallback=True,
            created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
        )
        assert point.confidence == pytest.approx(0.0)

    def test_confidence_upper_bound(self) -> None:
        """DebateTrendPoint accepts confidence of 1.0."""
        point = DebateTrendPoint(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            is_fallback=False,
            created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
        )
        assert point.confidence == pytest.approx(1.0)

    def test_confidence_rejects_negative(self) -> None:
        """DebateTrendPoint rejects negative confidence."""
        with pytest.raises(ValidationError, match="confidence must be in"):
            DebateTrendPoint(
                ticker="AAPL",
                direction=SignalDirection.BEARISH,
                confidence=-0.1,
                is_fallback=False,
                created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
            )

    def test_confidence_rejects_above_one(self) -> None:
        """DebateTrendPoint rejects confidence above 1.0."""
        with pytest.raises(ValidationError, match="confidence must be in"):
            DebateTrendPoint(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=1.1,
                is_fallback=False,
                created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
            )

    def test_confidence_rejects_nan(self) -> None:
        """DebateTrendPoint rejects NaN for confidence."""
        with pytest.raises(ValidationError, match="finite"):
            DebateTrendPoint(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=float("nan"),
                is_fallback=False,
                created_at=datetime(2026, 2, 1, 14, 30, 0, tzinfo=UTC),
            )

    def test_naive_created_at_raises(self) -> None:
        """DebateTrendPoint rejects naive datetime for created_at."""
        with pytest.raises(ValidationError, match="UTC"):
            DebateTrendPoint(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.75,
                is_fallback=False,
                created_at=datetime(2026, 2, 1, 14, 30, 0),  # naive
            )

    def test_json_roundtrip(self, sample_debate_trend_point: DebateTrendPoint) -> None:
        """DebateTrendPoint survives JSON roundtrip."""
        json_str = sample_debate_trend_point.model_dump_json()
        restored = DebateTrendPoint.model_validate_json(json_str)
        assert restored == sample_debate_trend_point
