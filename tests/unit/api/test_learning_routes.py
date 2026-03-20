"""Tests for learning API endpoints.

Covers:
  - GET /api/learning/weights
  - GET /api/learning/weights/history
  - GET /api/learning/status
  - POST /api/learning/weights/tune
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from options_arena.models import (
    AgentWeightsComparison,
    IndicatorWeightComparison,
    WeightSnapshot,
    WeightType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vote_snapshot() -> WeightSnapshot:
    return WeightSnapshot(
        computed_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        window_days=90,
        weights=[
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.25,
                auto_weight=0.22,
                brier_score=0.18,
                sample_size=50,
            )
        ],
        weight_type=WeightType.VOTE,
    )


def _make_indicator_snapshot() -> WeightSnapshot:
    return WeightSnapshot(
        computed_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        window_days=90,
        weights=[
            AgentWeightsComparison(
                agent_name="rsi",
                manual_weight=0.065,
                auto_weight=0.08,
                brier_score=None,
                sample_size=0,
            )
        ],
        weight_type=WeightType.INDICATOR,
        accuracy_at_time=0.72,
    )


# ---------------------------------------------------------------------------
# GET /api/learning/weights
# ---------------------------------------------------------------------------


class TestGetCurrentWeights:
    """Tests for GET /api/learning/weights."""

    @pytest.mark.asyncio
    async def test_returns_both_types(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns vote + indicator snapshots."""
        mock_repo.get_weight_history = AsyncMock(
            side_effect=lambda limit, weight_type: (
                [_make_vote_snapshot()]
                if weight_type == WeightType.VOTE
                else [_make_indicator_snapshot()]
            )
        )

        response = await client.get("/api/learning/weights")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Empty DB returns empty list."""
        mock_repo.get_weight_history = AsyncMock(return_value=[])

        response = await client.get("/api/learning/weights")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/learning/weights/history
# ---------------------------------------------------------------------------


class TestGetWeightHistory:
    """Tests for GET /api/learning/weights/history."""

    @pytest.mark.asyncio
    async def test_returns_history(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns list of snapshots."""
        mock_repo.get_weight_history = AsyncMock(return_value=[_make_vote_snapshot()])

        response = await client.get("/api/learning/weights/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_weight_type_filter(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """weight_type query param filters correctly."""
        mock_repo.get_weight_history = AsyncMock(return_value=[])

        response = await client.get("/api/learning/weights/history?weight_type=indicator")

        assert response.status_code == 200
        mock_repo.get_weight_history.assert_called_once_with(
            limit=20, weight_type=WeightType.INDICATOR
        )

    @pytest.mark.asyncio
    async def test_invalid_weight_type_returns_422(self, client: AsyncClient) -> None:
        """Invalid weight_type returns 422."""
        response = await client.get("/api/learning/weights/history?weight_type=bad")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/learning/status
# ---------------------------------------------------------------------------


class TestGetLearningStatus:
    """Tests for GET /api/learning/status."""

    @pytest.mark.asyncio
    async def test_returns_status(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns LearningStatus with populated fields."""
        mock_repo.get_weight_history = AsyncMock(
            side_effect=lambda limit, weight_type: (
                [_make_vote_snapshot()]
                if weight_type == WeightType.VOTE
                else [_make_indicator_snapshot()]
            )
        )

        response = await client.get("/api/learning/status")

        assert response.status_code == 200
        data = response.json()
        assert data["vote_agent_count"] == 1
        assert data["indicator_count"] == 1
        assert data["learning_enabled"] is True

    @pytest.mark.asyncio
    async def test_empty_db_status(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Empty DB returns status with None timestamps."""
        mock_repo.get_weight_history = AsyncMock(return_value=[])

        response = await client.get("/api/learning/status")

        assert response.status_code == 200
        data = response.json()
        assert data["last_vote_tune"] is None
        assert data["last_indicator_tune"] is None
        assert data["vote_agent_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/learning/weights/tune
# ---------------------------------------------------------------------------


class TestTriggerIndicatorTune:
    """Tests for POST /api/learning/weights/tune."""

    @pytest.mark.asyncio
    @patch(
        "options_arena.api.routes.learning.auto_tune_indicator_weights",
        new_callable=AsyncMock,
    )
    async def test_trigger_success(
        self,
        mock_tune: AsyncMock,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """POST triggers tuning and returns comparisons."""
        mock_tune.return_value = [
            IndicatorWeightComparison(
                indicator_name="rsi",
                static_weight=0.065,
                tuned_weight=0.08,
                pearson_r=0.32,
                sample_count=60,
            )
        ]

        response = await client.post("/api/learning/weights/tune")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["indicator_name"] == "rsi"

    @pytest.mark.asyncio
    @patch(
        "options_arena.api.routes.learning.auto_tune_indicator_weights",
        new_callable=AsyncMock,
    )
    async def test_trigger_empty_result(
        self,
        mock_tune: AsyncMock,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Returns empty list when insufficient data."""
        mock_tune.return_value = []

        response = await client.post("/api/learning/weights/tune")

        assert response.status_code == 200
        assert response.json() == []
