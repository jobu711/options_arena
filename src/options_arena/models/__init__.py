"""Options Arena — Data Models.

Re-exports all public models and enums from the ``models`` package.
Consumers import from the package: ``from options_arena.models import OptionContract``.
"""

from options_arena.models.analysis import (
    AgentResponse,
    MarketContext,
    TradeThesis,
    VolatilityThesis,
)
from options_arena.models.config import (
    AppSettings,
    DataConfig,
    DebateConfig,
    PricingConfig,
    ScanConfig,
    ServiceConfig,
)
from options_arena.models.diff import DebateTrendPoint, ScanDiffResult, ScoreChange
from options_arena.models.enums import (
    DividendSource,
    ExerciseStyle,
    GreeksSource,
    MacdSignal,
    MarketCapTier,
    OptionType,
    PositionSide,
    PricingModel,
    ScanPreset,
    SignalDirection,
    SpreadType,
    VolAssessment,
)
from options_arena.models.health import HealthStatus
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.models.options import OptionContract, OptionGreeks, OptionSpread, SpreadLeg
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore
from options_arena.models.watchlist import Watchlist, WatchlistDetail, WatchlistTicker

__all__ = [
    # Enums
    "DividendSource",
    "ExerciseStyle",
    "GreeksSource",
    "MacdSignal",
    "MarketCapTier",
    "OptionType",
    "PositionSide",
    "PricingModel",
    "ScanPreset",
    "SignalDirection",
    "SpreadType",
    "VolAssessment",
    # Market data
    "OHLCV",
    "Quote",
    "TickerInfo",
    # Options
    "OptionContract",
    "OptionGreeks",
    "OptionSpread",
    "SpreadLeg",
    # Analysis
    "AgentResponse",
    "MarketContext",
    "TradeThesis",
    "VolatilityThesis",
    # Scan
    "IndicatorSignals",
    "ScanRun",
    "TickerScore",
    # Config
    "AppSettings",
    "DataConfig",
    "DebateConfig",
    "PricingConfig",
    "ScanConfig",
    "ServiceConfig",
    # Diff
    "DebateTrendPoint",
    "ScanDiffResult",
    "ScoreChange",
    # Watchlist
    "Watchlist",
    "WatchlistDetail",
    "WatchlistTicker",
    # Health
    "HealthStatus",
]
