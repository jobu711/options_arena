"""Tests for config routing overlay endpoints (PUT, DELETE, GET) — #698."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _valid_routing_body() -> dict[str, object]:
    """Return a valid PUT /api/config/routing request body."""
    return {
        "enable_model_routing": True,
        "complexity_threshold_fast": 0.3,
        "complexity_threshold_premium": 0.7,
        "fast_model": "llama-3.1-8b-instant",
        "premium_model": "llama-3.3-70b-versatile",
        "cost_per_million_tokens": {
            "llama-3.3-70b-versatile": 0.59,
            "llama-3.1-8b-instant": 0.05,
        },
    }


class TestPutRoutingConfig:
    """PUT /api/config/routing — runtime routing overlay."""

    @pytest.mark.asyncio()
    async def test_put_valid_config(self, client: AsyncClient) -> None:
        """PUT with valid config returns 200 + RoutingConfigResponse with is_override=True."""
        response = await client.put("/api/config/routing", json=_valid_routing_body())
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is True
        assert data["enable_model_routing"] is True
        assert data["complexity_threshold_fast"] == pytest.approx(0.3)
        assert data["complexity_threshold_premium"] == pytest.approx(0.7)
        assert data["fast_model"] == "llama-3.1-8b-instant"
        assert data["premium_model"] == "llama-3.3-70b-versatile"
        assert "llama-3.3-70b-versatile" in data["cost_per_million_tokens"]

    @pytest.mark.asyncio()
    async def test_put_invalid_thresholds(self, client: AsyncClient) -> None:
        """PUT with fast >= premium returns 422."""
        body = _valid_routing_body()
        body["complexity_threshold_fast"] = 0.8
        body["complexity_threshold_premium"] = 0.3
        response = await client.put("/api/config/routing", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio()
    async def test_put_equal_thresholds(self, client: AsyncClient) -> None:
        """PUT with fast == premium returns 422."""
        body = _valid_routing_body()
        body["complexity_threshold_fast"] = 0.5
        body["complexity_threshold_premium"] = 0.5
        response = await client.put("/api/config/routing", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio()
    async def test_put_negative_cost(self, client: AsyncClient) -> None:
        """PUT with negative cost returns 422."""
        body = _valid_routing_body()
        body["cost_per_million_tokens"] = {"some-model": -1.0}
        response = await client.put("/api/config/routing", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio()
    async def test_put_nan_threshold(self, client: AsyncClient) -> None:
        """PUT with NaN threshold returns 422."""
        body = _valid_routing_body()
        # JSON does not support NaN natively — send as string to trigger type error,
        # or use None which also fails validation.
        body["complexity_threshold_fast"] = None
        response = await client.put("/api/config/routing", json=body)
        assert response.status_code == 422


class TestDeleteRoutingConfig:
    """DELETE /api/config/routing — clear override."""

    @pytest.mark.asyncio()
    async def test_delete_clears_override(self, client: AsyncClient) -> None:
        """DELETE clears override, returns base config with is_override=False."""
        # First set an override
        await client.put("/api/config/routing", json=_valid_routing_body())

        # Then clear it
        response = await client.delete("/api/config/routing")
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is False
        # Base config defaults
        assert data["enable_model_routing"] is False

    @pytest.mark.asyncio()
    async def test_delete_without_override(self, client: AsyncClient) -> None:
        """DELETE when no override is set still returns 200 with base config."""
        response = await client.delete("/api/config/routing")
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is False


class TestGetConfigWithRouting:
    """GET /api/config — verify routing field is present."""

    @pytest.mark.asyncio()
    async def test_get_without_override(self, client: AsyncClient) -> None:
        """GET returns routing with is_override=False when no override is set."""
        response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "routing" in data
        assert data["routing"] is not None
        assert data["routing"]["is_override"] is False
        # Should reflect base config defaults
        assert data["routing"]["enable_model_routing"] is False

    @pytest.mark.asyncio()
    async def test_get_with_override(self, client: AsyncClient) -> None:
        """PUT then GET returns overridden config with is_override=True."""
        body = _valid_routing_body()
        await client.put("/api/config/routing", json=body)

        response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["routing"]["is_override"] is True
        assert data["routing"]["enable_model_routing"] is True
        assert data["routing"]["complexity_threshold_fast"] == pytest.approx(0.3)

    @pytest.mark.asyncio()
    async def test_put_delete_get_cycle(self, client: AsyncClient) -> None:
        """PUT -> DELETE -> GET returns base config with is_override=False."""
        await client.put("/api/config/routing", json=_valid_routing_body())
        await client.delete("/api/config/routing")

        response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["routing"]["is_override"] is False
        assert data["routing"]["enable_model_routing"] is False
