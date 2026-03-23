"""Tests for routing config and cost detail API schemas (#704)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.api.schemas import (
    ConfigResponse,
    DeskCostDetail,
    RecommendationCostSummary,
    RoutingConfigResponse,
    RoutingConfigUpdate,
)


def _valid_routing_update_kwargs() -> dict[str, object]:
    """Return kwargs for a valid RoutingConfigUpdate."""
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


class TestRoutingConfigUpdate:
    """Verify RoutingConfigUpdate validation logic."""

    def test_valid_config_accepted(self) -> None:
        """Verify valid routing config passes validation."""
        update = RoutingConfigUpdate(**_valid_routing_update_kwargs())
        assert update.enable_model_routing is True
        assert update.complexity_threshold_fast == pytest.approx(0.3)
        assert update.complexity_threshold_premium == pytest.approx(0.7)
        assert update.fast_model == "llama-3.1-8b-instant"
        assert update.premium_model == "llama-3.3-70b-versatile"
        assert len(update.cost_per_million_tokens) == 2

    def test_fast_gte_premium_rejected(self) -> None:
        """Verify fast >= premium threshold raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_fast"] = 0.7
        kwargs["complexity_threshold_premium"] = 0.3
        with pytest.raises(ValidationError, match="must be <"):
            RoutingConfigUpdate(**kwargs)

    def test_fast_equals_premium_rejected(self) -> None:
        """Verify fast == premium threshold raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_fast"] = 0.5
        kwargs["complexity_threshold_premium"] = 0.5
        with pytest.raises(ValidationError, match="must be <"):
            RoutingConfigUpdate(**kwargs)

    def test_negative_cost_rejected(self) -> None:
        """Verify negative cost values raise ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["cost_per_million_tokens"] = {"model-a": -1.0}
        with pytest.raises(ValidationError, match="must be >= 0"):
            RoutingConfigUpdate(**kwargs)

    def test_nan_threshold_rejected(self) -> None:
        """Verify NaN threshold raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_fast"] = float("nan")
        with pytest.raises(ValidationError, match="finite"):
            RoutingConfigUpdate(**kwargs)

    def test_inf_threshold_rejected(self) -> None:
        """Verify Inf threshold raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_premium"] = float("inf")
        with pytest.raises(ValidationError, match="finite"):
            RoutingConfigUpdate(**kwargs)

    def test_threshold_out_of_range_rejected(self) -> None:
        """Verify threshold > 1.0 raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_premium"] = 1.5
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            RoutingConfigUpdate(**kwargs)

    def test_threshold_below_zero_rejected(self) -> None:
        """Verify threshold < 0.0 raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_fast"] = -0.1
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            RoutingConfigUpdate(**kwargs)

    def test_nan_cost_rejected(self) -> None:
        """Verify NaN cost value raises ValidationError."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["cost_per_million_tokens"] = {"model-a": float("nan")}
        with pytest.raises(ValidationError, match="finite"):
            RoutingConfigUpdate(**kwargs)

    def test_boundary_thresholds_accepted(self) -> None:
        """Verify thresholds at 0.0 and 1.0 are accepted (when ordered)."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["complexity_threshold_fast"] = 0.0
        kwargs["complexity_threshold_premium"] = 1.0
        update = RoutingConfigUpdate(**kwargs)
        assert update.complexity_threshold_fast == pytest.approx(0.0)
        assert update.complexity_threshold_premium == pytest.approx(1.0)

    def test_empty_cost_map_accepted(self) -> None:
        """Verify empty cost map is valid (no models configured)."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["cost_per_million_tokens"] = {}
        update = RoutingConfigUpdate(**kwargs)
        assert update.cost_per_million_tokens == {}

    def test_empty_premium_model_accepted(self) -> None:
        """Verify empty string for premium_model is valid (means use default)."""
        kwargs = _valid_routing_update_kwargs()
        kwargs["premium_model"] = ""
        update = RoutingConfigUpdate(**kwargs)
        assert update.premium_model == ""


class TestRoutingConfigResponse:
    """Verify RoutingConfigResponse schema."""

    def test_with_override_flag(self) -> None:
        """Verify is_override field serializes correctly."""
        resp = RoutingConfigResponse(
            enable_model_routing=True,
            complexity_threshold_fast=0.3,
            complexity_threshold_premium=0.7,
            fast_model="llama-3.1-8b-instant",
            premium_model="",
            cost_per_million_tokens={"llama-3.3-70b-versatile": 0.59},
            is_override=True,
        )
        assert resp.is_override is True
        data = resp.model_dump()
        assert data["is_override"] is True

    def test_without_override(self) -> None:
        """Verify is_override=False."""
        resp = RoutingConfigResponse(
            enable_model_routing=False,
            complexity_threshold_fast=0.3,
            complexity_threshold_premium=0.7,
            fast_model="llama-3.1-8b-instant",
            premium_model="",
            cost_per_million_tokens={},
            is_override=False,
        )
        assert resp.is_override is False

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization roundtrip."""
        resp = RoutingConfigResponse(
            enable_model_routing=True,
            complexity_threshold_fast=0.2,
            complexity_threshold_premium=0.8,
            fast_model="fast-model",
            premium_model="premium-model",
            cost_per_million_tokens={"fast-model": 0.05, "premium-model": 1.0},
            is_override=False,
        )
        restored = RoutingConfigResponse.model_validate_json(resp.model_dump_json())
        assert restored == resp


class TestDeskCostDetail:
    """Verify DeskCostDetail schema."""

    def _make_detail(self) -> DeskCostDetail:
        """Create a valid DeskCostDetail."""
        return DeskCostDetail(
            desk="trend",
            tier="STANDARD",
            model_used="llama-3.3-70b-versatile",
            input_tokens=1500,
            output_tokens=800,
            duration_ms=2400,
            status="SUCCESS",
        )

    def test_frozen_model(self) -> None:
        """Verify DeskCostDetail is frozen."""
        detail = self._make_detail()
        with pytest.raises(ValidationError):
            detail.desk = "volatility"

    def test_json_roundtrip(self) -> None:
        """Verify DeskCostDetail survives JSON roundtrip."""
        detail = self._make_detail()
        restored = DeskCostDetail.model_validate_json(detail.model_dump_json())
        assert restored == detail
        assert restored.desk == "trend"
        assert restored.input_tokens == 1500
        assert restored.output_tokens == 800
        assert restored.duration_ms == 2400

    def test_all_fields_present(self) -> None:
        """Verify all expected fields are present."""
        detail = self._make_detail()
        data = detail.model_dump()
        expected_fields = {
            "desk", "tier", "model_used", "input_tokens",
            "output_tokens", "duration_ms", "status",
        }
        assert set(data.keys()) == expected_fields


class TestExpandedConfigResponse:
    """Verify ConfigResponse includes routing field."""

    def test_routing_field_present(self) -> None:
        """Verify ConfigResponse includes routing field."""
        routing = RoutingConfigResponse(
            enable_model_routing=True,
            complexity_threshold_fast=0.3,
            complexity_threshold_premium=0.7,
            fast_model="fast",
            premium_model="premium",
            cost_per_million_tokens={},
            is_override=False,
        )
        config = ConfigResponse(
            groq_api_key_set=True,
            scan_preset_default="sp500",
            agent_timeout=30.0,
            recommendation_protocol="recommendation",
            routing=routing,
        )
        assert config.routing is not None
        assert config.routing.enable_model_routing is True

    def test_routing_field_defaults_none(self) -> None:
        """Verify routing defaults to None when not provided."""
        config = ConfigResponse(
            groq_api_key_set=False,
            scan_preset_default="sp500",
            agent_timeout=30.0,
            recommendation_protocol="recommendation",
        )
        assert config.routing is None


class TestExpandedRecommendationCostSummary:
    """Verify RecommendationCostSummary has desk_details field."""

    def test_desk_details_default_empty(self) -> None:
        """Verify desk_details defaults to empty list."""
        summary = RecommendationCostSummary(
            ticker="AAPL",
            created_at="2026-03-22T12:00:00Z",
            duration_ms=5000,
            total_tokens=10000,
            is_fallback=False,
        )
        assert summary.desk_details == []

    def test_desk_details_populated(self) -> None:
        """Verify desk_details can contain DeskCostDetail items."""
        details = [
            DeskCostDetail(
                desk="trend",
                tier="STANDARD",
                model_used="llama-3.3-70b-versatile",
                input_tokens=1500,
                output_tokens=800,
                duration_ms=2400,
                status="SUCCESS",
            ),
            DeskCostDetail(
                desk="risk",
                tier="PREMIUM",
                model_used="llama-3.3-70b-versatile",
                input_tokens=2000,
                output_tokens=1000,
                duration_ms=3100,
                status="SUCCESS",
            ),
        ]
        summary = RecommendationCostSummary(
            ticker="AAPL",
            created_at="2026-03-22T12:00:00Z",
            duration_ms=5500,
            total_tokens=15000,
            is_fallback=False,
            desk_details=details,
        )
        assert len(summary.desk_details) == 2
        assert summary.desk_details[0].desk == "trend"
        assert summary.desk_details[1].desk == "risk"
        assert summary.desk_details[1].tier == "PREMIUM"
