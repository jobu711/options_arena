"""Scan pipeline models for Options Arena.

Three models for the scan pipeline:
  IndicatorSignals -- 65 named indicator fields replacing ``dict[str, float]``.
  ScanRun          -- metadata for a completed scan run (frozen).
  TickerScore      -- scored ticker with typed indicator signals.

``IndicatorSignals`` is NOT frozen -- it gets populated incrementally during
the scan pipeline.  All fields default to ``None`` (indicator not computed).
Values are normalized 0--100 (percentile-ranked), not raw indicator values.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from options_arena.models.enums import (
    GICSIndustryGroup,
    GICSSector,
    MarketRegime,
    ScanPreset,
    ScanSource,
    SignalDirection,
)
from options_arena.models.scoring import DimensionalScores


class IndicatorSignals(BaseModel):
    """68 named indicator fields (18 + 1 MACD + 40 DSE + 2 liq + 4 quant + 3 surface).

    Replaces ``dict[str, float]`` on TickerScore.

    All fields are ``float | None`` -- ``None`` means the indicator could not be
    computed for this ticker (insufficient data, error, etc.).

    NOT frozen: populated incrementally during the scan pipeline.
    ``IndicatorSignals()`` with no arguments must succeed (all None).
    """

    # Oscillators
    rsi: float | None = None
    stochastic_rsi: float | None = None
    williams_r: float | None = None

    # Trend
    adx: float | None = None
    roc: float | None = None
    supertrend: float | None = None
    macd: float | None = None

    # Volatility
    bb_width: float | None = None
    atr_pct: float | None = None
    keltner_width: float | None = None

    # Volume
    obv: float | None = None
    ad: float | None = None
    relative_volume: float | None = None

    # Moving Averages
    sma_alignment: float | None = None
    vwap_deviation: float | None = None

    # Options-specific
    iv_rank: float | None = None
    iv_percentile: float | None = None
    put_call_ratio: float | None = None
    max_pain_distance: float | None = None

    # --- DSE: IV Volatility (13 new) ---
    iv_hv_spread: float | None = None
    hv_20d: float | None = None
    iv_term_slope: float | None = None
    iv_term_shape: float | None = None  # stored as float for normalized score
    put_skew_index: float | None = None
    call_skew_index: float | None = None
    skew_ratio: float | None = None
    vol_regime: float | None = None  # stored as float for normalized score
    ewma_vol_forecast: float | None = None
    vol_cone_percentile: float | None = None
    vix_correlation: float | None = None
    expected_move: float | None = None
    expected_move_ratio: float | None = None

    # --- DSE: Flow & OI (5 new) ---
    gex: float | None = None
    oi_concentration: float | None = None
    unusual_activity_score: float | None = None
    max_pain_magnet: float | None = None
    dollar_volume_trend: float | None = None

    # --- DSE: Second-Order Greeks (3 new) ---
    vanna: float | None = None
    charm: float | None = None
    vomma: float | None = None

    # --- DSE: Risk (4 new) ---
    pop: float | None = None
    optimal_dte_score: float | None = None
    spread_quality: float | None = None
    max_loss_ratio: float | None = None

    # --- DSE: Trend Extensions (3 new) ---
    multi_tf_alignment: float | None = None
    rsi_divergence: float | None = None
    adx_exhaustion: float | None = None

    # --- DSE: Relative Strength (1 new) ---
    rs_vs_spx: float | None = None

    # --- DSE: Fundamental (5 new) ---
    earnings_em_ratio: float | None = None
    days_to_earnings_impact: float | None = None
    short_interest_ratio: float | None = None
    div_ex_date_impact: float | None = None
    iv_crush_history: float | None = None

    # --- DSE: Regime & Macro (5 new) ---
    market_regime: float | None = None  # stored as float for normalized score
    vix_term_structure: float | None = None
    risk_on_off_score: float | None = None
    sector_relative_momentum: float | None = None
    correlation_regime_shift: float | None = None

    # --- DSE: Microstructure (3 new) ---
    volume_profile_skew: float | None = None
    chain_spread_pct: float | None = None  # OI-weighted avg spread as % points (0.0–30.0)
    chain_oi_depth: float | None = None  # log10(total_oi + 1), range 0.0–6.0

    # --- Native Quant: HV & Vol Surface (4 new) ---
    hv_yang_zhang: float | None = None  # Yang-Zhang historical volatility (annualized)
    skew_25d: float | None = None  # 25-delta skew (put IV - call IV)
    smile_curvature: float | None = None  # butterfly spread curvature measure
    prob_above_current: float | None = None  # risk-neutral probability of spot > current price

    # --- Volatility Intelligence: Surface Mispricing (3 new) ---
    iv_surface_residual: float | None = None
    surface_fit_r2: float | None = None
    surface_is_1d: float | None = None  # 0.0=2D, 1.0=1D (stored as float for normalization)

    # --- Regime Detection ---
    hurst_exponent: float | None = None  # Hurst exponent via R/S analysis [0, 1]

    @model_validator(mode="before")
    @classmethod
    def _normalize_non_finite(cls, data: dict[str, object]) -> dict[str, object]:
        """Replace NaN/Inf indicator values with None at the model boundary.

        Returns a shallow copy to avoid mutating the caller's input dict.
        """
        if isinstance(data, dict):
            data = {
                k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                for k, v in data.items()
            }
        return data


class ScanRun(BaseModel):
    """Metadata for a completed scan run.

    Frozen (immutable after construction) -- represents a completed scan snapshot.
    ``id`` is ``None`` until assigned by the database layer.
    ``preset`` is a ``ScanPreset`` enum: ``FULL``, ``SP500``, or ``ETFS``.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None  # DB-assigned
    started_at: datetime  # UTC
    completed_at: datetime | None = None
    preset: ScanPreset
    source: ScanSource = ScanSource.MANUAL
    tickers_scanned: int
    tickers_scored: int
    recommendations: int
    filter_spec_json: str | None = None  # ScanFilterSpec JSON for reproducibility

    @field_validator("tickers_scanned", "tickers_scored", "recommendations")
    @classmethod
    def validate_counts_non_negative(cls, v: int) -> int:
        """Ensure count fields are non-negative."""
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_utc(cls, v: datetime | None) -> datetime | None:
        """Ensure timestamps are UTC."""
        if v is not None and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("timestamp must be UTC")
        return v


class TickerScore(BaseModel):
    """Scored ticker from the scan pipeline.

    NOT frozen -- direction and signals may be updated during scoring.
    ``signals`` is a typed ``IndicatorSignals`` model, NEVER ``dict[str, float]``.
    """

    ticker: str
    composite_score: float  # 0-100
    direction: SignalDirection

    @field_validator("composite_score")
    @classmethod
    def validate_composite_score_bounds(cls, v: float) -> float:
        """Ensure composite_score is finite and within [0, 100]."""
        if not math.isfinite(v) or not 0.0 <= v <= 100.0:
            raise ValueError(f"composite_score must be in [0, 100], got {v}")
        return v

    signals: IndicatorSignals  # typed model, NOT dict[str, float]
    sector: GICSSector | None = None  # GICS sector from S&P 500 constituents
    company_name: str | None = None  # from TickerInfo.company_name
    next_earnings: date | None = None  # populated in Phase 3 from yfinance calendar
    scan_run_id: int | None = None

    # GICS industry group (finer-grained than sector)
    industry_group: GICSIndustryGroup | None = None

    # DSE dimensional scoring (populated after score_universe in Phase 2)
    dimensional_scores: DimensionalScores | None = None
    direction_confidence: float | None = None
    market_regime: MarketRegime | None = None

    @field_validator("direction_confidence")
    @classmethod
    def validate_direction_confidence(cls, v: float | None) -> float | None:
        """Ensure direction_confidence is finite and within [0.0, 1.0] when set."""
        if v is not None and (not math.isfinite(v) or not 0.0 <= v <= 1.0):
            raise ValueError(f"direction_confidence must be in [0, 1], got {v}")
        return v
