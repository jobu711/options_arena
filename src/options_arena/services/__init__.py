"""Options Arena — Data fetching, caching, and rate limiting.

The services package is the sole layer that touches external APIs.
All public functions return typed Pydantic models.
"""

from options_arena.services.cache import ServiceCache
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.market_data import (
    BatchOHLCVResult,
    MarketDataService,
    TickerOHLCVResult,
)
from options_arena.services.options_data import ExpirationChain, OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import (
    SP500Constituent,
    UniverseService,
    build_sector_map,
    filter_by_sectors,
)

__all__ = [
    "BatchOHLCVResult",
    "ExpirationChain",
    "FredService",
    "HealthService",
    "MarketDataService",
    "OptionsDataService",
    "RateLimiter",
    "SP500Constituent",
    "ServiceCache",
    "TickerOHLCVResult",
    "UniverseService",
    "build_sector_map",
    "filter_by_sectors",
]
