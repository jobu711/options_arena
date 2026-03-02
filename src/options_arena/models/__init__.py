"""Options Arena — Data Models.

Re-exports all public models and enums from the ``models`` package.
Consumers import from the package: ``from options_arena.models import OptionContract``.
"""

from options_arena.models.analysis import (
    AgentResponse,
    ContrarianThesis,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    TradeThesis,
    VolatilityThesis,
)
from options_arena.models.config import (
    AppSettings,
    DataConfig,
    DebateConfig,
    LogConfig,
    OpenBBConfig,
    PricingConfig,
    ScanConfig,
    ServiceConfig,
)
from options_arena.models.enums import (
    SECTOR_ALIASES,
    CatalystImpact,
    DividendSource,
    ExerciseStyle,
    GICSSector,
    GreeksSource,
    IVTermStructureShape,
    MacdSignal,
    MarketCapTier,
    MarketRegime,
    OptionType,
    PositionSide,
    PricingModel,
    RiskLevel,
    ScanPreset,
    SentimentLabel,
    SignalDirection,
    SpreadType,
    VolAssessment,
    VolRegime,
)
from options_arena.models.health import HealthStatus
from options_arena.models.history import HistoryPoint, TrendingTicker
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsHeadline,
    NewsSentimentSnapshot,
    OpenBBHealthStatus,
    UnusualFlowSnapshot,
)
from options_arena.models.options import OptionContract, OptionGreeks, OptionSpread, SpreadLeg
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore
from options_arena.models.scan_delta import ScanDiff, TickerDelta
from options_arena.models.scoring import DimensionalScores, DirectionSignal
from options_arena.models.watchlist import (
    Watchlist,
    WatchlistDetail,
    WatchlistTicker,
    WatchlistTickerDetail,
)

__all__ = [
    # Enums
    "CatalystImpact",
    "DividendSource",
    "ExerciseStyle",
    "GICSSector",
    "GreeksSource",
    "IVTermStructureShape",
    "MacdSignal",
    "MarketCapTier",
    "MarketRegime",
    "OptionType",
    "PositionSide",
    "PricingModel",
    "RiskLevel",
    "SECTOR_ALIASES",
    "ScanPreset",
    "SentimentLabel",
    "SignalDirection",
    "SpreadType",
    "VolAssessment",
    "VolRegime",
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
    "ContrarianThesis",
    "ExtendedTradeThesis",
    "FlowThesis",
    "FundamentalThesis",
    "MarketContext",
    "RiskAssessment",
    "TradeThesis",
    "VolatilityThesis",
    # Scan
    "IndicatorSignals",
    "ScanRun",
    "TickerScore",
    # Scan delta
    "ScanDiff",
    "TickerDelta",
    # Scoring
    "DimensionalScores",
    "DirectionSignal",
    # Config
    "AppSettings",
    "DataConfig",
    "DebateConfig",
    "LogConfig",
    "OpenBBConfig",
    "PricingConfig",
    "ScanConfig",
    "ServiceConfig",
    # History
    "HistoryPoint",
    "TrendingTicker",
    # Health
    "HealthStatus",
    # OpenBB
    "FundamentalSnapshot",
    "NewsHeadline",
    "NewsSentimentSnapshot",
    "OpenBBHealthStatus",
    "UnusualFlowSnapshot",
    # Watchlist
    "Watchlist",
    "WatchlistDetail",
    "WatchlistTicker",
    "WatchlistTickerDetail",
]
