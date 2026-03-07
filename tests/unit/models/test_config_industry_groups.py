"""Unit tests for ScanConfig.industry_groups.

Tests:
  - Default empty list for industry_groups
  - Normalization via INDUSTRY_GROUP_ALIASES (lowercase, short, hyphenated, underscored)
  - Deduplication after alias normalization
  - Invalid group raises ValueError
  - Mixed enum + string inputs
  - TickerScore new fields (industry_group)
"""

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AppSettings,
    GICSIndustryGroup,
    ScanConfig,
    TickerScore,
)
from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals

# ---------------------------------------------------------------------------
# Helper: list of ARENA_* env var names we might need to clean
# ---------------------------------------------------------------------------
_ARENA_ENV_VARS = [
    "ARENA_SCAN__TOP_N",
    "ARENA_SCAN__INDUSTRY_GROUPS",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ARENA_* env vars before each test to prevent cross-contamination."""
    for var in _ARENA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# ScanConfig.industry_groups
# ---------------------------------------------------------------------------


class TestScanConfigIndustryGroups:
    def test_default_empty(self) -> None:
        """Verify industry_groups defaults to empty list."""
        config = ScanConfig()
        assert config.industry_groups == []

    def test_accepts_canonical_enum_values(self) -> None:
        """Canonical GICSIndustryGroup enum instances pass through."""
        config = ScanConfig(
            industry_groups=[
                GICSIndustryGroup.SOFTWARE_SERVICES,
                GICSIndustryGroup.BANKS,
            ]
        )
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.BANKS,
        ]

    def test_normalize_from_strings(self) -> None:
        """Verify string inputs normalized via INDUSTRY_GROUP_ALIASES."""
        config = ScanConfig(industry_groups=["software", "banks", "pharma"])
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.BANKS,
            GICSIndustryGroup.PHARMA_BIOTECH,
        ]

    def test_normalize_lowercase_canonical(self) -> None:
        """Lowercase canonical names resolve correctly."""
        config = ScanConfig(industry_groups=["software & services", "capital goods"])
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.CAPITAL_GOODS,
        ]

    def test_normalize_hyphenated(self) -> None:
        """Hyphenated variants resolve correctly."""
        config = ScanConfig(industry_groups=["software-services", "semiconductors-equipment"])
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        ]

    def test_normalize_underscored(self) -> None:
        """Underscored variants resolve correctly."""
        config = ScanConfig(industry_groups=["software_services", "capital_goods"])
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.CAPITAL_GOODS,
        ]

    def test_accepts_canonical_string_values(self) -> None:
        """Canonical string values (mixed case) resolve via enum constructor."""
        config = ScanConfig(industry_groups=["Software & Services", "Banks"])
        assert config.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.BANKS,
        ]

    def test_deduplication(self) -> None:
        """Verify duplicate groups removed after alias normalization."""
        config = ScanConfig(
            industry_groups=["software", "Software & Services", "software_services"]
        )
        assert config.industry_groups == [GICSIndustryGroup.SOFTWARE_SERVICES]

    def test_deduplication_preserves_order(self) -> None:
        """Verify deduplication keeps first occurrence order."""
        config = ScanConfig(industry_groups=["banks", "software", "banks"])
        assert config.industry_groups == [
            GICSIndustryGroup.BANKS,
            GICSIndustryGroup.SOFTWARE_SERVICES,
        ]

    def test_invalid_group_raises(self) -> None:
        """Verify ValueError for unknown industry group."""
        with pytest.raises(ValidationError, match="Unknown industry group"):
            ScanConfig(industry_groups=["nonexistent_industry_group"])

    def test_mixed_enum_and_string(self) -> None:
        """Mix of GICSIndustryGroup enums and alias strings works."""
        config = ScanConfig(industry_groups=[GICSIndustryGroup.BANKS, "semiconductors"])
        assert config.industry_groups == [
            GICSIndustryGroup.BANKS,
            GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        ]

    def test_yfinance_industry_string(self) -> None:
        """Verify yfinance industry string resolves correctly."""
        config = ScanConfig(industry_groups=["biotechnology", "auto manufacturers"])
        assert config.industry_groups == [
            GICSIndustryGroup.PHARMA_BIOTECH,
            GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
        ]

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_SCAN__INDUSTRY_GROUPS env var works via JSON string."""
        monkeypatch.setenv("ARENA_SCAN__INDUSTRY_GROUPS", '["software","banks"]')
        settings = AppSettings()
        assert settings.scan.industry_groups == [
            GICSIndustryGroup.SOFTWARE_SERVICES,
            GICSIndustryGroup.BANKS,
        ]


# ---------------------------------------------------------------------------
# TickerScore new fields
# ---------------------------------------------------------------------------


class TestTickerScoreNewFields:
    def test_industry_group_defaults_to_none(self) -> None:
        """Verify industry_group defaults to None."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=75.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert score.industry_group is None

    def test_industry_group_accepts_string(self) -> None:
        """Verify industry_group accepts a string value."""
        score = TickerScore(
            ticker="NVDA",
            composite_score=90.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
            industry_group="Semiconductors & Semiconductor Equipment",
        )
        assert score.industry_group == "Semiconductors & Semiconductor Equipment"
