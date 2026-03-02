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

from pydantic import BaseModel, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from options_arena.models.enums import SECTOR_ALIASES, GICSSector


class ScanConfig(BaseModel):
    """Scan pipeline configuration — controls universe filtering and scoring thresholds."""

    top_n: int = 50
    min_score: float = 0.0
    min_price: float = 10.0
    min_dollar_volume: float = 10_000_000.0
    ohlcv_min_bars: int = 200
    # Direction threshold defaults are standard technical analysis values:
    # ADX < 15 = no trend (Wilder, 1978), RSI > 70 = overbought / < 30 = oversold
    # (Wilder, 1978). Widely accepted across quantitative finance (AUDIT-017).
    adx_trend_threshold: float = 15.0
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    options_per_ticker_timeout: float = 120.0
    options_batch_size: int = 5
    options_concurrency: int = 5
    enable_iv_analytics: bool = True
    enable_flow_analytics: bool = True
    enable_fundamental: bool = True
    enable_regime: bool = True
    sectors: list[GICSSector] = []

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        """Ensure top_n is at least 1."""
        if v < 1:
            raise ValueError(f"top_n must be >= 1, got {v}")
        return v

    @field_validator("ohlcv_min_bars")
    @classmethod
    def validate_ohlcv_min_bars(cls, v: int) -> int:
        """Ensure ohlcv_min_bars is at least 5."""
        if v < 5:
            raise ValueError(f"ohlcv_min_bars must be >= 5, got {v}")
        return v

    @field_validator("options_concurrency")
    @classmethod
    def validate_options_concurrency(cls, v: int) -> int:
        """Ensure options_concurrency is at least 1."""
        if v < 1:
            raise ValueError(f"options_concurrency must be >= 1, got {v}")
        return v

    @field_validator("sectors", mode="before")
    @classmethod
    def normalize_sectors(cls, v: list[str | GICSSector]) -> list[GICSSector]:
        """Normalize sector input strings via SECTOR_ALIASES.

        Accepts canonical enum values, lowercase names, hyphenated, underscored,
        and short-name variants. Raises ValueError for unrecognised inputs.
        """
        result: list[GICSSector] = []
        for item in v:
            if isinstance(item, GICSSector):
                result.append(item)
                continue
            # Normalize: lowercase, strip whitespace
            key = str(item).strip().lower()
            if key in SECTOR_ALIASES:
                result.append(SECTOR_ALIASES[key])
            else:
                # Try direct enum construction (handles canonical values)
                try:
                    result.append(GICSSector(str(item).strip()))
                except ValueError:
                    valid = sorted({s.value for s in GICSSector})
                    raise ValueError(
                        f"Unknown sector {item!r}. Valid sectors: {', '.join(valid)}"
                    ) from None
        return list(dict.fromkeys(result))

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
    fred_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
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


class LogConfig(BaseModel):
    """Logging configuration — controls JSON mode for structured logging."""

    json_mode: bool = False


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
    api_key: SecretStr | None = None
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

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class OpenBBConfig(BaseModel):
    """OpenBB Platform SDK configuration — controls optional enrichment data.

    All features default to enabled. When ``enabled`` is ``False``, the entire
    OpenBB integration is skipped. Individual data sources can be toggled via
    ``fundamentals_enabled``, ``unusual_flow_enabled``, and ``news_sentiment_enabled``.
    """

    enabled: bool = True
    fundamentals_enabled: bool = True
    unusual_flow_enabled: bool = True
    news_sentiment_enabled: bool = True
    fundamentals_cache_ttl: int = 3600
    flow_cache_ttl: int = 300
    news_cache_ttl: int = 900
    request_timeout: int = 15
    max_retries: int = 2
    cboe_chains_enabled: bool = False
    chains_cache_ttl: int = 60
    chain_validation_mode: bool = False


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
    log: LogConfig = LogConfig()
    openbb: OpenBBConfig = OpenBBConfig()
