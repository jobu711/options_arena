"""Options Arena — Data Models.

Re-exports all public models and enums from the ``models`` package.
Consumers import from the package: ``from options_arena.models import OptionContract``.
"""

from options_arena.models.analysis import (
    AgentPrediction,
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
from options_arena.models.analytics import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentWeightsComparison,
    CalibrationBucket,
    ContractOutcome,
    DeltaPerformanceResult,
    DrawdownPoint,
    DTEBucketResult,
    EquityCurvePoint,
    GreeksDecompositionResult,
    HoldingPeriodComparison,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    IVRankBucketResult,
    NormalizationStats,
    PerformanceSummary,
    RecommendedContract,
    ScoreCalibrationBucket,
    SectorPerformanceResult,
    WeightSnapshot,
    WinRateResult,
)
from options_arena.models.config import (
    TICKER_RE,
    AnalyticsConfig,
    AppSettings,
    DataConfig,
    DebateConfig,
    FinancialDatasetsConfig,
    IntelligenceConfig,
    LogConfig,
    OpenBBConfig,
    PricingConfig,
    ScanConfig,
    ServiceConfig,
)
from options_arena.models.enums import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    SECTOR_TO_INDUSTRY_GROUPS,
    CatalystImpact,
    DividendSource,
    ExerciseStyle,
    GICSIndustryGroup,
    GICSSector,
    GreeksGroupBy,
    GreeksSource,
    IVTermStructureShape,
    LLMProvider,
    MacdSignal,
    MarketCapTier,
    MarketRegime,
    OptionType,
    OutcomeCollectionMethod,
    PositionSide,
    PricingModel,
    RiskLevel,
    ScanPreset,
    ScanSource,
    SentimentLabel,
    SignalDirection,
    SpreadType,
    VolAssessment,
    VolRegime,
)
from options_arena.models.filters import (
    OptionsFilters,
    ScanFilterSpec,
    ScoringFilters,
    UniverseFilters,
)
from options_arena.models.financial_datasets import (
    BalanceSheetData,
    FinancialDatasetsPackage,
    FinancialMetricsData,
    IncomeStatementData,
)
from options_arena.models.health import HealthStatus
from options_arena.models.history import HistoryPoint, TrendingTicker
from options_arena.models.intelligence import (
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InsiderTransaction,
    InstitutionalSnapshot,
    IntelligencePackage,
    UpgradeDowngrade,
)
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.models.metadata import MetadataCoverage, TickerMetadata
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

__all__ = [
    # Enums
    "CatalystImpact",
    "DividendSource",
    "ExerciseStyle",
    "GICSIndustryGroup",
    "GICSSector",
    "GreeksGroupBy",
    "GreeksSource",
    "INDUSTRY_GROUP_ALIASES",
    "IVTermStructureShape",
    "LLMProvider",
    "MacdSignal",
    "MarketCapTier",
    "MarketRegime",
    "OptionType",
    "OutcomeCollectionMethod",
    "PositionSide",
    "PricingModel",
    "RiskLevel",
    "SECTOR_ALIASES",
    "SECTOR_TO_INDUSTRY_GROUPS",
    "ScanPreset",
    "ScanSource",
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
    "AgentPrediction",
    "AgentResponse",
    "ContrarianThesis",
    "ExtendedTradeThesis",
    "FlowThesis",
    "FundamentalThesis",
    "MarketContext",
    "RiskAssessment",
    "TradeThesis",
    "VolatilityThesis",
    # Analytics
    "AgentAccuracyReport",
    "AgentCalibrationData",
    "AgentWeightsComparison",
    "CalibrationBucket",
    "ContractOutcome",
    "DTEBucketResult",
    "DeltaPerformanceResult",
    "DrawdownPoint",
    "EquityCurvePoint",
    "GreeksDecompositionResult",
    "HoldingPeriodComparison",
    "HoldingPeriodResult",
    "IVRankBucketResult",
    "IndicatorAttributionResult",
    "NormalizationStats",
    "PerformanceSummary",
    "RecommendedContract",
    "ScoreCalibrationBucket",
    "SectorPerformanceResult",
    "WeightSnapshot",
    "WinRateResult",
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
    "AnalyticsConfig",
    "AppSettings",
    "DataConfig",
    "DebateConfig",
    "FinancialDatasetsConfig",
    "IntelligenceConfig",
    "LogConfig",
    "OpenBBConfig",
    "PricingConfig",
    "ScanConfig",
    "ServiceConfig",
    "TICKER_RE",
    # Filters
    "OptionsFilters",
    "ScanFilterSpec",
    "ScoringFilters",
    "UniverseFilters",
    # Financial Datasets
    "BalanceSheetData",
    "FinancialDatasetsPackage",
    "FinancialMetricsData",
    "IncomeStatementData",
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
    # Intelligence
    "AnalystActivitySnapshot",
    "AnalystSnapshot",
    "InsiderSnapshot",
    "InsiderTransaction",
    "InstitutionalSnapshot",
    "IntelligencePackage",
    "UpgradeDowngrade",
    # Metadata
    "MetadataCoverage",
    "TickerMetadata",
]
