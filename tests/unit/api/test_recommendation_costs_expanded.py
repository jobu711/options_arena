"""Tests for expanded recommendation costs endpoint with desk_details — #698."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@dataclass
class _FakeRecommendationRow:
    """Minimal fake RecommendationRow for cost endpoint tests."""

    id: int
    ticker: str
    created_at: str
    duration_ms: int
    total_input_tokens: int
    total_output_tokens: int
    is_fallback: bool
    desk_metrics_json: str


def _make_row(
    *,
    ticker: str = "AAPL",
    desk_metrics_json: str = "[]",
) -> _FakeRecommendationRow:
    """Create a fake recommendation row."""
    return _FakeRecommendationRow(
        id=1,
        ticker=ticker,
        created_at="2026-03-22T12:00:00+00:00",
        duration_ms=5000,
        total_input_tokens=3000,
        total_output_tokens=2000,
        is_fallback=False,
        desk_metrics_json=desk_metrics_json,
    )


class TestRecommendationCostsExpanded:
    """GET /api/analytics/recommendation-costs — desk_details expansion."""

    @pytest.mark.asyncio()
    async def test_desk_details_populated(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint returns desk_details from stored desk_metrics_json."""
        metrics = [
            {
                "desk": "trend",
                "model_tier": "STANDARD",
                "model_used": "llama-3.3-70b-versatile",
                "input_tokens": 1500,
                "output_tokens": 800,
                "duration_ms": 2400,
                "status": "SUCCESS",
            },
            {
                "desk": "risk",
                "model_tier": "PREMIUM",
                "model_used": "llama-3.3-70b-versatile",
                "input_tokens": 2000,
                "output_tokens": 1000,
                "duration_ms": 3100,
                "status": "SUCCESS",
            },
        ]
        row = _make_row(desk_metrics_json=json.dumps(metrics))
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert len(data[0]["desk_details"]) == 2
        assert data[0]["desk_details"][0]["desk"] == "trend"
        assert data[0]["desk_details"][0]["tier"] == "STANDARD"
        assert data[0]["desk_details"][0]["input_tokens"] == 1500
        assert data[0]["desk_details"][1]["desk"] == "risk"
        assert data[0]["desk_details"][1]["tier"] == "PREMIUM"
        assert data[0]["desk_details"][1]["duration_ms"] == 3100

    @pytest.mark.asyncio()
    async def test_desk_details_empty_for_legacy_data(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint returns empty desk_details for pre-migration rows."""
        row = _make_row(desk_metrics_json="[]")
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio()
    async def test_desk_details_empty_string(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint handles empty-string desk_metrics_json gracefully."""
        row = _make_row(desk_metrics_json="")
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio()
    async def test_desk_details_fields_match_schema(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Verify desk_details items have all DeskCostDetail fields."""
        metrics = [
            {
                "desk": "volatility",
                "model_tier": "FAST",
                "model_used": "llama-3.1-8b-instant",
                "input_tokens": 500,
                "output_tokens": 200,
                "duration_ms": 800,
                "status": "SUCCESS",
            },
        ]
        row = _make_row(desk_metrics_json=json.dumps(metrics))
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        detail = response.json()[0]["desk_details"][0]
        expected_fields = {
            "desk", "tier", "model_used", "input_tokens",
            "output_tokens", "duration_ms", "status",
        }
        assert set(detail.keys()) == expected_fields

    @pytest.mark.asyncio()
    async def test_no_recommendations_empty_list(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint with no recommendations returns empty list."""
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio()
    async def test_malformed_desk_metrics_json(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint handles malformed desk_metrics_json gracefully."""
        row = _make_row(desk_metrics_json="not valid json")
        mock_repo.get_recent_recommendations = AsyncMock(return_value=[row])

        response = await client.get("/api/analytics/recommendation-costs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio()
    async def test_ticker_filter_passes_through(
        self, client: AsyncClient, mock_repo: AsyncMock
    ) -> None:
        """Cost endpoint with ticker filter uses get_recommendations_for_ticker."""
        mock_repo.get_recommendations_for_ticker = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/recommendation-costs?ticker=AAPL")
        assert response.status_code == 200
        mock_repo.get_recommendations_for_ticker.assert_awaited_once_with("AAPL", limit=20)
