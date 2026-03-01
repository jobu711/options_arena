"""Configuration models for Options Arena.

AppSettings is the sole BaseSettings subclass, providing environment variable
overrides via pydantic-settings v2. Sub-configs (ScanConfig, PricingConfig,
ServiceConfig) are plain BaseModel — not BaseSettings.

Env override examples:
    ARENA_SCAN__TOP_N=30         -> settings.scan.top_n == 30
    ARENA_PRICING__DELTA_TARGET=0.40 -> settings.pricing.delta_target == 0.40
    ARENA_DEBATE__API_KEY=gsk_... -> settings.debate.api_key

Source priority (Context7-verified): init kwargs > env vars > field defaults.
AppSettings() with no args is a valid production config.
"""

import math
from typing import Self

from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanConfig(BaseModel):
    """Scan pipeline configuration — controls universe filtering and scoring thresholds."""

    top_n: int = 50
    min_score: float = 0.0
    min_price: float = 10.0
    min_dollar_volume: float = 10_000_000.0
    ohlcv_min_bars: int = 200
    adx_trend_threshold: float = 15.0
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    options_per_ticker_timeout: float = 120.0
    options_batch_size: int = 5
    enable_iv_analytics: bool = True
    enable_flow_analytics: bool = True
    enable_fundamental: bool = True
    enable_regime: bool = True

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class PricingConfig(BaseModel):
    """Options pricing configuration — delta targeting, DTE range, IV solver parameters."""

    risk_free_rate_fallback: float = 0.05
    delta_primary_min: float = 0.20
    delta_primary_max: float = 0.50
    delta_fallback_min: float = 0.10
    delta_fallback_max: float = 0.80
    delta_target: float = 0.35
    dte_min: int = 30
    dte_max: int = 365
    min_oi: int = 100
    min_volume: int = 1
    max_spread_pct: float = 0.30
    iv_solver_tol: float = 1e-6
    iv_solver_max_iter: int = 50

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class ServiceConfig(BaseModel):
    """External service configuration — timeouts, rate limits, cache TTLs."""

    yfinance_timeout: float = 15.0
    fred_timeout: float = 10.0
    cboe_timeout: float = 10.0
    fred_api_key: str | None = None
    groq_api_key: str | None = None
    rate_limit_rps: float = 2.0
    max_concurrent_requests: int = 5
    cache_ttl_market_hours: int = 300
    cache_ttl_after_hours: int = 3600

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class DataConfig(BaseModel):
    """Data layer configuration — controls database path."""

    db_path: str | None = None


class DebateConfig(BaseModel):
    """AI debate configuration — controls Groq LLM, timeouts, and fallback behavior.

    Uses Groq cloud API exclusively. Requires ``GROQ_API_KEY`` or
    ``ARENA_DEBATE__API_KEY`` env var.

    Default ``agent_timeout`` (60s) is for Groq cloud inference. Override via
    ``ARENA_DEBATE__AGENT_TIMEOUT=90``, ``ARENA_DEBATE__MAX_TOTAL_DURATION=300``.
    """

    model: str = "llama-3.3-70b-versatile"
    api_key: str | None = None
    agent_timeout: float = 60.0
    num_ctx: int = 8192
    retries: int = 2
    temperature: float = 0.3
    fallback_confidence: float = 0.3
    max_total_duration: float = 1800.0
    min_debate_score: float = 30.0
    enable_volatility_agent: bool = False
    enable_rebuttal: bool = False
    phase1_parallelism: int = 4  # 4 for paid Groq, 2 for free tier
    enable_regime_weights: bool = False  # opt-in regime-adjusted scoring weights

    @field_validator("min_debate_score")
    @classmethod
    def validate_min_debate_score(cls, v: float) -> float:
        """Ensure min_debate_score is finite and within [0.0, 100.0]."""
        if not math.isfinite(v):
            raise ValueError(f"min_debate_score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"min_debate_score must be in [0.0, 100.0], got {v}")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is finite and within [0.0, 2.0]."""
        if not math.isfinite(v):
            raise ValueError(f"temperature must be finite, got {v}")
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"temperature must be in [0.0, 2.0], got {v}")
        return v

    @field_validator("agent_timeout", "max_total_duration")
    @classmethod
    def validate_positive_timeout(cls, v: float) -> float:
        """Ensure timeout values are finite and positive."""
        if not math.isfinite(v):
            raise ValueError(f"timeout must be finite, got {v}")
        if v <= 0.0:
            raise ValueError(f"timeout must be > 0, got {v}")
        return v

    @field_validator("fallback_confidence")
    @classmethod
    def validate_fallback_confidence(cls, v: float) -> float:
        """Ensure fallback_confidence is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"fallback_confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"fallback_confidence must be in [0, 1], got {v}")
        return v

    @field_validator("num_ctx")
    @classmethod
    def validate_num_ctx(cls, v: int) -> int:
        """Ensure num_ctx is within reasonable bounds."""
        if not 128 <= v <= 131_072:
            raise ValueError(f"num_ctx must be in [128, 131072], got {v}")
        return v

    @field_validator("retries")
    @classmethod
    def validate_retries(cls, v: int) -> int:
        """Ensure retries is within [0, 5]."""
        if not 0 <= v <= 5:
            raise ValueError(f"retries must be in [0, 5], got {v}")
        return v

    @field_validator("phase1_parallelism")
    @classmethod
    def validate_phase1_parallelism(cls, v: int) -> int:
        """Ensure phase1_parallelism is within [1, 8]."""
        if not 1 <= v <= 8:
            raise ValueError(f"phase1_parallelism must be in [1, 8], got {v}")
        return v


class AppSettings(BaseSettings):
    """Root application settings — the sole BaseSettings subclass.

    Creates nested config from environment variables using ``ARENA_`` prefix
    and ``__`` as the nested delimiter. All defaults are production-ready;
    ``AppSettings()`` with no arguments is a valid configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    scan: ScanConfig = ScanConfig()
    pricing: PricingConfig = PricingConfig()
    service: ServiceConfig = ServiceConfig()
    debate: DebateConfig = DebateConfig()
    data: DataConfig = DataConfig()
