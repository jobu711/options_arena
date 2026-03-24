"""Tests for the attribution API endpoint.

Covers: GET /api/analytics/attribution returns 200 with AttributionReport,
window_days parameter validation, and source filter parameter.

Uses ``httpx.AsyncClient`` with mocked dependencies (conftest fixtures).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models.attribution import (
    Prediction,
    PredictionSource,
)
from options_arena.models.enums import SignalDirection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_predictions(
    *,
    sources: list[PredictionSource] | None = None,
) -> list[Prediction]:
    """Build sample scored predictions for tests."""
    if sources is None:
        sources = [PredictionSource.DESK_TREND, PredictionSource.SYNTHESIS]

    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)
    result: list[Prediction] = []
    for idx, src in enumerate(sources):
        result.append(
            Prediction(
                id=idx + 1,
                recommendation_id=1,
                ticker="AAPL",
                source=src,
                predicted_direction=SignalDirection.BULLISH,
                confidence=0.8,
                adx=25.0,
                iv_rank=45.0,
                atr_pct=2.0,
                rsi=55.0,
                was_correct=idx % 2 == 0,
                created_at=now,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAttributionEndpoint:
    """Tests for GET /api/analytics/attribution."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_returns_attribution_report(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """GET /api/analytics/attribution returns 200 with AttributionReport shape."""
        mock_repo.get_predictions = AsyncMock(return_value=_sample_predictions())
        response = await client.get("/api/analytics/attribution")
        assert response.status_code == 200
        data = response.json()
        assert "source_accuracy" in data
        assert "condition_accuracy" in data
        assert "total_recommendations" in data
        assert "total_outcomes" in data
        assert "window_days" in data
        assert len(data["source_accuracy"]) == 2

    @pytest.mark.asyncio
    async def test_window_days_default(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Default window_days=90 is forwarded to get_predictions."""
        mock_repo.get_predictions = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/attribution")
        assert response.status_code == 200
        mock_repo.get_predictions.assert_awaited_once_with(90, None)

    @pytest.mark.asyncio
    async def test_window_days_param(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """?window_days=30 accepted, ?window_days=3 rejected (min 7)."""
        mock_repo.get_predictions = AsyncMock(return_value=[])

        # Valid
        response = await client.get("/api/analytics/attribution?window_days=30")
        assert response.status_code == 200
        mock_repo.get_predictions.assert_awaited_once_with(30, None)

        # Invalid (below minimum)
        response = await client.get("/api/analytics/attribution?window_days=3")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_window_days_max(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """?window_days=365 accepted, ?window_days=400 rejected (max 365)."""
        mock_repo.get_predictions = AsyncMock(return_value=[])

        # Valid
        response = await client.get("/api/analytics/attribution?window_days=365")
        assert response.status_code == 200

        # Invalid (above maximum)
        response = await client.get("/api/analytics/attribution?window_days=400")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_source_filter_param(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """?source=desk_trend filters to one source."""
        filtered = _sample_predictions(sources=[PredictionSource.DESK_TREND])
        mock_repo.get_predictions = AsyncMock(return_value=filtered)

        response = await client.get("/api/analytics/attribution?source=desk_trend")
        assert response.status_code == 200
        mock_repo.get_predictions.assert_awaited_once_with(90, PredictionSource.DESK_TREND)
        data = response.json()
        assert len(data["source_accuracy"]) == 1
        assert data["source_accuracy"][0]["source"] == "desk_trend"

    @pytest.mark.asyncio
    async def test_invalid_source_returns_422(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Invalid source string returns 422."""
        response = await client.get("/api/analytics/attribution?source=not_a_source")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_predictions_returns_valid_report(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Empty predictions returns valid AttributionReport with empty lists."""
        mock_repo.get_predictions = AsyncMock(return_value=[])
        response = await client.get("/api/analytics/attribution")
        assert response.status_code == 200
        data = response.json()
        assert data["source_accuracy"] == []
        assert data["condition_accuracy"] == []
        assert data["total_recommendations"] == 0
        assert data["total_outcomes"] == 0
