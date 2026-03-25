"""Tests for GET /api/analytics/recommendation-costs endpoint (#813).

Covers:
  - Returns list of RecommendationCostDetailResponse
  - Returns empty list when no cost records exist
  - Response schema matches TypeScript interface expectations
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.data import RecommendationRow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recommendation_row(
    *,
    ticker: str = "AAPL",
    total_input_tokens: int = 1500,
    total_output_tokens: int = 500,
    duration_ms: int = 3200,
    is_fallback: bool = False,
    desk_metrics: list[dict[str, object]] | None = None,
) -> RecommendationRow:
    """Build a minimal RecommendationRow for cost endpoint testing."""
    if desk_metrics is None:
        desk_metrics = [
            {
                "desk": "trend",
                "status": "success",
                "duration_ms": 800,
                "model_tier": "fast",
                "model_used": "llama-3.3-70b",
                "input_tokens": 400,
                "output_tokens": 100,
            },
            {
                "desk": "volatility",
                "status": "success",
                "duration_ms": 900,
                "model_tier": "standard",
                "model_used": "llama-3.3-70b",
                "input_tokens": 500,
                "output_tokens": 150,
            },
        ]

    return RecommendationRow(
        id=1,
        ticker=ticker,
        scan_run_id=None,
        direction="bullish",
        confidence=0.75,
        recommended_contract="AAPL 190C 2026-04-18",
        entry_price="5.40",
        entry_criteria="Break above resistance",
        exit_criteria="Close below support",
        stop_loss="3.00",
        take_profit="8.00",
        position_size_pct=0.05,
        risk_reward_ratio=2.5,
        recommended_strategy=None,
        summary="Bullish outlook based on momentum",
        key_factors_json='["Strong momentum", "IV below average"]',
        risk_assessment="Moderate risk",
        agent_agreement_score=0.8,
        dissenting_desks_json="[]",
        assessments_json="[]",
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        duration_ms=duration_ms,
        is_fallback=is_fallback,
        citation_density=0.5,
        position_rationale="Momentum favors upside",
        strategy_rationale="Single leg for simplicity",
        max_loss_estimate="$540",
        model_used="llama-3.3-70b",
        desk_metrics_json=json.dumps(desk_metrics),
        created_at="2026-03-24T10:30:00+00:00",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecommendationCostsEndpoint:
    """Tests for GET /api/analytics/recommendation-costs."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_returns_cost_list(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Endpoint returns list of RecommendationCostDetailResponse."""
        row = _make_recommendation_row(
            total_input_tokens=1500,
            total_output_tokens=500,
        )
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

        item = data[0]
        assert item["ticker"] == "AAPL"
        assert item["total_tokens"] == 2000  # 1500 + 500
        assert item["duration_ms"] == 3200
        assert item["is_fallback"] is False
        assert len(item["desk_details"]) == 2

        # Verify desk detail fields
        desk = item["desk_details"][0]
        assert desk["desk"] == "trend"
        assert desk["tier"] == "fast"
        assert desk["model_used"] == "llama-3.3-70b"
        assert desk["input_tokens"] == 400
        assert desk["output_tokens"] == 100
        assert desk["duration_ms"] == 800
        assert desk["status"] == "success"

    @pytest.mark.asyncio
    async def test_empty_when_no_costs(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns empty list when no cost records exist."""
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_response_schema_matches(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Response fields match TypeScript RecommendationCostDetail interface."""
        row = _make_recommendation_row()
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        item = data[0]

        # All top-level fields expected by TypeScript interface
        expected_top_keys = {
            "ticker",
            "created_at",
            "duration_ms",
            "total_tokens",
            "is_fallback",
            "desk_details",
        }
        assert set(item.keys()) == expected_top_keys

        # All desk detail fields expected by TypeScript DeskCostDetail interface
        expected_desk_keys = {
            "desk",
            "tier",
            "model_used",
            "input_tokens",
            "output_tokens",
            "duration_ms",
            "status",
        }
        for desk in item["desk_details"]:
            assert set(desk.keys()) == expected_desk_keys

    @pytest.mark.asyncio
    async def test_handles_empty_desk_metrics(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Gracefully handles rows with empty or invalid desk_metrics_json."""
        row = _make_recommendation_row(desk_metrics=[])
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio
    async def test_limit_query_param(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify limit query param is passed to repository."""
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/recommendation-costs?limit=10")
        assert response.status_code == 200
        mock_repo.get_recent_recommendations.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_fallback_recommendation(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify is_fallback flag is correctly propagated."""
        row = _make_recommendation_row(is_fallback=True)
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["is_fallback"] is True
