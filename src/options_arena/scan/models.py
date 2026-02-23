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

from pydantic import BaseModel, ConfigDict, Field

from options_arena.models import (
    OHLCV,
    IndicatorSignals,
    OptionContract,
    ScanRun,
    TickerScore,
)


class UniverseResult(BaseModel):
    """Phase 1 output: universe tickers + OHLCV data.

    Attributes:
        tickers: Full universe list of ticker symbols.
        ohlcv_map: Ticker to OHLCV bars mapping (successful fetches only).
        sp500_sectors: Ticker to GICS sector mapping.
        failed_count: Number of tickers that failed OHLCV fetch.
        filtered_count: Number of tickers filtered for insufficient bars.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tickers: list[str]
    ohlcv_map: dict[str, list[OHLCV]]
    sp500_sectors: dict[str, str]
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
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scores: list[TickerScore]
    raw_signals: dict[str, IndicatorSignals]


class OptionsResult(BaseModel):
    """Phase 3 output: recommended contracts + risk-free rate.

    Attributes:
        recommendations: Ticker to recommended contracts mapping (0 or 1 contracts per ticker).
        risk_free_rate: Risk-free rate used for the entire scan (from FRED or fallback).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    recommendations: dict[str, list[OptionContract]]
    risk_free_rate: float


class ScanResult(BaseModel):
    """Final pipeline output combining all phases.

    Attributes:
        scan_run: Metadata for this scan (id populated after persist).
        scores: All scored tickers with direction set.
        recommendations: Recommended contracts per ticker.
        risk_free_rate: FRED rate or fallback used for pricing.
        cancelled: True if the pipeline was cancelled mid-run.
        phases_completed: How far the pipeline progressed (0--4).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scan_run: ScanRun
    scores: list[TickerScore]
    recommendations: dict[str, list[OptionContract]]
    risk_free_rate: float
    cancelled: bool = False
    phases_completed: int = Field(default=0, ge=0, le=4)
