"""Pipeline-internal typed models for the scan pipeline.

Four orchestration artifacts used to pass data between pipeline phases:
  UniverseResult  -- Phase 1 output: universe tickers + OHLCV data.
  ScoringResult   -- Phase 2 output: scored tickers + raw signals.
  OptionsResult   -- Phase 3 output: recommended contracts + risk-free rate.
  ScanResult      -- Final pipeline output: all phases combined.

These are NOT domain models -- they live in ``scan/``, not ``models/``.
They are NOT frozen -- the pipeline updates them during execution.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from options_arena.models import (
    OHLCV,
    GICSIndustryGroup,
    GICSSector,
    IndicatorSignals,
    NormalizationStats,
    OptionContract,
    ScanRun,
    SpreadAnalysis,
    TickerScore,
)


class UniverseResult(BaseModel):
    """Phase 1 output: universe tickers + OHLCV data.

    Attributes:
        tickers: Full universe list of ticker symbols.
        ohlcv_map: Ticker to OHLCV bars mapping (successful fetches only).
        sp500_sectors: Ticker to raw GICS sector string mapping (from Wikipedia).
        sector_map: Ticker to typed GICSSector enum mapping (normalized from sp500_sectors).
        industry_group_map: Ticker to typed GICSIndustryGroup enum mapping
            (from SECTOR_TO_INDUSTRY_GROUPS inference or yfinance industry data).
        failed_count: Number of tickers that failed OHLCV fetch.
        filtered_count: Number of tickers filtered for insufficient bars.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tickers: list[str]
    ohlcv_map: dict[str, list[OHLCV]]
    sp500_sectors: dict[str, str]
    sector_map: dict[str, GICSSector] = Field(default_factory=dict)
    industry_group_map: dict[str, GICSIndustryGroup] = Field(default_factory=dict)
    failed_count: int
    filtered_count: int


class ScoringResult(BaseModel):
    """Phase 2 output: scored tickers + raw signals.

    ``raw_signals`` stores RAW indicator values (NOT normalized).  This is
    critical because ``determine_direction()`` uses absolute thresholds
    (e.g., ADX < 15.0) that would be meaningless against percentile-ranked
    values.

    Attributes:
        scores: TickerScore list sorted descending by composite_score, direction set.
        raw_signals: Ticker to raw (NOT normalized) IndicatorSignals mapping.
        normalization_stats: Per-indicator distribution metadata (computed in Phase 2).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scores: list[TickerScore]
    raw_signals: dict[str, IndicatorSignals]
    normalization_stats: list[NormalizationStats] = Field(default_factory=list)


class OptionsResult(BaseModel):
    """Phase 3 output: recommended contracts + risk-free rate.

    Attributes:
        recommendations: Ticker to recommended contracts mapping (0 or 1 contracts per ticker).
        risk_free_rate: Risk-free rate used for the entire scan (from FRED or fallback).
        earnings_dates: Ticker to next earnings date mapping (None if unknown).
        entry_prices: Ticker to spot price at scan time (captured from TickerInfo.current_price).
        spread_analyses: Ticker to multi-leg spread analysis mapping (populated when
            SpreadConfig.enabled is True and select_strategy returns a result).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    recommendations: dict[str, list[OptionContract]]
    risk_free_rate: float
    earnings_dates: dict[str, date] = Field(default_factory=dict)
    entry_prices: dict[str, Decimal] = Field(default_factory=dict)
    spread_analyses: dict[str, SpreadAnalysis] = Field(default_factory=dict)


class ScanResult(BaseModel):
    """Final pipeline output combining all phases.

    Attributes:
        scan_run: Metadata for this scan (id populated after persist).
        scores: All scored tickers with direction set.
        recommendations: Recommended contracts per ticker.
        risk_free_rate: FRED rate or fallback used for pricing.
        earnings_dates: Ticker to next earnings date mapping.
        cancelled: True if the pipeline was cancelled mid-run.
        phases_completed: How far the pipeline progressed (0--4).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scan_run: ScanRun
    scores: list[TickerScore]
    recommendations: dict[str, list[OptionContract]]
    risk_free_rate: float
    earnings_dates: dict[str, date] = Field(default_factory=dict)
    cancelled: bool = False
    phases_completed: int = Field(default=0, ge=0, le=4)
