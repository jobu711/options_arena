"""Tests for scan delta Pydantic models.

Covers:
  - TickerDelta model construction, frozen enforcement, finite validators
  - ScanDiff model construction, frozen enforcement, JSON roundtrip
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.models import (
    ScanDiff,
    TickerDelta,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_delta(**overrides: object) -> TickerDelta:
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_score": 85.0,
        "previous_score": 78.0,
        "score_change": 7.0,
        "current_direction": "bullish",
        "previous_direction": "bullish",
        "is_new": False,
    }
    defaults.update(overrides)
    return TickerDelta(**defaults)  # type: ignore[arg-type]


# ===================================================================
# TickerDelta model tests
# ===================================================================


class TestTickerDelta:
    """TickerDelta model construction and validation."""

    def test_construction_happy_path(self) -> None:
        """Valid TickerDelta constructs correctly."""
        delta = _make_delta()
        assert delta.ticker == "AAPL"
        assert delta.current_score == pytest.approx(85.0)
        assert delta.previous_score == pytest.approx(78.0)
        assert delta.score_change == pytest.approx(7.0)
        assert delta.current_direction == "bullish"
        assert delta.previous_direction == "bullish"
        assert delta.is_new is False

    def test_construction_new_ticker(self) -> None:
        """New ticker has is_new=True and None previous_direction."""
        delta = _make_delta(
            is_new=True,
            previous_score=0.0,
            score_change=85.0,
            previous_direction=None,
        )
        assert delta.is_new is True
        assert delta.previous_direction is None

    def test_frozen(self) -> None:
        """Frozen model rejects attribute reassignment."""
        delta = _make_delta()
        with pytest.raises(ValidationError):
            delta.score_change = 10.0  # type: ignore[misc]

    def test_rejects_nan_current_score(self) -> None:
        """NaN in current_score raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            _make_delta(current_score=float("nan"))

    def test_rejects_inf_previous_score(self) -> None:
        """Inf in previous_score raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            _make_delta(previous_score=float("inf"))

    def test_rejects_nan_score_change(self) -> None:
        """NaN in score_change raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            _make_delta(score_change=float("nan"))

    def test_rejects_negative_inf_score_change(self) -> None:
        """Negative Inf in score_change raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            _make_delta(score_change=float("-inf"))

    def test_negative_score_change(self) -> None:
        """Negative score_change is valid (score dropped)."""
        delta = _make_delta(
            current_score=70.0,
            previous_score=85.0,
            score_change=-15.0,
        )
        assert delta.score_change == pytest.approx(-15.0)

    def test_zero_score_change(self) -> None:
        """Zero score_change is valid (no change)."""
        delta = _make_delta(
            current_score=80.0,
            previous_score=80.0,
            score_change=0.0,
        )
        assert delta.score_change == pytest.approx(0.0)

    def test_json_roundtrip(self) -> None:
        """JSON serialization roundtrip preserves all fields."""
        delta = _make_delta()
        roundtripped = TickerDelta.model_validate_json(delta.model_dump_json())
        assert roundtripped == delta

    def test_direction_change(self) -> None:
        """Ticker with direction change constructs correctly."""
        delta = _make_delta(
            current_direction="bearish",
            previous_direction="bullish",
        )
        assert delta.current_direction == "bearish"
        assert delta.previous_direction == "bullish"


# ===================================================================
# ScanDiff model tests
# ===================================================================


class TestScanDiff:
    """ScanDiff model construction and validation."""

    def test_construction_happy_path(self) -> None:
        """Valid ScanDiff constructs correctly."""
        diff = ScanDiff(
            current_scan_id=2,
            base_scan_id=1,
            added=["NVDA", "TSLA"],
            removed=["GE"],
            movers=[_make_delta()],
        )
        assert diff.current_scan_id == 2
        assert diff.base_scan_id == 1
        assert diff.added == ["NVDA", "TSLA"]
        assert diff.removed == ["GE"]
        assert len(diff.movers) == 1

    def test_frozen(self) -> None:
        """Frozen model rejects attribute reassignment."""
        diff = ScanDiff(
            current_scan_id=2,
            base_scan_id=1,
            added=[],
            removed=[],
            movers=[],
        )
        with pytest.raises(ValidationError):
            diff.current_scan_id = 3  # type: ignore[misc]

    def test_empty_diff(self) -> None:
        """Empty diff (identical scans) constructs correctly."""
        diff = ScanDiff(
            current_scan_id=2,
            base_scan_id=1,
            added=[],
            removed=[],
            movers=[],
        )
        assert len(diff.added) == 0
        assert len(diff.removed) == 0
        assert len(diff.movers) == 0

    def test_json_roundtrip(self) -> None:
        """JSON serialization roundtrip preserves all fields."""
        diff = ScanDiff(
            current_scan_id=2,
            base_scan_id=1,
            added=["NVDA"],
            removed=["GE"],
            movers=[_make_delta(), _make_delta(ticker="MSFT", score_change=-3.0)],
        )
        roundtripped = ScanDiff.model_validate_json(diff.model_dump_json())
        assert roundtripped == diff

    def test_multiple_movers(self) -> None:
        """ScanDiff with multiple movers stores all correctly."""
        movers = [
            _make_delta(ticker="AAPL", score_change=7.0),
            _make_delta(ticker="MSFT", score_change=-5.0),
            _make_delta(ticker="GOOGL", score_change=2.0),
        ]
        diff = ScanDiff(
            current_scan_id=3,
            base_scan_id=2,
            added=[],
            removed=[],
            movers=movers,
        )
        assert len(diff.movers) == 3
