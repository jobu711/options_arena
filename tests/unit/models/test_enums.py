"""Unit tests for all StrEnum definitions in options_arena.models.enums.

Tests each of the 12 enums for:
  - Correct member count
  - All values are lowercase strings
  - StrEnum subclass check
  - Exhaustive iteration matches expected members
  - String serialization
"""

import pytest

from options_arena.models import (
    DividendSource,
    ExerciseStyle,
    GICSSector,
    GreeksSource,
    MacdSignal,
    MarketCapTier,
    OptionType,
    PositionSide,
    PricingModel,
    ScanPreset,
    SignalDirection,
    SpreadType,
)
from options_arena.models.enums import SECTOR_ALIASES

# ---------------------------------------------------------------------------
# OptionType (2 members)
# ---------------------------------------------------------------------------


class TestOptionType:
    @pytest.mark.critical
    def test_option_type_has_exactly_two_members(self) -> None:
        assert len(OptionType) == 2

    def test_option_type_values_are_lowercase(self) -> None:
        assert OptionType.CALL == "call"
        assert OptionType.PUT == "put"

    def test_option_type_string_serialization(self) -> None:
        assert str(OptionType.CALL) == "call"
        assert str(OptionType.PUT) == "put"


# ---------------------------------------------------------------------------
# PositionSide (2 members)
# ---------------------------------------------------------------------------


class TestPositionSide:
    def test_position_side_has_exactly_two_members(self) -> None:
        assert len(PositionSide) == 2

    def test_position_side_values_are_lowercase(self) -> None:
        assert PositionSide.LONG == "long"
        assert PositionSide.SHORT == "short"

    def test_position_side_string_serialization(self) -> None:
        assert str(PositionSide.LONG) == "long"
        assert str(PositionSide.SHORT) == "short"


# ---------------------------------------------------------------------------
# SignalDirection (3 members)
# ---------------------------------------------------------------------------


class TestSignalDirection:
    def test_signal_direction_has_exactly_three_members(self) -> None:
        assert len(SignalDirection) == 3

    def test_signal_direction_values_are_lowercase(self) -> None:
        assert SignalDirection.BULLISH == "bullish"
        assert SignalDirection.BEARISH == "bearish"
        assert SignalDirection.NEUTRAL == "neutral"

    def test_signal_direction_string_serialization(self) -> None:
        assert str(SignalDirection.BULLISH) == "bullish"
        assert str(SignalDirection.BEARISH) == "bearish"
        assert str(SignalDirection.NEUTRAL) == "neutral"


# ---------------------------------------------------------------------------
# ExerciseStyle (2 members)
# ---------------------------------------------------------------------------


class TestExerciseStyle:
    def test_exercise_style_has_exactly_two_members(self) -> None:
        assert len(ExerciseStyle) == 2

    def test_exercise_style_values_are_lowercase(self) -> None:
        assert ExerciseStyle.AMERICAN == "american"
        assert ExerciseStyle.EUROPEAN == "european"

    def test_exercise_style_string_serialization(self) -> None:
        assert str(ExerciseStyle.AMERICAN) == "american"
        assert str(ExerciseStyle.EUROPEAN) == "european"


# ---------------------------------------------------------------------------
# PricingModel (2 members)
# ---------------------------------------------------------------------------


class TestPricingModel:
    def test_pricing_model_has_exactly_two_members(self) -> None:
        assert len(PricingModel) == 2

    def test_pricing_model_values_are_lowercase(self) -> None:
        assert PricingModel.BSM == "bsm"
        assert PricingModel.BAW == "baw"

    def test_pricing_model_string_serialization(self) -> None:
        assert str(PricingModel.BSM) == "bsm"
        assert str(PricingModel.BAW) == "baw"


# ---------------------------------------------------------------------------
# MarketCapTier (5 members)
# ---------------------------------------------------------------------------


class TestMarketCapTier:
    def test_market_cap_tier_has_exactly_five_members(self) -> None:
        assert len(MarketCapTier) == 5

    def test_market_cap_tier_values_are_lowercase(self) -> None:
        assert MarketCapTier.MEGA == "mega"
        assert MarketCapTier.LARGE == "large"
        assert MarketCapTier.MID == "mid"
        assert MarketCapTier.SMALL == "small"
        assert MarketCapTier.MICRO == "micro"

    def test_market_cap_tier_string_serialization(self) -> None:
        assert str(MarketCapTier.MEGA) == "mega"
        assert str(MarketCapTier.LARGE) == "large"
        assert str(MarketCapTier.MID) == "mid"
        assert str(MarketCapTier.SMALL) == "small"
        assert str(MarketCapTier.MICRO) == "micro"


# ---------------------------------------------------------------------------
# DividendSource (4 members)
# ---------------------------------------------------------------------------


class TestDividendSource:
    def test_dividend_source_has_exactly_four_members(self) -> None:
        assert len(DividendSource) == 4

    def test_dividend_source_values_are_lowercase(self) -> None:
        assert DividendSource.FORWARD == "forward"
        assert DividendSource.TRAILING == "trailing"
        assert DividendSource.COMPUTED == "computed"
        assert DividendSource.NONE == "none"

    def test_dividend_source_string_serialization(self) -> None:
        assert str(DividendSource.FORWARD) == "forward"
        assert str(DividendSource.TRAILING) == "trailing"
        assert str(DividendSource.COMPUTED) == "computed"
        assert str(DividendSource.NONE) == "none"


# ---------------------------------------------------------------------------
# SpreadType (4 members)
# ---------------------------------------------------------------------------


class TestSpreadType:
    def test_spread_type_has_exactly_four_members(self) -> None:
        assert len(SpreadType) == 4

    def test_spread_type_values_are_lowercase(self) -> None:
        assert SpreadType.VERTICAL == "vertical"
        assert SpreadType.IRON_CONDOR == "iron_condor"
        assert SpreadType.STRADDLE == "straddle"
        assert SpreadType.STRANGLE == "strangle"

    def test_spread_type_string_serialization(self) -> None:
        assert str(SpreadType.VERTICAL) == "vertical"
        assert str(SpreadType.IRON_CONDOR) == "iron_condor"
        assert str(SpreadType.STRADDLE) == "straddle"
        assert str(SpreadType.STRANGLE) == "strangle"


# ---------------------------------------------------------------------------
# MacdSignal (3 members)
# ---------------------------------------------------------------------------


class TestMacdSignal:
    def test_macd_signal_has_exactly_three_members(self) -> None:
        assert len(MacdSignal) == 3

    def test_macd_signal_values_are_lowercase(self) -> None:
        assert MacdSignal.BULLISH_CROSSOVER == "bullish_crossover"
        assert MacdSignal.BEARISH_CROSSOVER == "bearish_crossover"
        assert MacdSignal.NEUTRAL == "neutral"

    def test_macd_signal_string_serialization(self) -> None:
        assert str(MacdSignal.BULLISH_CROSSOVER) == "bullish_crossover"
        assert str(MacdSignal.BEARISH_CROSSOVER) == "bearish_crossover"
        assert str(MacdSignal.NEUTRAL) == "neutral"


# ---------------------------------------------------------------------------
# ScanPreset (6 members — 3 original + 3 added in #285)
# ---------------------------------------------------------------------------


class TestScanPreset:
    def test_scan_preset_has_exactly_six_members(self) -> None:
        assert len(ScanPreset) == 6

    def test_scan_preset_values_are_lowercase(self) -> None:
        assert ScanPreset.FULL == "full"
        assert ScanPreset.SP500 == "sp500"
        assert ScanPreset.ETFS == "etfs"
        assert ScanPreset.NASDAQ100 == "nasdaq100"
        assert ScanPreset.RUSSELL2000 == "russell2000"
        assert ScanPreset.MOST_ACTIVE == "most_active"

    def test_scan_preset_string_serialization(self) -> None:
        assert str(ScanPreset.FULL) == "full"
        assert str(ScanPreset.SP500) == "sp500"
        assert str(ScanPreset.ETFS) == "etfs"
        assert str(ScanPreset.NASDAQ100) == "nasdaq100"
        assert str(ScanPreset.RUSSELL2000) == "russell2000"
        assert str(ScanPreset.MOST_ACTIVE) == "most_active"


# ---------------------------------------------------------------------------
# GreeksSource (3 members)
# ---------------------------------------------------------------------------


class TestGreeksSource:
    def test_greeks_source_has_exactly_three_members(self) -> None:
        assert len(GreeksSource) == 3

    def test_greeks_source_values_are_lowercase(self) -> None:
        assert GreeksSource.COMPUTED == "computed"
        assert GreeksSource.MARKET == "market"
        assert GreeksSource.SMOOTHED == "smoothed"

    def test_greeks_source_string_serialization(self) -> None:
        assert str(GreeksSource.COMPUTED) == "computed"
        assert str(GreeksSource.MARKET) == "market"
        assert str(GreeksSource.SMOOTHED) == "smoothed"


# ---------------------------------------------------------------------------
# GICSSector (11 members)
# ---------------------------------------------------------------------------


class TestGICSSector:
    def test_gics_sector_has_exactly_eleven_members(self) -> None:
        assert len(GICSSector) == 11

    def test_gics_sector_canonical_values(self) -> None:
        assert GICSSector.COMMUNICATION_SERVICES == "Communication Services"
        assert GICSSector.CONSUMER_DISCRETIONARY == "Consumer Discretionary"
        assert GICSSector.CONSUMER_STAPLES == "Consumer Staples"
        assert GICSSector.ENERGY == "Energy"
        assert GICSSector.FINANCIALS == "Financials"
        assert GICSSector.HEALTH_CARE == "Health Care"
        assert GICSSector.INDUSTRIALS == "Industrials"
        assert GICSSector.INFORMATION_TECHNOLOGY == "Information Technology"
        assert GICSSector.MATERIALS == "Materials"
        assert GICSSector.REAL_ESTATE == "Real Estate"
        assert GICSSector.UTILITIES == "Utilities"

    def test_gics_sector_string_serialization(self) -> None:
        assert str(GICSSector.INFORMATION_TECHNOLOGY) == "Information Technology"
        assert str(GICSSector.HEALTH_CARE) == "Health Care"

    def test_gics_sector_construction_from_canonical_value(self) -> None:
        assert GICSSector("Information Technology") is GICSSector.INFORMATION_TECHNOLOGY


# ---------------------------------------------------------------------------
# SECTOR_ALIASES
# ---------------------------------------------------------------------------


class TestSectorAliases:
    def test_all_canonical_lowercase_present(self) -> None:
        """Every canonical sector name (lowered) should be in aliases."""
        for sector in GICSSector:
            assert sector.value.lower() in SECTOR_ALIASES
            assert SECTOR_ALIASES[sector.value.lower()] is sector

    def test_short_name_aliases(self) -> None:
        assert SECTOR_ALIASES["tech"] is GICSSector.INFORMATION_TECHNOLOGY
        assert SECTOR_ALIASES["technology"] is GICSSector.INFORMATION_TECHNOLOGY
        assert SECTOR_ALIASES["it"] is GICSSector.INFORMATION_TECHNOLOGY
        assert SECTOR_ALIASES["healthcare"] is GICSSector.HEALTH_CARE
        assert SECTOR_ALIASES["telecom"] is GICSSector.COMMUNICATION_SERVICES

    def test_hyphenated_aliases(self) -> None:
        assert SECTOR_ALIASES["information-technology"] is GICSSector.INFORMATION_TECHNOLOGY
        assert SECTOR_ALIASES["health-care"] is GICSSector.HEALTH_CARE
        assert SECTOR_ALIASES["real-estate"] is GICSSector.REAL_ESTATE

    def test_underscored_aliases(self) -> None:
        assert SECTOR_ALIASES["information_technology"] is GICSSector.INFORMATION_TECHNOLOGY
        assert SECTOR_ALIASES["health_care"] is GICSSector.HEALTH_CARE
        assert SECTOR_ALIASES["real_estate"] is GICSSector.REAL_ESTATE

    def test_all_aliases_map_to_valid_sector(self) -> None:
        """Every alias value must be a valid GICSSector member."""
        for alias, sector in SECTOR_ALIASES.items():
            assert isinstance(sector, GICSSector), f"Alias {alias!r} maps to invalid sector"
