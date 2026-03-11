"""Pre-scan filter models for pipeline phase control.

Four frozen Pydantic v2 models that decouple filter configuration from the
monolithic ``ScanConfig`` / ``PricingConfig``. Each model corresponds to a
pipeline phase:

- ``UniverseFilters``  — Phase 1 (universe selection)
- ``ScoringFilters``   — post-Phase 2 (scoring thresholds)
- ``OptionsFilters``   — Phase 3 (option chain filters)
- ``ScanFilterSpec``   — composite container for all three
"""

import math
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from options_arena.models.config import TICKER_RE
from options_arena.models.enums import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
)


class UniverseFilters(BaseModel):
    """Phase 1 universe selection filters — controls which tickers enter the pipeline."""

    model_config = ConfigDict(frozen=True)

    preset: ScanPreset = ScanPreset.SP500
    sectors: list[GICSSector] = []
    industry_groups: list[GICSIndustryGroup] = []
    custom_tickers: list[str] = []
    market_cap_tiers: list[MarketCapTier] = []
    ohlcv_min_bars: int = 200
    min_price: float = 10.0
    max_price: float | None = None

    @field_validator("sectors", mode="before")
    @classmethod
    def normalize_sectors(cls, v: list[str | GICSSector]) -> list[GICSSector]:
        """Normalize sector input strings via SECTOR_ALIASES, deduplicate."""
        result: list[GICSSector] = []
        for item in v:
            if isinstance(item, GICSSector):
                result.append(item)
                continue
            key = str(item).strip().lower()
            if key in SECTOR_ALIASES:
                result.append(SECTOR_ALIASES[key])
            else:
                try:
                    result.append(GICSSector(str(item).strip()))
                except ValueError:
                    valid = sorted({s.value for s in GICSSector})
                    raise ValueError(
                        f"Unknown sector {item!r}. Valid sectors: {', '.join(valid)}"
                    ) from None
        return list(dict.fromkeys(result))

    @field_validator("industry_groups", mode="before")
    @classmethod
    def normalize_industry_groups(
        cls, v: list[str | GICSIndustryGroup]
    ) -> list[GICSIndustryGroup]:
        """Normalize industry group input strings via INDUSTRY_GROUP_ALIASES, deduplicate."""
        result: list[GICSIndustryGroup] = []
        for item in v:
            if isinstance(item, GICSIndustryGroup):
                result.append(item)
                continue
            key = str(item).strip().lower()
            if key in INDUSTRY_GROUP_ALIASES:
                result.append(INDUSTRY_GROUP_ALIASES[key])
            else:
                try:
                    result.append(GICSIndustryGroup(str(item).strip()))
                except ValueError:
                    valid = sorted({g.value for g in GICSIndustryGroup})
                    raise ValueError(
                        f"Unknown industry group {item!r}. Valid groups: {', '.join(valid)}"
                    ) from None
        return list(dict.fromkeys(result))

    @field_validator("custom_tickers", mode="before")
    @classmethod
    def validate_custom_tickers(cls, v: list[str]) -> list[str]:
        """Uppercase, strip, validate format, deduplicate, and cap at 200."""
        result: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError(f"each custom ticker must be a string, got {type(item).__name__}")
            normalized = item.upper().strip()
            if not TICKER_RE.match(normalized):
                raise ValueError(
                    f"Invalid ticker format: {normalized!r}. "
                    "Must be 1-10 characters: A-Z, 0-9, dots, hyphens, or caret."
                )
            result.append(normalized)
        result = list(dict.fromkeys(result))
        if len(result) > 200:
            raise ValueError(f"custom_tickers exceeds 200 tickers ({len(result)})")
        return result

    @field_validator("market_cap_tiers", mode="before")
    @classmethod
    def deduplicate_market_cap_tiers(
        cls,
        v: list[str | MarketCapTier],
    ) -> list[MarketCapTier]:
        """Deduplicate market cap tier inputs."""
        result: list[MarketCapTier] = []
        for item in v:
            if isinstance(item, MarketCapTier):
                result.append(item)
            else:
                result.append(MarketCapTier(str(item).strip().lower()))
        return list(dict.fromkeys(result))

    @field_validator("ohlcv_min_bars")
    @classmethod
    def validate_ohlcv_min_bars(cls, v: int) -> int:
        """Ensure ohlcv_min_bars is at least 5."""
        if v < 5:
            raise ValueError(f"ohlcv_min_bars must be >= 5, got {v}")
        return v

    @field_validator("min_price")
    @classmethod
    def validate_min_price(cls, v: float) -> float:
        """Ensure min_price is finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"min_price must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"min_price must be >= 0, got {v}")
        return v

    @field_validator("max_price")
    @classmethod
    def validate_max_price(cls, v: float | None) -> float | None:
        """Ensure max_price is finite and positive when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"max_price must be finite, got {v}")
            if v <= 0.0:
                raise ValueError(f"max_price must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        """Reject min_price > max_price when both are set."""
        if self.max_price is not None and self.min_price > self.max_price:
            raise ValueError(
                f"min_price ({self.min_price}) must not exceed max_price ({self.max_price})"
            )
        return self

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class ScoringFilters(BaseModel):
    """Post-Phase 2 scoring threshold filters."""

    model_config = ConfigDict(frozen=True)

    direction_filter: SignalDirection | None = None
    min_score: float = 0.0
    min_direction_confidence: float = 0.0

    @field_validator("min_score")
    @classmethod
    def validate_min_score(cls, v: float) -> float:
        """Ensure min_score is finite and in [0.0, 100.0]."""
        if not math.isfinite(v):
            raise ValueError(f"min_score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"min_score must be in [0.0, 100.0], got {v}")
        return v

    @field_validator("min_direction_confidence")
    @classmethod
    def validate_min_direction_confidence(cls, v: float) -> float:
        """Ensure min_direction_confidence is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"min_direction_confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"min_direction_confidence must be in [0.0, 1.0], got {v}")
        return v

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class OptionsFilters(BaseModel):
    """Phase 3 option chain selection filters."""

    model_config = ConfigDict(frozen=True)

    top_n: int = 50
    min_dollar_volume: float = 10_000_000.0
    min_dte: int = 30
    max_dte: int = 365
    exclude_near_earnings_days: int | None = None
    min_iv_rank: float | None = None
    min_oi: int = 100
    min_volume: int = 1
    max_spread_pct: float = 30.0
    delta_primary_min: float = 0.20
    delta_primary_max: float = 0.50
    delta_fallback_min: float = 0.10
    delta_fallback_max: float = 0.80

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        """Ensure top_n is at least 1."""
        if v < 1:
            raise ValueError(f"top_n must be >= 1, got {v}")
        return v

    @field_validator("min_dollar_volume")
    @classmethod
    def validate_min_dollar_volume(cls, v: float) -> float:
        """Ensure min_dollar_volume is finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"min_dollar_volume must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"min_dollar_volume must be >= 0, got {v}")
        return v

    @field_validator("min_dte")
    @classmethod
    def validate_min_dte(cls, v: int) -> int:
        """Ensure min_dte is non-negative."""
        if v < 0:
            raise ValueError(f"min_dte must be >= 0, got {v}")
        return v

    @field_validator("max_dte")
    @classmethod
    def validate_max_dte(cls, v: int) -> int:
        """Ensure max_dte is at least 1."""
        if v < 1:
            raise ValueError(f"max_dte must be >= 1, got {v}")
        return v

    @field_validator("min_oi")
    @classmethod
    def validate_min_oi(cls, v: int) -> int:
        """Ensure min_oi is non-negative."""
        if v < 0:
            raise ValueError(f"min_oi must be >= 0, got {v}")
        return v

    @field_validator("min_volume")
    @classmethod
    def validate_min_volume(cls, v: int) -> int:
        """Ensure min_volume is non-negative."""
        if v < 0:
            raise ValueError(f"min_volume must be >= 0, got {v}")
        return v

    @field_validator("max_spread_pct")
    @classmethod
    def validate_max_spread_pct(cls, v: float) -> float:
        """Ensure max_spread_pct is finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"max_spread_pct must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"max_spread_pct must be >= 0, got {v}")
        return v

    @field_validator("min_iv_rank")
    @classmethod
    def validate_min_iv_rank(cls, v: float | None) -> float | None:
        """Ensure min_iv_rank is within [0, 100] if set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"min_iv_rank must be finite, got {v}")
            if not 0.0 <= v <= 100.0:
                raise ValueError(f"min_iv_rank must be in [0, 100], got {v}")
        return v

    @field_validator(
        "delta_primary_min",
        "delta_primary_max",
        "delta_fallback_min",
        "delta_fallback_max",
    )
    @classmethod
    def validate_delta_field(cls, v: float) -> float:
        """Ensure delta fields are finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"delta must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"delta must be in [0.0, 1.0], got {v}")
        return v

    @model_validator(mode="after")
    def validate_cross_field_ranges(self) -> Self:
        """Reject invalid cross-field relationships."""
        if self.min_dte > self.max_dte:
            raise ValueError(f"min_dte ({self.min_dte}) must not exceed max_dte ({self.max_dte})")
        if self.delta_primary_min > self.delta_primary_max:
            raise ValueError(
                f"delta_primary_min ({self.delta_primary_min}) must not exceed "
                f"delta_primary_max ({self.delta_primary_max})"
            )
        if self.delta_fallback_min > self.delta_fallback_max:
            raise ValueError(
                f"delta_fallback_min ({self.delta_fallback_min}) must not exceed "
                f"delta_fallback_max ({self.delta_fallback_max})"
            )
        if self.delta_primary_min < self.delta_fallback_min:
            raise ValueError(
                f"delta_primary_min ({self.delta_primary_min}) must be >= "
                f"delta_fallback_min ({self.delta_fallback_min})"
            )
        if self.delta_primary_max > self.delta_fallback_max:
            raise ValueError(
                f"delta_primary_max ({self.delta_primary_max}) must be <= "
                f"delta_fallback_max ({self.delta_fallback_max})"
            )
        return self

    @model_validator(mode="after")
    def validate_all_finite(self) -> Self:
        """Reject NaN/Inf on all float fields (defense-in-depth)."""
        for name, value in self.__dict__.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        return self


class ScanFilterSpec(BaseModel):
    """Composite container for all scan pipeline filters."""

    model_config = ConfigDict(frozen=True)

    universe: UniverseFilters = UniverseFilters()
    scoring: ScoringFilters = ScoringFilters()
    options: OptionsFilters = OptionsFilters()
