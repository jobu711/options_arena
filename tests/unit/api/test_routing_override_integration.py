"""Integration tests for routing override pipeline (#701).

End-to-end verification:
- PUT config -> override stored -> GET reflects it -> DELETE restores defaults.
- Multiple PUTs -> last one wins.
- Cost endpoint returns desk_details when desk_metrics_json is populated.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from options_arena.data._recommendation import RecommendationRow


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


def _make_recommendation_row(
    *,
    rec_id: int = 1,
    ticker: str = "AAPL",
    desk_metrics_json: str = "[]",
) -> RecommendationRow:
    """Build a minimal ``RecommendationRow`` for cost endpoint tests."""
    return RecommendationRow(
        id=rec_id,
        ticker=ticker,
        scan_run_id=None,
        direction="bullish",
        confidence=0.75,
        recommended_contract="AAPL240419C00185000",
        entry_price="3.50",
        entry_criteria="Enter on IV dip",
        exit_criteria="Exit at 2x entry",
        stop_loss="1.75",
        take_profit="7.00",
        position_size_pct=2.0,
        risk_reward_ratio=2.0,
        recommended_strategy="long_call",
        summary="Bullish outlook on AAPL",
        key_factors_json='["strong trend", "low IV"]',
        risk_assessment="Moderate risk",
        agent_agreement_score=0.85,
        dissenting_desks_json="[]",
        assessments_json="[]",
        total_input_tokens=5000,
        total_output_tokens=1500,
        duration_ms=3200,
        is_fallback=False,
        citation_density=0.6,
        position_rationale="Strong uptrend with low IV",
        strategy_rationale="Long call optimal for directional bet",
        max_loss_estimate="3.50",
        model_used="llama-3.3-70b-versatile",
        desk_metrics_json=desk_metrics_json,
        created_at="2026-03-23T12:00:00+00:00",
    )


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


class TestCostEndpointDeskDetails:
    """Verify /api/analytics/recommendation-costs returns desk_details."""

    @pytest.mark.asyncio()
    async def test_cost_endpoint_returns_desk_details(
        self, client: AsyncClient, mock_repo: object
    ) -> None:
        """Cost endpoint returns desk_details when desk_metrics_json is populated."""
        desk_metrics = [
            {
                "desk": "trend",
                "model_tier": "standard",
                "model_used": "llama-3.3-70b-versatile",
                "input_tokens": 1200,
                "output_tokens": 350,
                "duration_ms": 1500,
                "status": "success",
            },
            {
                "desk": "volatility",
                "model_tier": "fast",
                "model_used": "llama-3.1-8b-instant",
                "input_tokens": 800,
                "output_tokens": 200,
                "duration_ms": 900,
                "status": "success",
            },
        ]
        row = _make_recommendation_row(desk_metrics_json=json.dumps(desk_metrics))
        mock_repo.get_recent_recommendations.return_value = [row]  # type: ignore[union-attr]

        resp = await client.get("/api/analytics/recommendation-costs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert len(data[0]["desk_details"]) == 2

        trend_desk = data[0]["desk_details"][0]
        assert trend_desk["desk"] == "trend"
        assert trend_desk["tier"] == "standard"
        assert trend_desk["model_used"] == "llama-3.3-70b-versatile"
        assert trend_desk["input_tokens"] == 1200
        assert trend_desk["output_tokens"] == 350
        assert trend_desk["duration_ms"] == 1500
        assert trend_desk["status"] == "success"

        vol_desk = data[0]["desk_details"][1]
        assert vol_desk["desk"] == "volatility"
        assert vol_desk["tier"] == "fast"

    @pytest.mark.asyncio()
    async def test_cost_endpoint_empty_desk_metrics(
        self, client: AsyncClient, mock_repo: object
    ) -> None:
        """Cost endpoint returns empty desk_details when no desk metrics stored."""
        row = _make_recommendation_row(desk_metrics_json="[]")
        mock_repo.get_recent_recommendations.return_value = [row]  # type: ignore[union-attr]

        resp = await client.get("/api/analytics/recommendation-costs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio()
    async def test_cost_endpoint_malformed_desk_metrics(
        self, client: AsyncClient, mock_repo: object
    ) -> None:
        """Cost endpoint handles malformed desk_metrics_json gracefully."""
        row = _make_recommendation_row(desk_metrics_json="{invalid json")
        mock_repo.get_recent_recommendations.return_value = [row]  # type: ignore[union-attr]

        resp = await client.get("/api/analytics/recommendation-costs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["desk_details"] == []

    @pytest.mark.asyncio()
    async def test_cost_endpoint_with_ticker_filter(
        self, client: AsyncClient, mock_repo: object
    ) -> None:
        """Cost endpoint respects ticker query parameter."""
        desk_metrics = [
            {
                "desk": "risk",
                "model_tier": "standard",
                "model_used": "llama-3.3-70b-versatile",
                "input_tokens": 900,
                "output_tokens": 300,
                "duration_ms": 1100,
                "status": "success",
            },
        ]
        row = _make_recommendation_row(ticker="MSFT", desk_metrics_json=json.dumps(desk_metrics))
        mock_repo.get_recommendations_for_ticker.return_value = [row]  # type: ignore[union-attr]

        resp = await client.get("/api/analytics/recommendation-costs?ticker=MSFT")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "MSFT"
        assert len(data[0]["desk_details"]) == 1
        assert data[0]["desk_details"][0]["desk"] == "risk"
