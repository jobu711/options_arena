"""Tests for analytics API routes.

Covers all 9 endpoints in ``api/routes/analytics.py``:
  - GET /api/analytics/win-rate
  - GET /api/analytics/score-calibration
  - GET /api/analytics/indicator-attribution/{indicator}
  - GET /api/analytics/holding-period
  - GET /api/analytics/delta-performance
  - GET /api/analytics/summary
  - POST /api/analytics/collect-outcomes
  - GET /api/analytics/scan/{scan_id}/contracts
  - GET /api/analytics/ticker/{ticker}/contracts

Uses FastAPI TestClient with mocked dependencies (conftest fixtures).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.api.deps import get_outcome_collector
from options_arena.models import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentWeightsComparison,
    CalibrationBucket,
    DeltaPerformanceResult,
    ExerciseStyle,
    GreeksSource,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    OptionType,
    PerformanceSummary,
    PricingModel,
    RecommendedContract,
    ScoreCalibrationBucket,
    SignalDirection,
    WinRateResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_win_rate() -> WinRateResult:
    return WinRateResult(
        direction=SignalDirection.BULLISH,
        total_contracts=10,
        winners=7,
        losers=3,
        win_rate=0.7,
    )


def _make_score_bucket() -> ScoreCalibrationBucket:
    return ScoreCalibrationBucket(
        score_min=70.0,
        score_max=80.0,
        contract_count=5,
        avg_return_pct=12.5,
        win_rate=0.8,
    )


def _make_indicator_result() -> IndicatorAttributionResult:
    return IndicatorAttributionResult(
        indicator_name="rsi",
        holding_days=5,
        correlation=0.42,
        avg_return_when_high=15.0,
        avg_return_when_low=-3.0,
        sample_size=50,
    )


def _make_holding_period() -> HoldingPeriodResult:
    return HoldingPeriodResult(
        holding_days=5,
        direction=SignalDirection.BULLISH,
        avg_return_pct=10.5,
        median_return_pct=8.0,
        win_rate=0.65,
        sample_size=20,
    )


def _make_delta_perf() -> DeltaPerformanceResult:
    return DeltaPerformanceResult(
        delta_min=0.3,
        delta_max=0.4,
        holding_days=5,
        avg_return_pct=11.0,
        win_rate=0.7,
        sample_size=15,
    )


def _make_summary() -> PerformanceSummary:
    return PerformanceSummary(
        lookback_days=30,
        total_contracts=100,
        total_with_outcomes=80,
        overall_win_rate=0.6,
        avg_stock_return_pct=2.5,
        avg_contract_return_pct=8.0,
        best_direction=SignalDirection.BULLISH,
        best_holding_days=5,
    )


def _make_contract() -> RecommendedContract:
    return RecommendedContract(
        id=1,
        scan_run_id=1,
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.50"),
        expiration=date(2026, 4, 15),
        bid=Decimal("5.20"),
        ask=Decimal("5.60"),
        volume=1200,
        open_interest=5000,
        market_iv=0.32,
        exercise_style=ExerciseStyle.AMERICAN,
        delta=0.45,
        gamma=0.03,
        theta=-0.12,
        vega=0.15,
        rho=0.02,
        pricing_model=PricingModel.BAW,
        greeks_source=GreeksSource.COMPUTED,
        entry_stock_price=Decimal("182.30"),
        entry_mid=Decimal("5.40"),
        direction=SignalDirection.BULLISH,
        composite_score=78.5,
        risk_free_rate=0.045,
        created_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyticsRoutes:
    """Tests for analytics API endpoints."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_win_rate(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/win-rate returns 200 with list."""
        mock_repo.get_win_rate_by_direction = AsyncMock(return_value=[_make_win_rate()])
        response = await client.get("/api/analytics/win-rate")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["direction"] == "bullish"
        assert data[0]["win_rate"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_get_score_calibration(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/score-calibration returns 200."""
        mock_repo.get_score_calibration = AsyncMock(return_value=[_make_score_bucket()])
        response = await client.get("/api/analytics/score-calibration")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["score_min"] == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_get_score_calibration_custom_bucket(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify bucket_size query param works."""
        mock_repo.get_score_calibration = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/score-calibration?bucket_size=5")
        assert response.status_code == 200
        mock_repo.get_score_calibration.assert_called_once_with(bucket_size=5.0)

    @pytest.mark.asyncio
    async def test_get_indicator_attribution(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify GET /api/analytics/indicator-attribution/{indicator} returns 200."""
        mock_repo.get_indicator_attribution = AsyncMock(return_value=[_make_indicator_result()])
        response = await client.get("/api/analytics/indicator-attribution/rsi")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["indicator_name"] == "rsi"
        assert data[0]["correlation"] == pytest.approx(0.42)

    @pytest.mark.asyncio
    async def test_get_holding_period(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/holding-period returns 200."""
        mock_repo.get_optimal_holding_period = AsyncMock(return_value=[_make_holding_period()])
        response = await client.get("/api/analytics/holding-period")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["holding_days"] == 5

    @pytest.mark.asyncio
    async def test_get_holding_period_with_direction(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify direction query param filters results."""
        mock_repo.get_optimal_holding_period = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/holding-period?direction=bullish")
        assert response.status_code == 200
        mock_repo.get_optimal_holding_period.assert_called_once_with(
            direction=SignalDirection.BULLISH
        )

    @pytest.mark.asyncio
    async def test_get_delta_performance(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/delta-performance returns 200."""
        mock_repo.get_delta_performance = AsyncMock(return_value=[_make_delta_perf()])
        response = await client.get("/api/analytics/delta-performance")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["delta_min"] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_get_summary(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/summary returns 200."""
        mock_repo.get_performance_summary = AsyncMock(return_value=_make_summary())
        response = await client.get("/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_contracts"] == 100
        assert data["overall_win_rate"] == pytest.approx(0.6)
        assert data["best_direction"] == "bullish"

    @pytest.mark.asyncio
    async def test_post_collect_outcomes(self, client: AsyncClient, test_app: object) -> None:
        """Verify POST /api/analytics/collect-outcomes triggers collection."""
        mock_collector = MagicMock()
        mock_collector.collect_outcomes = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_outcome_collector] = lambda: mock_collector  # type: ignore[union-attr]

        response = await client.post("/api/analytics/collect-outcomes")
        assert response.status_code == 202
        data = response.json()
        assert data["outcomes_collected"] == 0
        mock_collector.collect_outcomes.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_scan_contracts(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/scan/{id}/contracts returns contracts."""
        mock_repo.get_contracts_for_scan = AsyncMock(return_value=[_make_contract()])
        response = await client.get("/api/analytics/scan/1/contracts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_scan_contracts_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty list for scan with no contracts."""
        mock_repo.get_contracts_for_scan = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/scan/999/contracts")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_ticker_contracts(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/ticker/{ticker}/contracts returns contracts."""
        mock_repo.get_contracts_for_ticker = AsyncMock(return_value=[_make_contract()])
        response = await client.get("/api/analytics/ticker/AAPL/contracts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_invalid_bucket_size(self, client: AsyncClient) -> None:
        """Verify bucket_size < 1 returns 422."""
        response = await client.get("/api/analytics/score-calibration?bucket_size=0.5")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Agent Calibration Endpoint Tests
# ---------------------------------------------------------------------------


def _make_accuracy_report() -> AgentAccuracyReport:
    return AgentAccuracyReport(
        agent_name="trend",
        direction_hit_rate=0.75,
        mean_confidence=0.70,
        brier_score=0.18,
        sample_size=50,
    )


def _make_calibration_data() -> AgentCalibrationData:
    return AgentCalibrationData(
        agent_name=None,
        buckets=[
            CalibrationBucket(
                bucket_label="0.6-0.8",
                bucket_low=0.6,
                bucket_high=0.8,
                mean_confidence=0.7,
                actual_hit_rate=0.65,
                count=20,
            ),
        ],
        sample_size=20,
    )


def _make_weights_comparison() -> AgentWeightsComparison:
    return AgentWeightsComparison(
        agent_name="trend",
        manual_weight=0.25,
        auto_weight=0.22,
        brier_score=0.18,
        sample_size=50,
    )


class TestAgentCalibrationRoutes:
    """Tests for agent calibration API endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_accuracy(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/agent-accuracy returns 200 with list."""
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[_make_accuracy_report()])
        response = await client.get("/api/analytics/agent-accuracy")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_name"] == "trend"
        assert data[0]["direction_hit_rate"] == pytest.approx(0.75)
        assert data[0]["brier_score"] == pytest.approx(0.18)

    @pytest.mark.asyncio
    async def test_get_agent_accuracy_with_window(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify window query param passes to repository."""
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/agent-accuracy?window=30")
        assert response.status_code == 200
        mock_repo.get_agent_accuracy.assert_called_once_with(30)

    @pytest.mark.asyncio
    async def test_get_agent_accuracy_no_window(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify no window param passes None to repository."""
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/agent-accuracy")
        assert response.status_code == 200
        mock_repo.get_agent_accuracy.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_get_agent_calibration(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/agent-calibration returns 200."""
        mock_repo.get_agent_calibration = AsyncMock(return_value=_make_calibration_data())
        response = await client.get("/api/analytics/agent-calibration")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] is None
        assert len(data["buckets"]) == 1
        assert data["buckets"][0]["bucket_label"] == "0.6-0.8"
        assert data["sample_size"] == 20

    @pytest.mark.asyncio
    async def test_get_agent_calibration_with_agent(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify agent query param passes to repository."""
        mock_repo.get_agent_calibration = AsyncMock(
            return_value=AgentCalibrationData(agent_name="trend", buckets=[], sample_size=0)
        )
        response = await client.get("/api/analytics/agent-calibration?agent=trend")
        assert response.status_code == 200
        mock_repo.get_agent_calibration.assert_called_once_with("trend")

    @pytest.mark.asyncio
    async def test_get_agent_weights(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/analytics/agent-weights returns 200 with list."""
        mock_repo.get_latest_auto_tune_weights = AsyncMock(
            return_value=[_make_weights_comparison()]
        )
        response = await client.get("/api/analytics/agent-weights")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_name"] == "trend"
        assert data[0]["manual_weight"] == pytest.approx(0.25)
        assert data[0]["auto_weight"] == pytest.approx(0.22)

    @pytest.mark.asyncio
    async def test_get_agent_weights_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty list when no auto-tune data exists."""
        mock_repo.get_latest_auto_tune_weights = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/agent-weights")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_agent_accuracy_empty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify empty list when no accuracy data exists."""
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/agent-accuracy")
        assert response.status_code == 200
        assert response.json() == []
