"""Options Arena — Data fetching, caching, and rate limiting.

The services package is the sole layer that touches external APIs.
All public functions return typed Pydantic models.
"""

from options_arena.services.base import ServiceBase
from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import (
    BatchOHLCVResult,
    BatchQuote,
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
    build_industry_group_map,
    build_sector_map,
    classify_market_cap,
    filter_by_industry_groups,
    filter_by_sectors,
    index_tickers,
    map_yfinance_to_metadata,
)

__all__ = [
    "BatchOHLCVResult",
    "BatchQuote",
    "CBOEChainProvider",
    "ChainProvider",
    "ExpirationChain",
    "FinancialDatasetsService",
    "FredService",
    "HealthService",
    "IntelligenceService",
    "MarketDataService",
    "OpenBBService",
    "OptionsDataService",
    "OutcomeCollector",
    "RateLimiter",
    "SP500Constituent",
    "ServiceBase",
    "ServiceCache",
    "TickerOHLCVResult",
    "UniverseService",
    "YFinanceChainProvider",
    "build_industry_group_map",
    "build_sector_map",
    "classify_market_cap",
    "filter_by_industry_groups",
    "filter_by_sectors",
    "index_tickers",
    "map_yfinance_to_metadata",
]
