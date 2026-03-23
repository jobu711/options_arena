"""Integration tests for routing override pipeline (#701).

End-to-end verification:
- PUT config -> override stored -> GET reflects it -> DELETE restores defaults.
- Multiple PUTs -> last one wins.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _valid_routing_body(
    *,
    fast_model: str = "test-fast-model",
    premium_model: str = "test-premium-model",
) -> dict[str, object]:
    """Return a valid PUT /api/config/routing request body."""
    return {
        "enable_model_routing": True,
        "complexity_threshold_fast": 0.2,
        "complexity_threshold_premium": 0.8,
        "fast_model": fast_model,
        "premium_model": premium_model,
        "cost_per_million_tokens": {fast_model: 0.01, premium_model: 1.0},
    }


class TestRoutingOverrideIntegration:
    """End-to-end routing override pipeline: PUT -> GET -> DELETE cycle."""

    @pytest.mark.asyncio()
    async def test_put_then_get_reflects_override(self, client: AsyncClient) -> None:
        """PUT routing config then GET /api/config shows overridden values."""
        body = _valid_routing_body()
        put_resp = await client.put("/api/config/routing", json=body)
        assert put_resp.status_code == 200

        get_resp = await client.get("/api/config")
        assert get_resp.status_code == 200
        config = get_resp.json()
        assert config["routing"]["is_override"] is True
        assert config["routing"]["enable_model_routing"] is True
        assert config["routing"]["fast_model"] == "test-fast-model"
        assert config["routing"]["premium_model"] == "test-premium-model"
        assert config["routing"]["complexity_threshold_fast"] == pytest.approx(0.2)
        assert config["routing"]["complexity_threshold_premium"] == pytest.approx(0.8)

    @pytest.mark.asyncio()
    async def test_delete_restores_defaults(self, client: AsyncClient) -> None:
        """PUT then DELETE then GET shows base values with is_override=False."""
        body = _valid_routing_body()
        await client.put("/api/config/routing", json=body)

        del_resp = await client.delete("/api/config/routing")
        assert del_resp.status_code == 200
        assert del_resp.json()["is_override"] is False

        get_resp = await client.get("/api/config")
        config = get_resp.json()
        assert config["routing"]["is_override"] is False
        assert config["routing"]["enable_model_routing"] is False

    @pytest.mark.asyncio()
    async def test_multiple_puts_last_wins(self, client: AsyncClient) -> None:
        """Multiple PUT calls — last one wins."""
        for fast in ["model-a", "model-b", "model-c"]:
            body = _valid_routing_body(fast_model=fast)
            resp = await client.put("/api/config/routing", json=body)
            assert resp.status_code == 200

        get_resp = await client.get("/api/config")
        assert get_resp.json()["routing"]["fast_model"] == "model-c"
        assert get_resp.json()["routing"]["is_override"] is True

    @pytest.mark.asyncio()
    async def test_no_override_uses_base_config(self, client: AsyncClient) -> None:
        """Without override, GET returns base config with is_override=False."""
        get_resp = await client.get("/api/config")
        assert get_resp.status_code == 200
        routing = get_resp.json()["routing"]
        assert routing["is_override"] is False
        assert routing["enable_model_routing"] is False

    @pytest.mark.asyncio()
    async def test_put_delete_put_cycle(self, client: AsyncClient) -> None:
        """PUT -> DELETE -> PUT second override is applied correctly."""
        body_a = _valid_routing_body(fast_model="first-model")
        await client.put("/api/config/routing", json=body_a)
        await client.delete("/api/config/routing")

        body_b = _valid_routing_body(fast_model="second-model")
        await client.put("/api/config/routing", json=body_b)

        get_resp = await client.get("/api/config")
        routing = get_resp.json()["routing"]
        assert routing["is_override"] is True
        assert routing["fast_model"] == "second-model"

    @pytest.mark.asyncio()
    async def test_delete_without_prior_override(self, client: AsyncClient) -> None:
        """DELETE when no override was ever set still returns 200 with base config."""
        del_resp = await client.delete("/api/config/routing")
        assert del_resp.status_code == 200
        assert del_resp.json()["is_override"] is False

        get_resp = await client.get("/api/config")
        assert get_resp.json()["routing"]["is_override"] is False


