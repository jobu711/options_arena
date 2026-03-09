"""FastAPI dependency injection providers.

Each provider reads from ``app.state`` (populated by the lifespan context manager)
and adds type information at the injection site.
"""

from __future__ import annotations

import asyncio
from typing import cast

from fastapi import Request

from options_arena.data import Repository
from options_arena.models.config import AppSettings
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.fred import FredService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import MarketDataService
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.outcome_collector import OutcomeCollector
from options_arena.services.universe import UniverseService


def get_repo(request: Request) -> Repository:
    """Inject the typed CRUD repository."""
    return cast(Repository, request.app.state.repo)


def get_market_data(request: Request) -> MarketDataService:
    """Inject the market data service."""
    return cast(MarketDataService, request.app.state.market_data)


def get_options_data(request: Request) -> OptionsDataService:
    """Inject the options data service."""
    return cast(OptionsDataService, request.app.state.options_data)


def get_fred(request: Request) -> FredService:
    """Inject the FRED service."""
    return cast(FredService, request.app.state.fred)


def get_universe(request: Request) -> UniverseService:
    """Inject the universe service."""
    return cast(UniverseService, request.app.state.universe)


def get_settings(request: Request) -> AppSettings:
    """Inject the application settings."""
    return cast(AppSettings, request.app.state.settings)


def get_openbb(request: Request) -> OpenBBService | None:
    """Inject the OpenBB enrichment service (``None`` when disabled)."""
    return cast(OpenBBService | None, request.app.state.openbb)


def get_intelligence(request: Request) -> IntelligenceService | None:
    """Inject the intelligence service (``None`` when disabled)."""
    return getattr(request.app.state, "intelligence", None)


def get_financial_datasets(request: Request) -> FinancialDatasetsService | None:
    """Inject the Financial Datasets service (``None`` when disabled or no API key)."""
    return getattr(request.app.state, "financial_datasets", None)


def get_operation_lock(request: Request) -> asyncio.Lock:
    """Inject the global operation mutex."""
    return cast(asyncio.Lock, request.app.state.operation_lock)


def get_outcome_collector(request: Request) -> OutcomeCollector:
    """Inject the outcome collector service (created on-demand via DI)."""
    return OutcomeCollector(
        config=request.app.state.settings.analytics,
        repository=request.app.state.repo,
        market_data=request.app.state.market_data,
        options_data=request.app.state.options_data,
    )
