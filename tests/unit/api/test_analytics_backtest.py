"""Tests for backtesting analytics API routes.

Covers all 7 endpoints in ``api/routes/backtest.py``:
  - GET /api/analytics/backtest/equity-curve
  - GET /api/analytics/backtest/drawdown
  - GET /api/analytics/backtest/sector-performance
  - GET /api/analytics/backtest/dte-performance
  - GET /api/analytics/backtest/iv-performance
  - GET /api/analytics/backtest/greeks-decomposition
  - GET /api/analytics/backtest/holding-comparison

Uses FastAPI TestClient with mocked dependencies (conftest fixtures).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import (
    DrawdownPoint,
    DTEBucketResult,
    EquityCurvePoint,
    GreeksDecompositionResult,
    HoldingPeriodComparison,
    IVRankBucketResult,
    SectorPerformanceResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_equity_point() -> EquityCurvePoint:
    return EquityCurvePoint(
        date=date(2026, 3, 1),
        cumulative_return_pct=5.2,
        trade_count=10,
    )


def _make_drawdown_point() -> DrawdownPoint:
    return DrawdownPoint(
        date=date(2026, 3, 5),
        drawdown_pct=-3.1,
        peak_value=105.2,
    )


def _make_sector_result() -> SectorPerformanceResult:
    return SectorPerformanceResult(
        sector="Information Technology",
        total=25,
        win_rate_pct=68.0,
        avg_return_pct=12.5,
    )


def _make_dte_result() -> DTEBucketResult:
    return DTEBucketResult(
        dte_min=30,
        dte_max=60,
        total=15,
        win_rate_pct=73.3,
        avg_return_pct=9.8,
    )


def _make_iv_result() -> IVRankBucketResult:
    return IVRankBucketResult(
        iv_min=25.0,
        iv_max=50.0,
        total=20,
        win_rate_pct=65.0,
        avg_return_pct=7.2,
    )


def _make_greeks_result() -> GreeksDecompositionResult:
    return GreeksDecompositionResult(
        group_key="bullish",
        delta_pnl=8.5,
        residual_pnl=2.3,
        total_pnl=10.8,
        count=12,
    )


def _make_holding_comparison() -> HoldingPeriodComparison:
    return HoldingPeriodComparison(
        holding_days=5,
        direction="bullish",
        avg_return=10.5,
        median_return=8.0,
        win_rate=0.65,
        sharpe_like=1.2,
        max_loss=-15.0,
        count=30,
    )


# ---------------------------------------------------------------------------
# Tests — Equity Curve
# ---------------------------------------------------------------------------


class TestEquityCurve:
    """Tests for GET /api/analytics/backtest/equity-curve."""

    @pytest.mark.asyncio
    async def test_equity_curve_empty(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/equity-curve")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_equity_curve_with_data(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_equity_curve = AsyncMock(return_value=[_make_equity_point()])
        response = await client.get("/api/analytics/backtest/equity-curve")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["date"] == "2026-03-01"
        assert data[0]["cumulative_return_pct"] == pytest.approx(5.2)
        assert data[0]["trade_count"] == 10

    @pytest.mark.asyncio
    async def test_equity_curve_direction_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify direction query param passes to repository."""
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/equity-curve?direction=bullish")
        assert response.status_code == 200
        mock_repo.get_equity_curve.assert_called_once_with(direction="bullish", period_days=None)

    @pytest.mark.asyncio
    async def test_equity_curve_period_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify period query param passes to repository."""
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/equity-curve?period=30")
        assert response.status_code == 200
        mock_repo.get_equity_curve.assert_called_once_with(direction=None, period_days=30)


# ---------------------------------------------------------------------------
# Tests — Drawdown
# ---------------------------------------------------------------------------


class TestDrawdown:
    """Tests for GET /api/analytics/backtest/drawdown."""

    @pytest.mark.asyncio
    async def test_drawdown_empty(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_drawdown_series = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/drawdown")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_drawdown_with_data(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_drawdown_series = AsyncMock(return_value=[_make_drawdown_point()])
        response = await client.get("/api/analytics/backtest/drawdown")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["date"] == "2026-03-05"
        assert data[0]["drawdown_pct"] == pytest.approx(-3.1)
        assert data[0]["peak_value"] == pytest.approx(105.2)

    @pytest.mark.asyncio
    async def test_drawdown_period_param(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify period query param passes to repository."""
        mock_repo.get_drawdown_series = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/drawdown?period=60")
        assert response.status_code == 200
        mock_repo.get_drawdown_series.assert_called_once_with(period_days=60)


# ---------------------------------------------------------------------------
# Tests — Sector Performance
# ---------------------------------------------------------------------------


class TestSectorPerformance:
    """Tests for GET /api/analytics/backtest/sector-performance."""

    @pytest.mark.asyncio
    async def test_sector_performance_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_win_rate_by_sector = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/sector-performance")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_sector_performance_with_data(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_win_rate_by_sector = AsyncMock(return_value=[_make_sector_result()])
        response = await client.get("/api/analytics/backtest/sector-performance")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sector"] == "Information Technology"
        assert data[0]["win_rate_pct"] == pytest.approx(68.0)
        assert data[0]["avg_return_pct"] == pytest.approx(12.5)

    @pytest.mark.asyncio
    async def test_sector_performance_holding_days_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify holding_days query param passes to repository."""
        mock_repo.get_win_rate_by_sector = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/sector-performance?holding_days=5")
        assert response.status_code == 200
        mock_repo.get_win_rate_by_sector.assert_called_once_with(holding_days=5)


# ---------------------------------------------------------------------------
# Tests — DTE Performance
# ---------------------------------------------------------------------------


class TestDTEPerformance:
    """Tests for GET /api/analytics/backtest/dte-performance."""

    @pytest.mark.asyncio
    async def test_dte_performance_empty(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_win_rate_by_dte_bucket = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/dte-performance")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_dte_performance_with_data(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_win_rate_by_dte_bucket = AsyncMock(return_value=[_make_dte_result()])
        response = await client.get("/api/analytics/backtest/dte-performance")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["dte_min"] == 30
        assert data[0]["dte_max"] == 60
        assert data[0]["win_rate_pct"] == pytest.approx(73.3)

    @pytest.mark.asyncio
    async def test_dte_performance_holding_days_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify holding_days query param passes to repository."""
        mock_repo.get_win_rate_by_dte_bucket = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/dte-performance?holding_days=10")
        assert response.status_code == 200
        mock_repo.get_win_rate_by_dte_bucket.assert_called_once_with(holding_days=10)


# ---------------------------------------------------------------------------
# Tests — IV Performance
# ---------------------------------------------------------------------------


class TestIVPerformance:
    """Tests for GET /api/analytics/backtest/iv-performance."""

    @pytest.mark.asyncio
    async def test_iv_performance_empty(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_win_rate_by_iv_rank = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/iv-performance")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_iv_performance_with_data(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_win_rate_by_iv_rank = AsyncMock(return_value=[_make_iv_result()])
        response = await client.get("/api/analytics/backtest/iv-performance")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["iv_min"] == pytest.approx(25.0)
        assert data[0]["iv_max"] == pytest.approx(50.0)
        assert data[0]["win_rate_pct"] == pytest.approx(65.0)

    @pytest.mark.asyncio
    async def test_iv_performance_holding_days_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify holding_days query param passes to repository."""
        mock_repo.get_win_rate_by_iv_rank = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/iv-performance?holding_days=1")
        assert response.status_code == 200
        mock_repo.get_win_rate_by_iv_rank.assert_called_once_with(holding_days=1)


# ---------------------------------------------------------------------------
# Tests — Greeks Decomposition
# ---------------------------------------------------------------------------


class TestGreeksDecomposition:
    """Tests for GET /api/analytics/backtest/greeks-decomposition."""

    @pytest.mark.asyncio
    async def test_greeks_decomposition_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_greeks_decomposition = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/greeks-decomposition")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_greeks_decomposition_with_data(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_greeks_decomposition = AsyncMock(return_value=[_make_greeks_result()])
        response = await client.get("/api/analytics/backtest/greeks-decomposition")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["group_key"] == "bullish"
        assert data[0]["delta_pnl"] == pytest.approx(8.5)
        assert data[0]["residual_pnl"] == pytest.approx(2.3)
        assert data[0]["total_pnl"] == pytest.approx(10.8)
        assert data[0]["count"] == 12

    @pytest.mark.asyncio
    async def test_greeks_decomposition_groupby_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify groupby query param passes to repository."""
        mock_repo.get_greeks_decomposition = AsyncMock(return_value=[])
        response = await client.get(
            "/api/analytics/backtest/greeks-decomposition?groupby=option_type"
        )
        assert response.status_code == 200
        mock_repo.get_greeks_decomposition.assert_called_once_with(
            holding_days=20, groupby="option_type"
        )

    @pytest.mark.asyncio
    async def test_greeks_decomposition_holding_days_param(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify holding_days query param passes to repository."""
        mock_repo.get_greeks_decomposition = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/greeks-decomposition?holding_days=5")
        assert response.status_code == 200
        mock_repo.get_greeks_decomposition.assert_called_once_with(
            holding_days=5, groupby="direction"
        )


# ---------------------------------------------------------------------------
# Tests — Holding Comparison
# ---------------------------------------------------------------------------


class TestHoldingComparison:
    """Tests for GET /api/analytics/backtest/holding-comparison."""

    @pytest.mark.asyncio
    async def test_holding_comparison_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty response returns 200 with []."""
        mock_repo.get_holding_period_comparison = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/backtest/holding-comparison")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_holding_comparison_with_data(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify response with data returns correct shape."""
        mock_repo.get_holding_period_comparison = AsyncMock(
            return_value=[_make_holding_comparison()]
        )
        response = await client.get("/api/analytics/backtest/holding-comparison")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["holding_days"] == 5
        assert data[0]["direction"] == "bullish"
        assert data[0]["avg_return"] == pytest.approx(10.5)
        assert data[0]["median_return"] == pytest.approx(8.0)
        assert data[0]["win_rate"] == pytest.approx(0.65)
        assert data[0]["sharpe_like"] == pytest.approx(1.2)
        assert data[0]["max_loss"] == pytest.approx(-15.0)
        assert data[0]["count"] == 30


# ---------------------------------------------------------------------------
# Tests — Validation
# ---------------------------------------------------------------------------


class TestBacktestValidation:
    """Tests for query parameter validation on backtest endpoints."""

    @pytest.mark.asyncio
    async def test_period_rejects_zero(self, client: AsyncClient) -> None:
        """Verify period=0 returns 422."""
        response = await client.get("/api/analytics/backtest/equity-curve?period=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_holding_days_rejects_zero(self, client: AsyncClient) -> None:
        """Verify holding_days=0 returns 422."""
        response = await client.get("/api/analytics/backtest/sector-performance?holding_days=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_period_rejects_negative(self, client: AsyncClient) -> None:
        """Verify negative period returns 422."""
        response = await client.get("/api/analytics/backtest/drawdown?period=-5")
        assert response.status_code == 422
