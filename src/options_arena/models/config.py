"""Configuration models for Options Arena.

AppSettings is the sole BaseSettings subclass, providing environment variable
overrides via pydantic-settings v2. Sub-configs (ScanConfig, PricingConfig,
ServiceConfig) are plain BaseModel — not BaseSettings.

Env override examples:
    ARENA_SCAN__TOP_N=30         -> settings.scan.top_n == 30
    ARENA_PRICING__DELTA_TARGET=0.40 -> settings.pricing.delta_target == 0.40
    ARENA_SERVICE__OLLAMA_HOST=http://gpu:11434 -> settings.service.ollama_host

Source priority (Context7-verified): init kwargs > env vars > field defaults.
AppSettings() with no args is a valid production config.
"""

import math

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from options_arena.models.enums import DebateProvider


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


class ServiceConfig(BaseModel):
    """External service configuration — timeouts, rate limits, cache TTLs, Ollama settings."""

    yfinance_timeout: float = 15.0
    fred_timeout: float = 10.0
    cboe_timeout: float = 10.0
    fred_api_key: str | None = None
    ollama_timeout: float = 60.0
    rate_limit_rps: float = 2.0
    max_concurrent_requests: int = 5
    cache_ttl_market_hours: int = 300
    cache_ttl_after_hours: int = 3600
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"


class DebateConfig(BaseModel):
    """AI debate configuration — controls LLM provider, timeouts, and fallback behavior.

    Supports two providers:
    - ``ollama`` (default): local Ollama server, generous CPU timeouts.
    - ``groq``: Groq cloud API, requires ``GROQ_API_KEY`` or ``ARENA_DEBATE__GROQ_API_KEY``.

    Default ``agent_timeout`` (600s) is generous for CPU-only Ollama inference (~2-5 min
    per agent response). ``groq_timeout`` (60s) is used for Groq cloud API. GPU users can
    lower via env vars: ``ARENA_DEBATE__AGENT_TIMEOUT=90``,
    ``ARENA_DEBATE__MAX_TOTAL_DURATION=300``.
    """

    provider: DebateProvider = DebateProvider.OLLAMA
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    agent_timeout: float = 600.0
    groq_timeout: float = 60.0
    groq_model: str = "llama-3.3-70b-versatile"
    groq_api_key: str | None = None
    num_ctx: int = 8192
    retries: int = 2
    temperature: float = 0.3
    fallback_confidence: float = 0.3
    max_total_duration: float = 1800.0

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is finite and within [0.0, 2.0]."""
        if not math.isfinite(v):
            raise ValueError(f"temperature must be finite, got {v}")
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"temperature must be in [0.0, 2.0], got {v}")
        return v

    @field_validator("agent_timeout", "groq_timeout", "max_total_duration")
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


class AppSettings(BaseSettings):
    """Root application settings — the sole BaseSettings subclass.

    Creates nested config from environment variables using ``ARENA_`` prefix
    and ``__`` as the nested delimiter. All defaults are production-ready;
    ``AppSettings()`` with no arguments is a valid configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",
    )

    scan: ScanConfig = ScanConfig()
    pricing: PricingConfig = PricingConfig()
    service: ServiceConfig = ServiceConfig()
    debate: DebateConfig = DebateConfig()
