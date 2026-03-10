"""Unit tests for backtesting analytics models.

Tests cover:
- Happy path construction with all required fields for each model
- Frozen enforcement (attribute reassignment raises ValidationError)
- isfinite() validators reject NaN/Inf on float fields
- JSON roundtrip (model_validate_json(m.model_dump_json()) == m)
- Range validators (win_rate bounded, counts non-negative, etc.)
"""

from datetime import date

import pytest
from pydantic import ValidationError

from options_arena.models.analytics import (
    DrawdownPoint,
    DTEBucketResult,
    EquityCurvePoint,
    GreeksDecompositionResult,
    HoldingPeriodComparison,
    IVRankBucketResult,
    SectorPerformanceResult,
)

# ---------------------------------------------------------------------------
# TestEquityCurvePoint
# ---------------------------------------------------------------------------


class TestEquityCurvePoint:
    """Tests for the EquityCurvePoint frozen model."""

    def test_construction_valid(self) -> None:
        """Verify EquityCurvePoint constructs with valid data."""
        point = EquityCurvePoint(
            date=date(2026, 3, 1),
            cumulative_return_pct=12.5,
            trade_count=25,
        )
        assert point.date == date(2026, 3, 1)
        assert point.cumulative_return_pct == pytest.approx(12.5, rel=1e-6)
        assert point.trade_count == 25

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        point = EquityCurvePoint(
            date=date(2026, 3, 1),
            cumulative_return_pct=12.5,
            trade_count=25,
        )
        with pytest.raises(ValidationError):
            point.trade_count = 30  # type: ignore[misc]

    def test_rejects_nan_cumulative_return(self) -> None:
        """Verify NaN cumulative_return_pct rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            EquityCurvePoint(
                date=date(2026, 3, 1),
                cumulative_return_pct=float("nan"),
                trade_count=25,
            )

    def test_rejects_inf_cumulative_return(self) -> None:
        """Verify Inf cumulative_return_pct rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            EquityCurvePoint(
                date=date(2026, 3, 1),
                cumulative_return_pct=float("inf"),
                trade_count=25,
            )

    def test_rejects_negative_trade_count(self) -> None:
        """Verify negative trade_count rejected."""
        with pytest.raises(ValidationError, match="trade_count"):
            EquityCurvePoint(
                date=date(2026, 3, 1),
                cumulative_return_pct=12.5,
                trade_count=-1,
            )

    def test_allows_negative_cumulative_return(self) -> None:
        """Verify negative cumulative_return_pct is valid (drawdown scenario)."""
        point = EquityCurvePoint(
            date=date(2026, 3, 1),
            cumulative_return_pct=-8.3,
            trade_count=10,
        )
        assert point.cumulative_return_pct == pytest.approx(-8.3, rel=1e-6)

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        point = EquityCurvePoint(
            date=date(2026, 3, 1),
            cumulative_return_pct=12.5,
            trade_count=25,
        )
        restored = EquityCurvePoint.model_validate_json(point.model_dump_json())
        assert restored == point


# ---------------------------------------------------------------------------
# TestDrawdownPoint
# ---------------------------------------------------------------------------


class TestDrawdownPoint:
    """Tests for the DrawdownPoint frozen model."""

    def test_construction_valid(self) -> None:
        """Verify DrawdownPoint constructs with valid data."""
        point = DrawdownPoint(
            date=date(2026, 3, 5),
            drawdown_pct=-5.2,
            peak_value=112.5,
        )
        assert point.date == date(2026, 3, 5)
        assert point.drawdown_pct == pytest.approx(-5.2, rel=1e-6)
        assert point.peak_value == pytest.approx(112.5, rel=1e-6)

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        point = DrawdownPoint(
            date=date(2026, 3, 5),
            drawdown_pct=-5.2,
            peak_value=112.5,
        )
        with pytest.raises(ValidationError):
            point.drawdown_pct = -10.0  # type: ignore[misc]

    def test_rejects_nan_drawdown(self) -> None:
        """Verify NaN drawdown_pct rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            DrawdownPoint(
                date=date(2026, 3, 5),
                drawdown_pct=float("nan"),
                peak_value=112.5,
            )

    def test_rejects_inf_peak_value(self) -> None:
        """Verify Inf peak_value rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            DrawdownPoint(
                date=date(2026, 3, 5),
                drawdown_pct=-5.2,
                peak_value=float("inf"),
            )

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        point = DrawdownPoint(
            date=date(2026, 3, 5),
            drawdown_pct=-5.2,
            peak_value=112.5,
        )
        restored = DrawdownPoint.model_validate_json(point.model_dump_json())
        assert restored == point

    def test_zero_drawdown_at_peak(self) -> None:
        """Verify 0.0 drawdown is valid (at peak)."""
        point = DrawdownPoint(
            date=date(2026, 3, 5),
            drawdown_pct=0.0,
            peak_value=100.0,
        )
        assert point.drawdown_pct == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# TestSectorPerformanceResult
# ---------------------------------------------------------------------------


class TestSectorPerformanceResult:
    """Tests for the SectorPerformanceResult frozen model."""

    def test_construction_valid(self) -> None:
        """Verify SectorPerformanceResult constructs with valid data."""
        result = SectorPerformanceResult(
            sector="Information Technology",
            total=50,
            win_rate_pct=65.0,
            avg_return_pct=8.3,
        )
        assert result.sector == "Information Technology"
        assert result.total == 50
        assert result.win_rate_pct == pytest.approx(65.0, rel=1e-6)
        assert result.avg_return_pct == pytest.approx(8.3, rel=1e-6)

    def test_rejects_nan_win_rate(self) -> None:
        """Verify NaN win_rate_pct rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            SectorPerformanceResult(
                sector="Energy",
                total=20,
                win_rate_pct=float("nan"),
                avg_return_pct=5.0,
            )

    def test_rejects_win_rate_above_100(self) -> None:
        """Verify win_rate_pct > 100.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate_pct"):
            SectorPerformanceResult(
                sector="Energy",
                total=20,
                win_rate_pct=101.0,
                avg_return_pct=5.0,
            )

    def test_rejects_negative_total(self) -> None:
        """Verify negative total rejected."""
        with pytest.raises(ValidationError, match="total"):
            SectorPerformanceResult(
                sector="Energy",
                total=-1,
                win_rate_pct=50.0,
                avg_return_pct=5.0,
            )

    def test_rejects_inf_avg_return(self) -> None:
        """Verify Inf avg_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            SectorPerformanceResult(
                sector="Energy",
                total=20,
                win_rate_pct=50.0,
                avg_return_pct=float("inf"),
            )

    def test_allows_negative_avg_return(self) -> None:
        """Verify negative avg_return_pct is valid (losing sector)."""
        result = SectorPerformanceResult(
            sector="Real Estate",
            total=15,
            win_rate_pct=30.0,
            avg_return_pct=-12.5,
        )
        assert result.avg_return_pct == pytest.approx(-12.5, rel=1e-6)


# ---------------------------------------------------------------------------
# TestDTEBucketResult
# ---------------------------------------------------------------------------


class TestDTEBucketResult:
    """Tests for the DTEBucketResult frozen model."""

    def test_construction_valid(self) -> None:
        """Verify DTEBucketResult constructs with valid data."""
        result = DTEBucketResult(
            dte_min=30,
            dte_max=45,
            total=80,
            win_rate_pct=62.5,
            avg_return_pct=9.1,
        )
        assert result.dte_min == 30
        assert result.dte_max == 45
        assert result.total == 80
        assert result.win_rate_pct == pytest.approx(62.5, rel=1e-6)

    def test_rejects_negative_dte(self) -> None:
        """Verify negative DTE bounds rejected."""
        with pytest.raises(ValidationError, match="DTE"):
            DTEBucketResult(
                dte_min=-1,
                dte_max=45,
                total=80,
                win_rate_pct=62.5,
                avg_return_pct=9.1,
            )

    def test_rejects_nan_win_rate(self) -> None:
        """Verify NaN win_rate_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            DTEBucketResult(
                dte_min=30,
                dte_max=45,
                total=80,
                win_rate_pct=float("nan"),
                avg_return_pct=9.1,
            )

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        result = DTEBucketResult(
            dte_min=30,
            dte_max=45,
            total=80,
            win_rate_pct=62.5,
            avg_return_pct=9.1,
        )
        restored = DTEBucketResult.model_validate_json(result.model_dump_json())
        assert restored == result


# ---------------------------------------------------------------------------
# TestIVRankBucketResult
# ---------------------------------------------------------------------------


class TestIVRankBucketResult:
    """Tests for the IVRankBucketResult frozen model."""

    def test_construction_valid(self) -> None:
        """Verify IVRankBucketResult constructs with valid data."""
        result = IVRankBucketResult(
            iv_min=0.0,
            iv_max=25.0,
            total=45,
            win_rate_pct=55.0,
            avg_return_pct=3.2,
        )
        assert result.iv_min == pytest.approx(0.0, abs=1e-9)
        assert result.iv_max == pytest.approx(25.0, rel=1e-6)
        assert result.total == 45

    def test_rejects_inf_iv_bounds(self) -> None:
        """Verify Inf IV bounds rejected."""
        with pytest.raises(ValidationError, match="finite"):
            IVRankBucketResult(
                iv_min=float("inf"),
                iv_max=25.0,
                total=45,
                win_rate_pct=55.0,
                avg_return_pct=3.2,
            )

    def test_rejects_nan_avg_return(self) -> None:
        """Verify NaN avg_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            IVRankBucketResult(
                iv_min=0.0,
                iv_max=25.0,
                total=45,
                win_rate_pct=55.0,
                avg_return_pct=float("nan"),
            )

    def test_rejects_win_rate_below_zero(self) -> None:
        """Verify win_rate_pct < 0.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate_pct"):
            IVRankBucketResult(
                iv_min=0.0,
                iv_max=25.0,
                total=45,
                win_rate_pct=-1.0,
                avg_return_pct=3.2,
            )

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        result = IVRankBucketResult(
            iv_min=0.0,
            iv_max=25.0,
            total=45,
            win_rate_pct=55.0,
            avg_return_pct=3.2,
        )
        restored = IVRankBucketResult.model_validate_json(result.model_dump_json())
        assert restored == result


# ---------------------------------------------------------------------------
# TestGreeksDecompositionResult
# ---------------------------------------------------------------------------


class TestGreeksDecompositionResult:
    """Tests for the GreeksDecompositionResult frozen model."""

    def test_construction_valid(self) -> None:
        """Verify GreeksDecompositionResult constructs with valid data."""
        result = GreeksDecompositionResult(
            group_key="calls",
            delta_pnl=150.0,
            residual_pnl=-30.0,
            total_pnl=120.0,
            count=40,
        )
        assert result.group_key == "calls"
        assert result.delta_pnl == pytest.approx(150.0, rel=1e-6)
        assert result.residual_pnl == pytest.approx(-30.0, rel=1e-6)
        assert result.total_pnl == pytest.approx(120.0, rel=1e-6)
        assert result.count == 40

    def test_rejects_nan_delta_pnl(self) -> None:
        """Verify NaN delta_pnl rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            GreeksDecompositionResult(
                group_key="puts",
                delta_pnl=float("nan"),
                residual_pnl=-30.0,
                total_pnl=120.0,
                count=40,
            )

    def test_rejects_inf_residual_pnl(self) -> None:
        """Verify Inf residual_pnl rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            GreeksDecompositionResult(
                group_key="puts",
                delta_pnl=150.0,
                residual_pnl=float("inf"),
                total_pnl=120.0,
                count=40,
            )

    def test_rejects_inf_total_pnl(self) -> None:
        """Verify Inf total_pnl rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            GreeksDecompositionResult(
                group_key="puts",
                delta_pnl=150.0,
                residual_pnl=-30.0,
                total_pnl=float("-inf"),
                count=40,
            )

    def test_rejects_negative_count(self) -> None:
        """Verify negative count rejected."""
        with pytest.raises(ValidationError, match="count"):
            GreeksDecompositionResult(
                group_key="puts",
                delta_pnl=150.0,
                residual_pnl=-30.0,
                total_pnl=120.0,
                count=-5,
            )

    def test_allows_negative_pnl(self) -> None:
        """Verify negative P&L values are valid (losing positions)."""
        result = GreeksDecompositionResult(
            group_key="bearish",
            delta_pnl=-200.0,
            residual_pnl=-50.0,
            total_pnl=-250.0,
            count=15,
        )
        assert result.total_pnl == pytest.approx(-250.0, rel=1e-6)

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        result = GreeksDecompositionResult(
            group_key="calls",
            delta_pnl=150.0,
            residual_pnl=-30.0,
            total_pnl=120.0,
            count=40,
        )
        restored = GreeksDecompositionResult.model_validate_json(result.model_dump_json())
        assert restored == result


# ---------------------------------------------------------------------------
# TestHoldingPeriodComparison
# ---------------------------------------------------------------------------


class TestHoldingPeriodComparison:
    """Tests for the HoldingPeriodComparison frozen model."""

    def test_construction_valid(self) -> None:
        """Verify HoldingPeriodComparison constructs with valid data."""
        result = HoldingPeriodComparison(
            holding_days=5,
            direction="bullish",
            avg_return=6.3,
            median_return=4.8,
            win_rate=0.68,
            sharpe_like=1.2,
            max_loss=-25.0,
            count=150,
        )
        assert result.holding_days == 5
        assert result.direction == "bullish"
        assert result.avg_return == pytest.approx(6.3, rel=1e-6)
        assert result.median_return == pytest.approx(4.8, rel=1e-6)
        assert result.win_rate == pytest.approx(0.68, rel=1e-6)
        assert result.sharpe_like == pytest.approx(1.2, rel=1e-6)
        assert result.max_loss == pytest.approx(-25.0, rel=1e-6)
        assert result.count == 150

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        result = HoldingPeriodComparison(
            holding_days=5,
            direction="bullish",
            avg_return=6.3,
            median_return=4.8,
            win_rate=0.68,
            sharpe_like=1.2,
            max_loss=-25.0,
            count=150,
        )
        with pytest.raises(ValidationError):
            result.win_rate = 0.9  # type: ignore[misc]

    def test_rejects_zero_holding_days(self) -> None:
        """Verify holding_days < 1 rejected."""
        with pytest.raises(ValidationError, match="holding_days"):
            HoldingPeriodComparison(
                holding_days=0,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=0.68,
                sharpe_like=1.2,
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_nan_avg_return(self) -> None:
        """Verify NaN avg_return rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=float("nan"),
                median_return=4.8,
                win_rate=0.68,
                sharpe_like=1.2,
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_inf_sharpe_like(self) -> None:
        """Verify Inf sharpe_like rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=0.68,
                sharpe_like=float("inf"),
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_inf_max_loss(self) -> None:
        """Verify -Inf max_loss rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=0.68,
                sharpe_like=1.2,
                max_loss=float("-inf"),
                count=150,
            )

    def test_rejects_win_rate_above_one(self) -> None:
        """Verify win_rate > 1.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=1.1,
                sharpe_like=1.2,
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_win_rate_below_zero(self) -> None:
        """Verify win_rate < 0.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bearish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=-0.1,
                sharpe_like=1.2,
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_nan_win_rate(self) -> None:
        """Verify NaN win_rate rejected by isfinite check."""
        with pytest.raises(ValidationError, match="finite"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=float("nan"),
                sharpe_like=1.2,
                max_loss=-25.0,
                count=150,
            )

    def test_rejects_negative_count(self) -> None:
        """Verify negative count rejected."""
        with pytest.raises(ValidationError, match="count"):
            HoldingPeriodComparison(
                holding_days=5,
                direction="bullish",
                avg_return=6.3,
                median_return=4.8,
                win_rate=0.68,
                sharpe_like=1.2,
                max_loss=-25.0,
                count=-1,
            )

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization roundtrip."""
        result = HoldingPeriodComparison(
            holding_days=10,
            direction="bearish",
            avg_return=-2.1,
            median_return=-3.5,
            win_rate=0.42,
            sharpe_like=-0.5,
            max_loss=-45.0,
            count=80,
        )
        restored = HoldingPeriodComparison.model_validate_json(result.model_dump_json())
        assert restored == result

    def test_allows_negative_sharpe(self) -> None:
        """Verify negative sharpe_like is valid (poor risk-adjusted return)."""
        result = HoldingPeriodComparison(
            holding_days=20,
            direction="neutral",
            avg_return=-1.5,
            median_return=-2.0,
            win_rate=0.35,
            sharpe_like=-0.8,
            max_loss=-60.0,
            count=30,
        )
        assert result.sharpe_like == pytest.approx(-0.8, rel=1e-6)
