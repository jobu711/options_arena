"""Tests for TickerMetadata and MetadataCoverage Pydantic models."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.enums import GICSIndustryGroup, GICSSector, MarketCapTier
from options_arena.models.metadata import MetadataCoverage, TickerMetadata

# ---------------------------------------------------------------------------
# TickerMetadata
# ---------------------------------------------------------------------------


class TestTickerMetadata:
    """Tests for the TickerMetadata model."""

    def test_frozen_model(self) -> None:
        """TickerMetadata is frozen (immutable after construction)."""
        meta = TickerMetadata(
            ticker="AAPL",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            last_updated=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        )
        with pytest.raises(ValidationError):
            meta.ticker = "MSFT"  # type: ignore[misc]

    def test_utc_validator_rejects_naive(self) -> None:
        """TickerMetadata rejects naive datetime (no tzinfo)."""
        with pytest.raises(ValidationError, match="UTC"):
            TickerMetadata(
                ticker="AAPL",
                last_updated=datetime(2026, 3, 5, 12, 0),
            )

    def test_utc_validator_rejects_non_utc(self) -> None:
        """TickerMetadata rejects non-UTC timezone."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            TickerMetadata(
                ticker="AAPL",
                last_updated=datetime(2026, 3, 5, 12, 0, tzinfo=est),
            )

    def test_utc_validator_accepts_utc(self) -> None:
        """TickerMetadata accepts UTC datetime."""
        ts = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
        meta = TickerMetadata(ticker="AAPL", last_updated=ts)
        assert meta.last_updated == ts

    def test_json_roundtrip(self) -> None:
        """TickerMetadata survives JSON serialization roundtrip."""
        meta = TickerMetadata(
            ticker="MSFT",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            industry_group=GICSIndustryGroup.SOFTWARE_SERVICES,
            market_cap_tier=MarketCapTier.MEGA,
            company_name="Microsoft Corporation",
            raw_sector="Technology",
            raw_industry="Software—Infrastructure",
            last_updated=datetime(2026, 3, 5, 10, 30, tzinfo=UTC),
        )
        loaded = TickerMetadata.model_validate_json(meta.model_dump_json())
        assert loaded == meta

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None when not provided."""
        meta = TickerMetadata(
            ticker="XYZ",
            last_updated=datetime(2026, 3, 5, tzinfo=UTC),
        )
        assert meta.sector is None
        assert meta.industry_group is None
        assert meta.market_cap_tier is None
        assert meta.company_name is None

    def test_enum_serialization(self) -> None:
        """Enum fields serialize and deserialize correctly."""
        meta = TickerMetadata(
            ticker="AAPL",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            industry_group=GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
            market_cap_tier=MarketCapTier.MEGA,
            last_updated=datetime(2026, 3, 5, tzinfo=UTC),
        )
        dumped = meta.model_dump()
        assert dumped["sector"] == "Information Technology"
        assert dumped["industry_group"] == "Technology Hardware & Equipment"
        assert dumped["market_cap_tier"] == "mega"

        loaded = TickerMetadata.model_validate_json(meta.model_dump_json())
        assert loaded.sector is GICSSector.INFORMATION_TECHNOLOGY
        assert loaded.industry_group is GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT
        assert loaded.market_cap_tier is MarketCapTier.MEGA

    def test_raw_fields_preserve_free_text(self) -> None:
        """raw_sector and raw_industry store arbitrary strings."""
        meta = TickerMetadata(
            ticker="AAPL",
            raw_sector="Technology",
            raw_industry="Consumer Electronics",
            last_updated=datetime(2026, 3, 5, tzinfo=UTC),
        )
        assert meta.raw_sector == "Technology"
        assert meta.raw_industry == "Consumer Electronics"

    def test_raw_fields_default_unknown(self) -> None:
        """raw_sector and raw_industry default to 'Unknown'."""
        meta = TickerMetadata(
            ticker="XYZ",
            last_updated=datetime(2026, 3, 5, tzinfo=UTC),
        )
        assert meta.raw_sector == "Unknown"
        assert meta.raw_industry == "Unknown"


# ---------------------------------------------------------------------------
# MetadataCoverage
# ---------------------------------------------------------------------------


class TestMetadataCoverage:
    """Tests for the MetadataCoverage model."""

    def test_metadata_coverage_model(self) -> None:
        """MetadataCoverage constructs with valid data."""
        cov = MetadataCoverage(
            total=500,
            with_sector=480,
            with_industry_group=450,
            coverage=0.96,
        )
        assert cov.total == 500
        assert cov.with_sector == 480
        assert cov.with_industry_group == 450
        assert cov.coverage == pytest.approx(0.96)

    def test_metadata_coverage_frozen(self) -> None:
        """MetadataCoverage is frozen (immutable)."""
        cov = MetadataCoverage(
            total=100,
            with_sector=90,
            with_industry_group=80,
            coverage=0.90,
        )
        with pytest.raises(ValidationError):
            cov.total = 200  # type: ignore[misc]

    def test_metadata_coverage_json_roundtrip(self) -> None:
        """MetadataCoverage survives JSON roundtrip."""
        cov = MetadataCoverage(
            total=500,
            with_sector=480,
            with_industry_group=450,
            coverage=0.96,
        )
        loaded = MetadataCoverage.model_validate_json(cov.model_dump_json())
        assert loaded == cov
