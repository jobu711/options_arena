"""Config endpoints — GET (read-only), PUT/DELETE routing overlay."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_routing_override, get_settings
from options_arena.api.schemas import ConfigResponse, RoutingConfigResponse, RoutingConfigUpdate
from options_arena.models import AppSettings
from options_arena.models.config import RoutingConfig

router = APIRouter(prefix="/api", tags=["config"])


def _routing_response(cfg: RoutingConfig, *, is_override: bool) -> RoutingConfigResponse:
    """Build a ``RoutingConfigResponse`` from a ``RoutingConfig`` instance."""
    return RoutingConfigResponse(
        enable_model_routing=cfg.enable_model_routing,
        complexity_threshold_fast=cfg.complexity_threshold_fast,
        complexity_threshold_premium=cfg.complexity_threshold_premium,
        fast_model=cfg.fast_model,
        premium_model=cfg.premium_model,
        cost_per_million_tokens=cfg.cost_per_million_tokens,
        is_override=is_override,
    )


@router.get("/config")
@limiter.limit("60/minute")
async def get_config(
    request: Request,
    settings: AppSettings = Depends(get_settings),
    override: RoutingConfig | None = Depends(get_routing_override),
) -> ConfigResponse:
    """Return safe configuration values (never the actual API key)."""
    has_api_key = settings.debate.api_key is not None or bool(os.environ.get("GROQ_API_KEY"))

    # Resolve routing: override if set, else base config
    resolved = override if override is not None else settings.debate.routing
    routing = _routing_response(resolved, is_override=override is not None)

    return ConfigResponse(
        groq_api_key_set=has_api_key,
        scan_preset_default="sp500",
        agent_timeout=settings.debate.agent_timeout,
        recommendation_protocol=settings.debate.recommendation_protocol,
        routing=routing,
    )


@router.put("/config/routing")
@limiter.limit("10/minute")
async def put_routing_config(
    request: Request,
    body: RoutingConfigUpdate,
    settings: AppSettings = Depends(get_settings),  # noqa: ARG001
) -> RoutingConfigResponse:
    """Set a runtime routing config override.

    The override persists in-memory until cleared via DELETE or server restart.
    Validates input by constructing a ``RoutingConfig`` (leverages model validators).
    """
    routing = RoutingConfig(**body.model_dump())
    request.app.state.routing_override = routing
    return _routing_response(routing, is_override=True)


@router.delete("/config/routing")
@limiter.limit("10/minute")
async def delete_routing_config(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> RoutingConfigResponse:
    """Clear the runtime routing config override, reverting to base config."""
    request.app.state.routing_override = None
    return _routing_response(settings.debate.routing, is_override=False)
