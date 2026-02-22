"""Unit tests for all StrEnum definitions in options_arena.models.enums.

Tests each of the 9 enums for:
  - Correct member count
  - All values are lowercase strings
  - StrEnum subclass check
  - Exhaustive iteration matches expected members
  - String serialization
"""

from enum import StrEnum

from options_arena.models import (
    DividendSource,
    ExerciseStyle,
    GreeksSource,
    MarketCapTier,
    OptionType,
    PositionSide,
    PricingModel,
    SignalDirection,
    SpreadType,
)

# ---------------------------------------------------------------------------
# OptionType (2 members)
# ---------------------------------------------------------------------------


class TestOptionType:
    def test_option_type_has_exactly_two_members(self) -> None:
        assert len(OptionType) == 2

    def test_option_type_values_are_lowercase(self) -> None:
        assert OptionType.CALL == "call"
        assert OptionType.PUT == "put"

    def test_option_type_is_str_enum(self) -> None:
        assert issubclass(OptionType, StrEnum)

    def test_option_type_exhaustive_iteration(self) -> None:
        assert set(OptionType) == {OptionType.CALL, OptionType.PUT}

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

    def test_position_side_is_str_enum(self) -> None:
        assert issubclass(PositionSide, StrEnum)

    def test_position_side_exhaustive_iteration(self) -> None:
        assert set(PositionSide) == {PositionSide.LONG, PositionSide.SHORT}

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

    def test_signal_direction_is_str_enum(self) -> None:
        assert issubclass(SignalDirection, StrEnum)

    def test_signal_direction_exhaustive_iteration(self) -> None:
        assert set(SignalDirection) == {
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        }

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

    def test_exercise_style_is_str_enum(self) -> None:
        assert issubclass(ExerciseStyle, StrEnum)

    def test_exercise_style_exhaustive_iteration(self) -> None:
        assert set(ExerciseStyle) == {ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN}

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

    def test_pricing_model_is_str_enum(self) -> None:
        assert issubclass(PricingModel, StrEnum)

    def test_pricing_model_exhaustive_iteration(self) -> None:
        assert set(PricingModel) == {PricingModel.BSM, PricingModel.BAW}

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

    def test_market_cap_tier_is_str_enum(self) -> None:
        assert issubclass(MarketCapTier, StrEnum)

    def test_market_cap_tier_exhaustive_iteration(self) -> None:
        assert set(MarketCapTier) == {
            MarketCapTier.MEGA,
            MarketCapTier.LARGE,
            MarketCapTier.MID,
            MarketCapTier.SMALL,
            MarketCapTier.MICRO,
        }

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

    def test_dividend_source_is_str_enum(self) -> None:
        assert issubclass(DividendSource, StrEnum)

    def test_dividend_source_exhaustive_iteration(self) -> None:
        assert set(DividendSource) == {
            DividendSource.FORWARD,
            DividendSource.TRAILING,
            DividendSource.COMPUTED,
            DividendSource.NONE,
        }

    def test_dividend_source_string_serialization(self) -> None:
        assert str(DividendSource.FORWARD) == "forward"
        assert str(DividendSource.TRAILING) == "trailing"
        assert str(DividendSource.COMPUTED) == "computed"
        assert str(DividendSource.NONE) == "none"


# ---------------------------------------------------------------------------
# SpreadType (6 members)
# ---------------------------------------------------------------------------


class TestSpreadType:
    def test_spread_type_has_exactly_six_members(self) -> None:
        assert len(SpreadType) == 6

    def test_spread_type_values_are_lowercase(self) -> None:
        assert SpreadType.VERTICAL == "vertical"
        assert SpreadType.CALENDAR == "calendar"
        assert SpreadType.IRON_CONDOR == "iron_condor"
        assert SpreadType.STRADDLE == "straddle"
        assert SpreadType.STRANGLE == "strangle"
        assert SpreadType.BUTTERFLY == "butterfly"

    def test_spread_type_is_str_enum(self) -> None:
        assert issubclass(SpreadType, StrEnum)

    def test_spread_type_exhaustive_iteration(self) -> None:
        assert set(SpreadType) == {
            SpreadType.VERTICAL,
            SpreadType.CALENDAR,
            SpreadType.IRON_CONDOR,
            SpreadType.STRADDLE,
            SpreadType.STRANGLE,
            SpreadType.BUTTERFLY,
        }

    def test_spread_type_string_serialization(self) -> None:
        assert str(SpreadType.VERTICAL) == "vertical"
        assert str(SpreadType.CALENDAR) == "calendar"
        assert str(SpreadType.IRON_CONDOR) == "iron_condor"
        assert str(SpreadType.STRADDLE) == "straddle"
        assert str(SpreadType.STRANGLE) == "strangle"
        assert str(SpreadType.BUTTERFLY) == "butterfly"


# ---------------------------------------------------------------------------
# GreeksSource (2 members)
# ---------------------------------------------------------------------------


class TestGreeksSource:
    def test_greeks_source_has_exactly_two_members(self) -> None:
        assert len(GreeksSource) == 2

    def test_greeks_source_values_are_lowercase(self) -> None:
        assert GreeksSource.COMPUTED == "computed"
        assert GreeksSource.MARKET == "market"

    def test_greeks_source_is_str_enum(self) -> None:
        assert issubclass(GreeksSource, StrEnum)

    def test_greeks_source_exhaustive_iteration(self) -> None:
        assert set(GreeksSource) == {GreeksSource.COMPUTED, GreeksSource.MARKET}

    def test_greeks_source_string_serialization(self) -> None:
        assert str(GreeksSource.COMPUTED) == "computed"
        assert str(GreeksSource.MARKET) == "market"
