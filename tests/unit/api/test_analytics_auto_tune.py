"""Tests for auto-tune API endpoints.

Covers:
  - POST /api/analytics/weights/auto-tune
  - GET /api/analytics/weights/history
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from options_arena.models import AgentWeightsComparison, WeightSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_weights_comparison(agent: str = "trend") -> AgentWeightsComparison:
    return AgentWeightsComparison(
        agent_name=agent,
        manual_weight=0.25,
        auto_weight=0.22,
        brier_score=0.18,
        sample_size=50,
    )


def _make_weight_snapshot() -> WeightSnapshot:
    return WeightSnapshot(
        computed_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        window_days=90,
        weights=[_make_weights_comparison("trend"), _make_weights_comparison("volatility")],
    )


# ---------------------------------------------------------------------------
# POST /api/analytics/weights/auto-tune
# ---------------------------------------------------------------------------


class TestAutoTuneEndpoint:
    """Tests for POST /api/analytics/weights/auto-tune."""

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.analytics.auto_tune_weights", new_callable=AsyncMock)
    async def test_post_auto_tune_success(
        self, mock_auto_tune: AsyncMock, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """POST triggers computation and returns comparisons."""
        comparisons = [_make_weights_comparison("trend"), _make_weights_comparison("volatility")]
        mock_auto_tune.return_value = comparisons

        response = await client.post("/api/analytics/weights/auto-tune")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["agent_name"] == "trend"
        assert data[0]["auto_weight"] == pytest.approx(0.22)
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=90, dry_run=False)

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.analytics.auto_tune_weights", new_callable=AsyncMock)
    async def test_post_auto_tune_dry_run(
        self, mock_auto_tune: AsyncMock, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """dry_run=true skips persistence."""
        mock_auto_tune.return_value = [_make_weights_comparison()]

        response = await client.post("/api/analytics/weights/auto-tune?dry_run=true")

        assert response.status_code == 200
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=90, dry_run=True)

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.analytics.auto_tune_weights", new_callable=AsyncMock)
    async def test_post_auto_tune_custom_window(
        self, mock_auto_tune: AsyncMock, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """window parameter is forwarded to auto_tune_weights."""
        mock_auto_tune.return_value = []

        response = await client.post("/api/analytics/weights/auto-tune?window=180")

        assert response.status_code == 200
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=180, dry_run=False)

    @pytest.mark.asyncio
    async def test_post_auto_tune_window_validation_too_low(self, client: AsyncClient) -> None:
        """Rejects window < 1."""
        response = await client.post("/api/analytics/weights/auto-tune?window=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_auto_tune_window_validation_too_high(self, client: AsyncClient) -> None:
        """Rejects window > 365."""
        response = await client.post("/api/analytics/weights/auto-tune?window=400")
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.analytics.auto_tune_weights", new_callable=AsyncMock)
    async def test_post_auto_tune_concurrent_returns_409(
        self, mock_auto_tune: AsyncMock, test_app: object, client: AsyncClient
    ) -> None:
        """Returns 409 when operation mutex is already held."""
        import asyncio

        from options_arena.api.deps import get_operation_lock

        lock = asyncio.Lock()
        await lock.acquire()  # Pre-hold the lock
        test_app.dependency_overrides[get_operation_lock] = lambda: lock  # type: ignore[union-attr]
        try:
            response = await client.post("/api/analytics/weights/auto-tune")
            assert response.status_code == 409
            mock_auto_tune.assert_not_called()
        finally:
            lock.release()


# ---------------------------------------------------------------------------
# GET /api/analytics/weights/history
# ---------------------------------------------------------------------------


class TestWeightHistoryEndpoint:
    """Tests for GET /api/analytics/weights/history."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns list of WeightSnapshot."""
        snapshot = _make_weight_snapshot()
        mock_repo.get_weight_history = AsyncMock(return_value=[snapshot])

        response = await client.get("/api/analytics/weights/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["window_days"] == 90
        assert len(data[0]["weights"]) == 2
        assert data[0]["weights"][0]["agent_name"] == "trend"

    @pytest.mark.asyncio
    async def test_get_history_empty(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Empty list when no history exists."""
        mock_repo.get_weight_history = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/weights/history")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_history_limit(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """limit parameter is respected and forwarded."""
        mock_repo.get_weight_history = AsyncMock(return_value=[])

        response = await client.get("/api/analytics/weights/history?limit=5")

        assert response.status_code == 200
        mock_repo.get_weight_history.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_get_history_limit_validation_too_low(self, client: AsyncClient) -> None:
        """Rejects limit < 1."""
        response = await client.get("/api/analytics/weights/history?limit=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_history_limit_validation_too_high(self, client: AsyncClient) -> None:
        """Rejects limit > 100."""
        response = await client.get("/api/analytics/weights/history?limit=200")
        assert response.status_code == 422
