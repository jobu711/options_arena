"""Tests for industry group mapping and filtering helpers.

Covers:
  - build_industry_group_map with known, unknown, empty, and case-insensitive inputs.
  - filter_by_industry_groups with matching, empty filter, and no-match cases.
  - Hyphenated yfinance industry strings (em dash and ASCII dash variants).
"""

from __future__ import annotations

from options_arena.models.enums import GICSIndustryGroup
from options_arena.services.universe import (
    build_industry_group_map,
    filter_by_industry_groups,
)

# ---------------------------------------------------------------------------
# build_industry_group_map tests
# ---------------------------------------------------------------------------


class TestBuildIndustryGroupMap:
    """build_industry_group_map maps yfinance industry strings to GICSIndustryGroup."""

    def test_maps_known_industry(self) -> None:
        """Verify 'Semiconductors' maps to SEMICONDUCTORS_EQUIPMENT."""
        data = {"NVDA": "Semiconductors"}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_maps_hyphenated_industry_em_dash(self) -> None:
        """Verify 'Software\u2014Application' (em dash) maps to SOFTWARE_SERVICES."""
        data = {"CRM": "Software\u2014Application"}
        result = build_industry_group_map(data)
        assert result == {"CRM": GICSIndustryGroup.SOFTWARE_SERVICES}

    def test_maps_hyphenated_industry_ascii_dash(self) -> None:
        """Verify 'Software - Application' (ASCII dash) maps to SOFTWARE_SERVICES."""
        data = {"ORCL": "Software - Application"}
        result = build_industry_group_map(data)
        assert result == {"ORCL": GICSIndustryGroup.SOFTWARE_SERVICES}

    def test_maps_internet_retail_to_retailing(self) -> None:
        """Verify 'Internet Retail' maps to RETAILING."""
        data = {"AMZN": "Internet Retail"}
        result = build_industry_group_map(data)
        assert result == {"AMZN": GICSIndustryGroup.RETAILING}

    def test_maps_biotechnology_to_pharma_biotech(self) -> None:
        """Verify 'Biotechnology' maps to PHARMA_BIOTECH."""
        data = {"MRNA": "Biotechnology"}
        result = build_industry_group_map(data)
        assert result == {"MRNA": GICSIndustryGroup.PHARMA_BIOTECH}

    def test_maps_banks_diversified(self) -> None:
        """Verify 'Banks\u2014Diversified' maps to BANKS."""
        data = {"JPM": "Banks\u2014Diversified"}
        result = build_industry_group_map(data)
        assert result == {"JPM": GICSIndustryGroup.BANKS}

    def test_unknown_industry_excluded(self) -> None:
        """Verify unmapped industry is excluded from result dict, not an error."""
        data = {
            "NVDA": "Semiconductors",
            "FAKE": "Underwater Basket Weaving",
        }
        result = build_industry_group_map(data)
        assert "NVDA" in result
        assert "FAKE" not in result
        assert len(result) == 1

    def test_empty_input(self) -> None:
        """Verify empty dict input returns empty dict."""
        result = build_industry_group_map({})
        assert result == {}

    def test_case_insensitive(self) -> None:
        """Verify 'semiconductors' (lowercase) maps correctly."""
        data = {"NVDA": "semiconductors"}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_whitespace_handling(self) -> None:
        """Verify leading/trailing whitespace is stripped before lookup."""
        data = {"NVDA": "  Semiconductors  "}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_multiple_tickers(self) -> None:
        """Verify multiple tickers are all mapped correctly."""
        data = {
            "NVDA": "Semiconductors",
            "CRM": "Software\u2014Application",
            "JPM": "Banks\u2014Diversified",
            "XOM": "Oil & Gas Integrated",
        }
        result = build_industry_group_map(data)
        assert result["NVDA"] == GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        assert result["CRM"] == GICSIndustryGroup.SOFTWARE_SERVICES
        assert result["JPM"] == GICSIndustryGroup.BANKS
        assert result["XOM"] == GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS
        assert len(result) == 4


# ---------------------------------------------------------------------------
# filter_by_industry_groups tests
# ---------------------------------------------------------------------------


class TestFilterByIndustryGroups:
    """filter_by_industry_groups filters tickers by industry group membership."""

    def test_filters_matching_tickers(self) -> None:
        """Verify only tickers in selected groups are returned."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "JPM": GICSIndustryGroup.BANKS,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM", "JPM"],
            industry_groups=[GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT],
            ig_map=ig_map,
        )
        assert result == ["NVDA"]

    def test_multiple_groups_or_logic(self) -> None:
        """Verify multiple industry groups use OR logic."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "JPM": GICSIndustryGroup.BANKS,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM", "JPM"],
            industry_groups=[
                GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
                GICSIndustryGroup.SOFTWARE_SERVICES,
            ],
            ig_map=ig_map,
        )
        assert result == ["NVDA", "CRM"]

    def test_empty_filter_returns_all(self) -> None:
        """Verify empty group list returns all tickers unchanged."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "JPM": GICSIndustryGroup.BANKS,
        }
        tickers = ["NVDA", "JPM", "TSLA"]
        result = filter_by_industry_groups(
            tickers=tickers,
            industry_groups=[],
            ig_map=ig_map,
        )
        assert result == tickers

    def test_no_matches_returns_empty(self) -> None:
        """Verify empty result when no tickers match selected groups."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM"],
            industry_groups=[GICSIndustryGroup.BANKS],
            ig_map=ig_map,
        )
        assert result == []

    def test_ticker_not_in_map_excluded(self) -> None:
        """Verify tickers not in ig_map are excluded when filtering is active."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "UNKNOWN"],
            industry_groups=[GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT],
            ig_map=ig_map,
        )
        assert result == ["NVDA"]

    def test_preserves_order(self) -> None:
        """Verify filter preserves input order of tickers."""
        ig_map = {
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        }
        result = filter_by_industry_groups(
            tickers=["CRM", "NVDA"],
            industry_groups=[
                GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
                GICSIndustryGroup.SOFTWARE_SERVICES,
            ],
            ig_map=ig_map,
        )
        assert result == ["CRM", "NVDA"]

    def test_empty_tickers_returns_empty(self) -> None:
        """Verify empty ticker list returns empty."""
        result = filter_by_industry_groups(
            tickers=[],
            industry_groups=[GICSIndustryGroup.BANKS],
            ig_map={},
        )
        assert result == []
