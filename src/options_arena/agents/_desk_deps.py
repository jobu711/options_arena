"""Dependency injection dataclass for desk agents.

Follows the ``DebateDeps`` pattern — a plain dataclass (PydanticAI convention).
Service instances are injected by the caller (CLI or API layer).
``tools_used`` accumulates tool names during a query for observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from options_arena.data.repository import Repository
from options_arena.services.fred import FredService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService


@dataclass
class DeskDeps:
    """Dependency injection for desk agents.

    Follows the DebateDeps pattern -- a plain dataclass (PydanticAI convention).
    Service instances are injected by the caller (CLI or API layer).
    ``tools_used`` accumulates tool names during a query for observability.
    """

    query: str
    ticker: str
    market_data: MarketDataService
    options_data: OptionsDataService
    repo: Repository
    fred: FredService | None = None
    tools_used: list[str] = field(default_factory=list)
    learned_patterns: str = ""
