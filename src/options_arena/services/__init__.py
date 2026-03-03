"""Options Arena — Data fetching, caching, and rate limiting.

The services package is the sole layer that touches external APIs.
All public functions return typed Pydantic models.
"""

from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import (
    BatchOHLCVResult,
    MarketDataService,
    TickerOHLCVResult,
)
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import (
    ChainProvider,
    ExpirationChain,
    OptionsDataService,
    YFinanceChainProvider,
)
from options_arena.services.outcome_collector import OutcomeCollector
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import (
    SP500Constituent,
    UniverseService,
    build_sector_map,
    filter_by_sectors,
)

__all__ = [
    "BatchOHLCVResult",
    "CBOEChainProvider",
    "ChainProvider",
    "ExpirationChain",
    "FredService",
    "HealthService",
    "IntelligenceService",
    "MarketDataService",
    "OpenBBService",
    "OptionsDataService",
    "OutcomeCollector",
    "RateLimiter",
    "SP500Constituent",
    "ServiceCache",
    "TickerOHLCVResult",
    "UniverseService",
    "YFinanceChainProvider",
    "build_sector_map",
    "filter_by_sectors",
]
