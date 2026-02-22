"""Scan pipeline models for Options Arena.

Three models for the scan pipeline:
  IndicatorSignals -- 18 named indicator fields replacing ``dict[str, float]``.
  ScanRun          -- metadata for a completed scan run (frozen).
  TickerScore      -- scored ticker with typed indicator signals.

``IndicatorSignals`` is NOT frozen -- it gets populated incrementally during
the scan pipeline.  All 18 fields default to ``None`` (indicator not computed).
Values are normalized 0--100 (percentile-ranked), not raw indicator values.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from options_arena.models.enums import SignalDirection


class IndicatorSignals(BaseModel):
    """18 named indicator fields.  Replaces ``dict[str, float]`` on TickerScore.

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


class ScanRun(BaseModel):
    """Metadata for a completed scan run.

    Frozen (immutable after construction) -- represents a completed scan snapshot.
    ``id`` is ``None`` until assigned by the database layer.
    ``preset`` is one of ``"full"``, ``"sp500"``, ``"etfs"``.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None  # DB-assigned
    started_at: datetime  # UTC
    completed_at: datetime | None = None
    preset: str  # "full", "sp500", "etfs"
    tickers_scanned: int
    tickers_scored: int
    recommendations: int


class TickerScore(BaseModel):
    """Scored ticker from the scan pipeline.

    NOT frozen -- direction and signals may be updated during scoring.
    ``signals`` is a typed ``IndicatorSignals`` model, NEVER ``dict[str, float]``.
    """

    ticker: str
    composite_score: float  # 0-100
    direction: SignalDirection
    signals: IndicatorSignals  # typed model, NOT dict[str, float]
    scan_run_id: int | None = None
