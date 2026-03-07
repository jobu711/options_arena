"""FastAPI dependency injection providers.

Each provider reads from ``app.state`` (populated by the lifespan context manager)
and adds type information at the injection site.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

from options_arena.data import Repository
from options_arena.models.config import AppSettings
from options_arena.services.fred import FredService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import MarketDataService
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.outcome_collector import OutcomeCollector
from options_arena.services.universe import UniverseService


def get_repo(request: Request) -> Repository:
    """Inject the typed CRUD repository."""
    return request.app.state.repo  # type: ignore[no-any-return]


def get_market_data(request: Request) -> MarketDataService:
    """Inject the market data service."""
    return request.app.state.market_data  # type: ignore[no-any-return]


def get_options_data(request: Request) -> OptionsDataService:
    """Inject the options data service."""
    return request.app.state.options_data  # type: ignore[no-any-return]


def get_fred(request: Request) -> FredService:
    """Inject the FRED service."""
    return request.app.state.fred  # type: ignore[no-any-return]


def get_universe(request: Request) -> UniverseService:
    """Inject the universe service."""
    return request.app.state.universe  # type: ignore[no-any-return]


def get_settings(request: Request) -> AppSettings:
    """Inject the application settings."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_openbb(request: Request) -> OpenBBService | None:
    """Inject the OpenBB enrichment service (``None`` when disabled)."""
    return request.app.state.openbb  # type: ignore[no-any-return]


def get_intelligence(request: Request) -> IntelligenceService | None:
    """Inject the intelligence service (``None`` when disabled)."""
    return getattr(request.app.state, "intelligence", None)


def get_operation_lock(request: Request) -> asyncio.Lock:
    """Inject the global operation mutex."""
    return request.app.state.operation_lock  # type: ignore[no-any-return]


def get_outcome_collector(request: Request) -> OutcomeCollector:
    """Inject the outcome collector service (created on-demand via DI)."""
    return OutcomeCollector(
        config=request.app.state.settings.analytics,
        repository=request.app.state.repo,
        market_data=request.app.state.market_data,
        options_data=request.app.state.options_data,
    )
