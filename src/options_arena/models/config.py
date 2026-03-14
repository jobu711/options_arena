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

from options_arena.models.enums import (
    LLMProvider,
)
from options_arena.models.filters import ScanFilterSpec


class ScanConfig(BaseModel):
    """Scan pipeline configuration — scoring thresholds, timeouts, toggles, and filters.

    Filter fields that previously lived directly on ``ScanConfig`` and ``PricingConfig``
    are now consolidated in ``filters: ScanFilterSpec``.  Scoring thresholds (ADX, RSI),
    concurrency controls, and feature toggles remain here.
    """

    # Direction threshold defaults are standard technical analysis values:
    # ADX < 15 = no trend (Wilder, 1978), RSI > 70 = overbought / < 30 = oversold
    # (Wilder, 1978). Widely accepted across quantitative finance (AUDIT-017).
    adx_trend_threshold: float = 15.0
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    options_per_ticker_timeout: float = 120.0
    options_concurrency: int = 5
    enable_iv_analytics: bool = True
    enable_flow_analytics: bool = True
    enable_fundamental: bool = True
    enable_regime: bool = True

    # Consolidated filter spec — all pre-scan filter fields
    filters: ScanFilterSpec = ScanFilterSpec()

    @field_validator("options_concurrency")
    @classmethod
    def validate_options_concurrency(cls, v: int) -> int:
        """Ensure options_concurrency is at least 1."""
        if v < 1:
            raise ValueError(f"options_concurrency must be >= 1, got {v}")
        return v

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class PricingConfig(BaseModel):
    """Options pricing configuration — delta targeting and IV solver parameters.

    Contract selection fields (delta ranges, DTE, OI, volume, spread) have moved
    to ``OptionsFilters`` in ``ScanFilterSpec``.  This config retains pricing math
    parameters only.
    """

    risk_free_rate_fallback: float = 0.05
    delta_target: float = 0.35
    iv_solver_tol: float = 1e-6
    iv_solver_max_iter: int = 50
    use_parity_smoothing: bool = True

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
    health_check_timeout: float = 10.0
    fred_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
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

    @model_validator(mode="after")
    def validate_timeouts_positive(self) -> Self:
        """Ensure all timeout fields are strictly positive."""
        for name in ("yfinance_timeout", "fred_timeout", "cboe_timeout", "health_check_timeout"):
            value = getattr(self, name)
            if value <= 0.0:
                raise ValueError(f"{name} must be > 0, got {value}")
        return self


class LogConfig(BaseModel):
    """Logging configuration — controls JSON mode for structured logging."""

    json_mode: bool = False


class DataConfig(BaseModel):
    """Data layer configuration — controls database path."""

    db_path: str | None = None


class DebateConfig(BaseModel):
    """AI debate configuration — controls LLM provider, timeouts, and fallback behavior.

    Supports Groq (default, free) and Anthropic (Claude) providers. Provider selection
    via ``ARENA_DEBATE__PROVIDER=anthropic`` env var or ``--provider`` CLI flag.

    Default ``agent_timeout`` (60s) is for Groq cloud inference. Override via
    ``ARENA_DEBATE__AGENT_TIMEOUT=90``, ``ARENA_DEBATE__MAX_TOTAL_DURATION=300``.
    """

    provider: LLMProvider = LLMProvider.GROQ
    model: str = "llama-3.3-70b-versatile"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    enable_extended_thinking: bool = False
    thinking_budget_tokens: int = 5000
    agent_timeout: float = 60.0
    num_ctx: int = 8192
    retries: int = 2
    temperature: float = 0.3
    fallback_confidence: float = 0.3
    max_total_duration: float = 1800.0
    min_debate_score: float = 30.0
    enable_volatility_agent: bool = False
    enable_rebuttal: bool = False
    phase1_parallelism: int = 2  # 2 for free tier, 4+ for paid Groq
    phase1_batch_delay: float = 1.0  # seconds between Phase 1 agent batches
    batch_ticker_delay: float = 5.0  # seconds between tickers in batch debate
    rate_limit_retries: int = 3  # max 429 retries at transport level (0 = disabled)
    rate_limit_max_wait: float = 30.0  # max single retry wait in seconds
    enable_regime_weights: bool = False  # opt-in regime-adjusted scoring weights
    auto_tune_weights: bool = False  # opt-in auto-tuned agent vote weights from accuracy data

    @field_validator("thinking_budget_tokens")
    @classmethod
    def validate_thinking_budget_tokens(cls, v: int) -> int:
        """Ensure thinking_budget_tokens is finite and within [1024, 128000]."""
        if not math.isfinite(v):
            raise ValueError(f"thinking_budget_tokens must be finite, got {v}")
        if not 1024 <= v <= 128_000:
            raise ValueError(f"thinking_budget_tokens must be in [1024, 128000], got {v}")
        return v

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

    @field_validator("phase1_batch_delay", "batch_ticker_delay")
    @classmethod
    def validate_non_negative_delay(cls, v: float) -> float:
        """Ensure delay values are finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"delay must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"delay must be >= 0, got {v}")
        return v

    @field_validator("rate_limit_retries")
    @classmethod
    def validate_rate_limit_retries(cls, v: int) -> int:
        """Ensure rate_limit_retries is within [0, 10]."""
        if not 0 <= v <= 10:
            raise ValueError(f"rate_limit_retries must be in [0, 10], got {v}")
        return v

    @field_validator("rate_limit_max_wait")
    @classmethod
    def validate_rate_limit_max_wait(cls, v: float) -> float:
        """Ensure rate_limit_max_wait is finite and positive."""
        if not math.isfinite(v):
            raise ValueError(f"rate_limit_max_wait must be finite, got {v}")
        if v <= 0.0:
            raise ValueError(f"rate_limit_max_wait must be > 0, got {v}")
        return v

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class IntelligenceConfig(BaseModel):
    """Intelligence data configuration — controls yfinance intelligence fetching.

    All features default to enabled. When ``enabled`` is ``False``, the entire
    intelligence integration is skipped. Individual data sources can be toggled via
    ``analyst_enabled``, ``insider_enabled``, ``institutional_enabled``, and
    ``news_fallback_enabled``.
    """

    enabled: bool = True
    analyst_enabled: bool = True
    insider_enabled: bool = True
    institutional_enabled: bool = True
    news_fallback_enabled: bool = True
    analyst_cache_ttl: int = 86400  # 24h
    insider_cache_ttl: int = 21600  # 6h
    institutional_cache_ttl: int = 86400  # 24h
    news_cache_ttl: int = 900  # 15min
    request_timeout: float = 15.0

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float config fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class AnalyticsConfig(BaseModel):
    """Analytics persistence configuration — controls outcome collection and batch sizing.

    ``holding_periods`` defines which holding periods (in trading days) to evaluate
    contract outcomes for. ``batch_size`` controls how many contracts are processed per
    batch. Outcome collection runs automatically after every successful scan.

    ``auto_collect_enabled`` activates a background scheduler that runs
    ``collect_outcomes()`` once daily at ``auto_collect_hour_utc`` (0-23 UTC).
    """

    holding_periods: list[int] = [1, 5, 10, 20]
    batch_size: int = 50
    collection_timeout: float = 120.0
    auto_collect_enabled: bool = False
    auto_collect_hour_utc: int = 6

    @field_validator("auto_collect_hour_utc")
    @classmethod
    def _validate_hour(cls, v: int) -> int:
        """Ensure auto_collect_hour_utc is within [0, 23]."""
        if not 0 <= v <= 23:
            raise ValueError("must be 0-23")
        return v

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        """Ensure batch_size is at least 1."""
        if v < 1:
            raise ValueError(f"batch_size must be >= 1, got {v}")
        return v

    @field_validator("holding_periods")
    @classmethod
    def validate_holding_periods(cls, v: list[int]) -> list[int]:
        """Ensure all holding periods are positive integers."""
        for period in v:
            if period < 1:
                raise ValueError(f"holding_period must be >= 1, got {period}")
        return v


class FinancialDatasetsConfig(BaseModel):
    """Financial Datasets AI configuration — controls optional fundamental data enrichment.

    When ``enabled`` is ``False``, the entire financialdatasets.ai integration is
    skipped. ``api_key`` is required for authenticated requests; ``None`` means
    unauthenticated (rate-limited). ``cache_ttl`` controls how long responses are
    cached (in seconds).
    """

    enabled: bool = True
    api_key: SecretStr | None = None
    base_url: str = "https://api.financialdatasets.ai"
    request_timeout: float = 10.0
    cache_ttl: int = 3600

    @field_validator("api_key", mode="before")
    @classmethod
    def normalize_blank_api_key(cls, v: object) -> object:
        """Treat blank or whitespace-only API keys as unset (None)."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("request_timeout")
    @classmethod
    def validate_request_timeout(cls, v: float) -> float:
        """Ensure request_timeout is finite and positive."""
        if not math.isfinite(v):
            raise ValueError(f"request_timeout must be finite, got {v}")
        if v <= 0.0:
            raise ValueError(f"request_timeout must be > 0, got {v}")
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
    cboe_chains_enabled: bool = True
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
    intelligence: IntelligenceConfig = IntelligenceConfig()
    analytics: AnalyticsConfig = AnalyticsConfig()
    financial_datasets: FinancialDatasetsConfig = FinancialDatasetsConfig()
