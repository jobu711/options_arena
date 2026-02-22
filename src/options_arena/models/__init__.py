"""Options Arena — Data Models.

Re-exports all public models and enums from the ``models`` package.
Consumers import from the package: ``from options_arena.models import OptionContract``.
"""

from options_arena.models.analysis import AgentResponse, MarketContext, TradeThesis
from options_arena.models.config import AppSettings, PricingConfig, ScanConfig, ServiceConfig
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
)
from options_arena.models.health import HealthStatus
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.models.options import OptionContract, OptionGreeks, OptionSpread, SpreadLeg
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore

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
    # Scan
    "IndicatorSignals",
    "ScanRun",
    "TickerScore",
    # Config
    "AppSettings",
    "PricingConfig",
    "ScanConfig",
    "ServiceConfig",
    # Health
    "HealthStatus",
]
