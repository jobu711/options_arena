"""Unit tests for options_arena.scoring.dimensional — dimensional scoring engine."""

import pytest

from options_arena.models.enums import MarketRegime, SignalDirection
from options_arena.models.scan import IndicatorSignals
from options_arena.models.scoring import DimensionalScores, DirectionSignal
from options_arena.scoring.dimensional import (
    _FAMILY_NAMES,
    DEFAULT_FAMILY_WEIGHTS,
    FAMILY_INDICATOR_MAP,
    REGIME_WEIGHT_PROFILES,
    apply_regime_weights,
    compute_dimensional_scores,
    compute_direction_signal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_INDICATOR_FIELDS: set[str] = set(IndicatorSignals.model_fields.keys())


def _make_signals(**kwargs: float | None) -> IndicatorSignals:
    """Build IndicatorSignals with specified fields; unspecified remain None."""
    return IndicatorSignals(**kwargs)


def _make_full_signals(value: float = 60.0) -> IndicatorSignals:
    """Build IndicatorSignals with ALL 58 fields set to *value*."""
    return IndicatorSignals(**{f: value for f in ALL_INDICATOR_FIELDS})


# ---------------------------------------------------------------------------
# FAMILY_INDICATOR_MAP validation
# ---------------------------------------------------------------------------


class TestFamilyIndicatorMap:
    """Validate FAMILY_INDICATOR_MAP structure and coverage."""

    def test_all_families_present(self) -> None:
        """Map has exactly the 8 expected family keys."""
        assert set(FAMILY_INDICATOR_MAP.keys()) == set(_FAMILY_NAMES)

    def test_every_indicator_field_in_at_least_one_family(self) -> None:
        """Every IndicatorSignals field appears in at least one family (no orphans)."""
        covered: set[str] = set()
        for indicators in FAMILY_INDICATOR_MAP.values():
            covered.update(indicators)

        orphans = ALL_INDICATOR_FIELDS - covered
        assert orphans == set(), f"Orphan indicator fields not in any family: {orphans}"

    def test_every_mapped_field_exists_on_model(self) -> None:
        """Every field name in the map is a valid IndicatorSignals field."""
        for family, indicators in FAMILY_INDICATOR_MAP.items():
            for field_name in indicators:
                assert field_name in ALL_INDICATOR_FIELDS, (
                    f"'{field_name}' in family '{family}' is not an IndicatorSignals field"
                )

    def test_no_empty_families(self) -> None:
        """Every family has at least one indicator."""
        for family, indicators in FAMILY_INDICATOR_MAP.items():
            assert len(indicators) > 0, f"Family '{family}' has no indicators"


# ---------------------------------------------------------------------------
# Weight profile validation
# ---------------------------------------------------------------------------


class TestWeightProfiles:
    """Validate that all weight profiles sum to 1.0."""

    def test_default_weights_sum_to_one(self) -> None:
        """DEFAULT_FAMILY_WEIGHTS values sum to 1.0."""
        total = sum(DEFAULT_FAMILY_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_default_weights_cover_all_families(self) -> None:
        """DEFAULT_FAMILY_WEIGHTS has all 8 families."""
        assert set(DEFAULT_FAMILY_WEIGHTS.keys()) == set(_FAMILY_NAMES)

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_regime_weights_sum_to_one(self, regime: MarketRegime) -> None:
        """Each regime weight profile sums to 1.0."""
        profile = REGIME_WEIGHT_PROFILES[regime]
        total = sum(profile.values())
        assert total == pytest.approx(1.0, abs=1e-9), (
            f"Regime {regime.value} weights sum to {total}, not 1.0"
        )

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_regime_weights_cover_all_families(self, regime: MarketRegime) -> None:
        """Each regime weight profile has all 8 families."""
        profile = REGIME_WEIGHT_PROFILES[regime]
        assert set(profile.keys()) == set(_FAMILY_NAMES), f"Regime {regime.value} missing families"

    def test_all_four_regimes_have_profiles(self) -> None:
        """REGIME_WEIGHT_PROFILES has entries for all MarketRegime members."""
        for regime in MarketRegime:
            assert regime in REGIME_WEIGHT_PROFILES, f"Missing profile for regime {regime.value}"

    def test_all_weights_are_positive(self) -> None:
        """Every weight in every profile is strictly positive."""
        for family, weight in DEFAULT_FAMILY_WEIGHTS.items():
            assert weight > 0.0, f"Default weight for '{family}' is not positive: {weight}"
        for regime, profile in REGIME_WEIGHT_PROFILES.items():
            for family, weight in profile.items():
                assert weight > 0.0, (
                    f"Regime {regime.value} weight for '{family}' is not positive: {weight}"
                )


# ---------------------------------------------------------------------------
# compute_dimensional_scores
# ---------------------------------------------------------------------------


class TestComputeDimensionalScores:
    """Tests for compute_dimensional_scores()."""

    def test_all_none_signals(self) -> None:
        """All-None IndicatorSignals produce all-None family scores."""
        signals = IndicatorSignals()
        result = compute_dimensional_scores(signals)

        assert isinstance(result, DimensionalScores)
        for family in _FAMILY_NAMES:
            assert getattr(result, family) is None, f"Family '{family}' should be None"

    def test_full_signals_all_families_populated(self) -> None:
        """All 58 fields set to 60.0 produce all 8 families with score == 60.0."""
        signals = _make_full_signals(60.0)
        result = compute_dimensional_scores(signals)

        for family in _FAMILY_NAMES:
            score = getattr(result, family)
            assert score is not None, f"Family '{family}' should not be None"
            assert score == pytest.approx(60.0, rel=1e-4), (
                f"Family '{family}' expected 60.0, got {score}"
            )

    def test_partial_signals_some_families_none(self) -> None:
        """Only trend indicators set; other families should be None."""
        signals = _make_signals(rsi=70.0, adx=50.0, supertrend=80.0)
        result = compute_dimensional_scores(signals)

        # Trend family should be populated
        assert result.trend is not None
        assert result.trend == pytest.approx((70.0 + 50.0 + 80.0) / 3.0, rel=1e-4)

        # Other families should be None (no indicators set)
        assert result.iv_vol is None
        assert result.hv_vol is None
        assert result.flow is None
        assert result.microstructure is None
        assert result.fundamental is None
        assert result.regime is None
        assert result.risk is None

    def test_trend_family_specific_fields(self) -> None:
        """Trend family computed from its specific indicator subset."""
        signals = _make_signals(
            rsi=80.0,
            stochastic_rsi=70.0,
            williams_r=60.0,
            adx=50.0,
            roc=40.0,
        )
        result = compute_dimensional_scores(signals)

        expected = (80.0 + 70.0 + 60.0 + 50.0 + 40.0) / 5.0
        assert result.trend == pytest.approx(expected, rel=1e-4)

    def test_iv_vol_family_specific_fields(self) -> None:
        """IV vol family computed from its specific indicator subset."""
        signals = _make_signals(iv_rank=55.0, iv_percentile=65.0, iv_hv_spread=45.0)
        result = compute_dimensional_scores(signals)

        expected = (55.0 + 65.0 + 45.0) / 3.0
        assert result.iv_vol == pytest.approx(expected, rel=1e-4)

    def test_hv_vol_family_specific_fields(self) -> None:
        """HV vol family computed from its 3 indicators."""
        signals = _make_signals(bb_width=30.0, atr_pct=40.0, keltner_width=50.0)
        result = compute_dimensional_scores(signals)

        expected = (30.0 + 40.0 + 50.0) / 3.0
        assert result.hv_vol == pytest.approx(expected, rel=1e-4)

    def test_flow_family_specific_fields(self) -> None:
        """Flow family computed from its indicator subset."""
        signals = _make_signals(put_call_ratio=60.0, gex=70.0, dollar_volume_trend=80.0)
        result = compute_dimensional_scores(signals)

        expected = (60.0 + 70.0 + 80.0) / 3.0
        assert result.flow == pytest.approx(expected, rel=1e-4)

    def test_microstructure_family_specific_fields(self) -> None:
        """Microstructure family computed from its indicator subset."""
        signals = _make_signals(obv=55.0, ad=65.0, volume_profile_skew=45.0)
        result = compute_dimensional_scores(signals)

        expected = (55.0 + 65.0 + 45.0) / 3.0
        assert result.microstructure == pytest.approx(expected, rel=1e-4)

    def test_fundamental_family_specific_fields(self) -> None:
        """Fundamental family computed from its indicator subset."""
        signals = _make_signals(
            earnings_em_ratio=50.0,
            short_interest_ratio=60.0,
            iv_crush_history=70.0,
        )
        result = compute_dimensional_scores(signals)

        expected = (50.0 + 60.0 + 70.0) / 3.0
        assert result.fundamental == pytest.approx(expected, rel=1e-4)

    def test_regime_family_specific_fields(self) -> None:
        """Regime family computed from its indicator subset."""
        signals = _make_signals(
            vix_term_structure=40.0,
            risk_on_off_score=60.0,
            market_regime=50.0,
        )
        result = compute_dimensional_scores(signals)

        expected = (40.0 + 60.0 + 50.0) / 3.0
        assert result.regime == pytest.approx(expected, rel=1e-4)

    def test_risk_family_specific_fields(self) -> None:
        """Risk family computed from its indicator subset."""
        signals = _make_signals(pop=75.0, optimal_dte_score=80.0, max_loss_ratio=60.0)
        result = compute_dimensional_scores(signals)

        expected = (75.0 + 80.0 + 60.0) / 3.0
        assert result.risk == pytest.approx(expected, rel=1e-4)

    def test_single_indicator_per_family(self) -> None:
        """A family with exactly one non-None indicator uses that value."""
        signals = _make_signals(rsi=85.0)
        result = compute_dimensional_scores(signals)

        assert result.trend == pytest.approx(85.0, rel=1e-4)

    def test_nan_values_ignored(self) -> None:
        """NaN indicator values are treated like None (excluded from mean)."""
        signals = _make_signals(rsi=float("nan"), adx=60.0)
        result = compute_dimensional_scores(signals)

        # Only adx contributes (NaN rsi is excluded)
        assert result.trend == pytest.approx(60.0, rel=1e-4)

    def test_inf_values_ignored(self) -> None:
        """Infinity indicator values are treated like None (excluded from mean)."""
        signals = _make_signals(rsi=float("inf"), adx=60.0)
        result = compute_dimensional_scores(signals)

        assert result.trend == pytest.approx(60.0, rel=1e-4)

    def test_result_is_frozen(self) -> None:
        """DimensionalScores is frozen (immutable)."""
        signals = _make_full_signals(50.0)
        result = compute_dimensional_scores(signals)

        with pytest.raises(Exception):  # noqa: B017
            result.trend = 99.0  # type: ignore[misc]

    def test_spread_quality_only_in_microstructure(self) -> None:
        """spread_quality appears in microstructure only (not risk)."""
        signals = _make_signals(spread_quality=70.0)
        result = compute_dimensional_scores(signals)

        assert result.microstructure == pytest.approx(70.0, rel=1e-4)
        assert result.risk is None  # spread_quality not in risk family

    def test_no_duplicate_indicators_across_families(self) -> None:
        """No indicator appears in more than one family."""
        seen: dict[str, str] = {}
        for family, indicators in FAMILY_INDICATOR_MAP.items():
            for ind in indicators:
                assert ind not in seen, f"'{ind}' duplicated: in '{seen[ind]}' and '{family}'"
                seen[ind] = family

    def test_clamping_high_values(self) -> None:
        """Values above 100 are clamped to 100 in family score."""
        # IndicatorSignals has no validator preventing > 100 on fields,
        # but dimensional scoring clamps the result.
        signals = IndicatorSignals(rsi=100.0, adx=100.0)
        result = compute_dimensional_scores(signals)
        assert result.trend is not None
        assert result.trend <= 100.0


# ---------------------------------------------------------------------------
# apply_regime_weights
# ---------------------------------------------------------------------------


class TestApplyRegimeWeights:
    """Tests for apply_regime_weights()."""

    def test_default_weights_all_families(self) -> None:
        """With all families at 60.0 and default weights, composite == 60.0."""
        scores = DimensionalScores(
            trend=60.0,
            iv_vol=60.0,
            hv_vol=60.0,
            flow=60.0,
            microstructure=60.0,
            fundamental=60.0,
            regime=60.0,
            risk=60.0,
        )
        result = apply_regime_weights(scores)
        assert result == pytest.approx(60.0, rel=1e-4)

    def test_default_weights_varied_families(self) -> None:
        """Manually compute weighted average with varied family scores."""
        scores = DimensionalScores(
            trend=80.0,
            iv_vol=60.0,
            hv_vol=40.0,
            flow=70.0,
            microstructure=50.0,
            fundamental=30.0,
            regime=90.0,
            risk=20.0,
        )
        expected = (
            0.22 * 80.0
            + 0.20 * 60.0
            + 0.05 * 40.0
            + 0.18 * 70.0
            + 0.08 * 50.0
            + 0.10 * 30.0
            + 0.07 * 90.0
            + 0.10 * 20.0
        )
        result = apply_regime_weights(scores)
        assert result == pytest.approx(expected, rel=1e-4)

    def test_all_none_returns_zero(self) -> None:
        """All family scores None produce composite == 0.0."""
        scores = DimensionalScores()
        result = apply_regime_weights(scores)
        assert result == 0.0

    def test_weight_redistribution_partial_none(self) -> None:
        """When some families are None, weights redistribute to remaining."""
        # Only trend (0.22) and risk (0.10) present.
        # After redistribution: trend_weight = 0.22/(0.22+0.10) = 0.6875
        # risk_weight = 0.10/(0.22+0.10) = 0.3125
        # composite = 0.6875*80 + 0.3125*40 = 55 + 12.5 = 67.5
        scores = DimensionalScores(trend=80.0, risk=40.0)
        result = apply_regime_weights(scores)

        effective_weight_sum = 0.22 + 0.10
        expected = (0.22 * 80.0 + 0.10 * 40.0) / effective_weight_sum
        assert result == pytest.approx(expected, rel=1e-4)

    def test_single_family_present(self) -> None:
        """Single family present: composite equals that family's score."""
        scores = DimensionalScores(flow=75.0)
        result = apply_regime_weights(scores)
        assert result == pytest.approx(75.0, rel=1e-4)

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_regime_weights_uniform_scores(self, regime: MarketRegime) -> None:
        """With all families at the same score, any regime produces that score."""
        scores = DimensionalScores(
            trend=50.0,
            iv_vol=50.0,
            hv_vol=50.0,
            flow=50.0,
            microstructure=50.0,
            fundamental=50.0,
            regime=50.0,
            risk=50.0,
        )
        result = apply_regime_weights(scores, regime=regime, enable_regime_weights=True)
        assert result == pytest.approx(50.0, rel=1e-4)

    def test_trending_regime_boosts_trend(self) -> None:
        """TRENDING regime: trend weight (0.30) > default (0.22)."""
        scores = DimensionalScores(
            trend=100.0,
            iv_vol=0.0,
            hv_vol=0.0,
            flow=0.0,
            microstructure=0.0,
            fundamental=0.0,
            regime=0.0,
            risk=0.0,
        )
        default_result = apply_regime_weights(scores)
        trending_result = apply_regime_weights(
            scores, regime=MarketRegime.TRENDING, enable_regime_weights=True
        )
        # Trending should give higher composite when only trend is 100
        assert trending_result > default_result

    def test_crisis_regime_boosts_risk(self) -> None:
        """CRISIS regime: risk weight (0.30) > default (0.10)."""
        scores = DimensionalScores(
            trend=0.0,
            iv_vol=0.0,
            hv_vol=0.0,
            flow=0.0,
            microstructure=0.0,
            fundamental=0.0,
            regime=0.0,
            risk=100.0,
        )
        default_result = apply_regime_weights(scores)
        crisis_result = apply_regime_weights(
            scores, regime=MarketRegime.CRISIS, enable_regime_weights=True
        )
        # Crisis should give higher composite when only risk is 100
        assert crisis_result > default_result

    def test_enable_flag_false_ignores_regime(self) -> None:
        """When enable_regime_weights=False, regime parameter is ignored."""
        scores = DimensionalScores(
            trend=100.0,
            iv_vol=0.0,
            hv_vol=0.0,
            flow=0.0,
            microstructure=0.0,
            fundamental=0.0,
            regime=0.0,
            risk=0.0,
        )
        default_result = apply_regime_weights(scores)
        with_regime_but_disabled = apply_regime_weights(
            scores, regime=MarketRegime.TRENDING, enable_regime_weights=False
        )
        assert with_regime_but_disabled == pytest.approx(default_result, rel=1e-9)

    def test_regime_none_uses_defaults(self) -> None:
        """When regime is None (even with enable=True), default weights used."""
        scores = DimensionalScores(trend=70.0, flow=50.0)
        result_default = apply_regime_weights(scores)
        result_none_regime = apply_regime_weights(scores, regime=None, enable_regime_weights=True)
        assert result_none_regime == pytest.approx(result_default, rel=1e-9)

    def test_result_clamped_to_100(self) -> None:
        """Result is clamped to 100.0 maximum."""
        scores = DimensionalScores(
            trend=100.0,
            iv_vol=100.0,
            hv_vol=100.0,
            flow=100.0,
            microstructure=100.0,
            fundamental=100.0,
            regime=100.0,
            risk=100.0,
        )
        result = apply_regime_weights(scores)
        assert result <= 100.0

    def test_result_clamped_to_zero(self) -> None:
        """Result is clamped to 0.0 minimum."""
        scores = DimensionalScores(
            trend=0.0,
            iv_vol=0.0,
            hv_vol=0.0,
            flow=0.0,
            microstructure=0.0,
            fundamental=0.0,
            regime=0.0,
            risk=0.0,
        )
        result = apply_regime_weights(scores)
        assert result >= 0.0


# ---------------------------------------------------------------------------
# compute_direction_signal
# ---------------------------------------------------------------------------


class TestComputeDirectionSignal:
    """Tests for compute_direction_signal()."""

    def test_bullish_direction_with_high_signals(self) -> None:
        """Strong bullish signals produce bullish direction with high confidence."""
        signals = _make_full_signals(80.0)
        result = compute_direction_signal(signals, 80.0, SignalDirection.BULLISH)

        assert isinstance(result, DirectionSignal)
        assert result.direction is SignalDirection.BULLISH
        assert result.confidence > 0.5
        assert len(result.contributing_signals) > 0

    def test_bearish_direction_with_low_signals(self) -> None:
        """Low signals with bearish direction produce reasonable confidence."""
        signals = _make_full_signals(20.0)
        result = compute_direction_signal(signals, 20.0, SignalDirection.BEARISH)

        assert result.direction is SignalDirection.BEARISH
        assert result.confidence > 0.5
        assert len(result.contributing_signals) > 0

    def test_neutral_direction(self) -> None:
        """Neutral direction with mixed signals produces moderate confidence."""
        signals = _make_full_signals(50.0)
        result = compute_direction_signal(signals, 50.0, SignalDirection.NEUTRAL)

        assert result.direction is SignalDirection.NEUTRAL
        # Neutral with score at 50 should have low-moderate confidence
        assert 0.1 <= result.confidence <= 1.0

    def test_all_none_signals_returns_neutral(self) -> None:
        """All-None signals produce neutral with minimum confidence."""
        signals = IndicatorSignals()
        result = compute_direction_signal(signals, 50.0, SignalDirection.NEUTRAL)

        assert result.direction is SignalDirection.NEUTRAL
        assert result.confidence == pytest.approx(0.1, abs=0.01)
        assert "no_valid_indicators" in result.contributing_signals

    def test_contributing_signals_are_indicator_names(self) -> None:
        """Contributing signals should be valid IndicatorSignals field names."""
        signals = _make_signals(rsi=80.0, adx=75.0, obv=65.0)
        result = compute_direction_signal(signals, 70.0, SignalDirection.BULLISH)

        for signal_name in result.contributing_signals:
            if signal_name == "composite_score":
                continue  # Special fallback marker
            assert signal_name in ALL_INDICATOR_FIELDS, (
                f"'{signal_name}' is not an IndicatorSignals field"
            )

    def test_confidence_range(self) -> None:
        """Confidence is always within [0.1, 1.0]."""
        test_cases = [
            (_make_full_signals(100.0), 100.0, SignalDirection.BULLISH),
            (_make_full_signals(0.0), 0.0, SignalDirection.BEARISH),
            (_make_full_signals(50.0), 50.0, SignalDirection.NEUTRAL),
            (IndicatorSignals(), 50.0, SignalDirection.NEUTRAL),
        ]
        for signals, score, direction in test_cases:
            result = compute_direction_signal(signals, score, direction)
            assert 0.1 <= result.confidence <= 1.0, (
                f"Confidence {result.confidence} out of [0.1, 1.0] range"
            )

    def test_higher_agreement_means_higher_confidence(self) -> None:
        """More indicators agreeing with direction produces higher confidence."""
        # Few bullish signals
        few_signals = _make_signals(rsi=80.0)
        result_few = compute_direction_signal(few_signals, 70.0, SignalDirection.BULLISH)

        # Many bullish signals
        many_signals = _make_signals(
            rsi=80.0,
            adx=75.0,
            obv=70.0,
            sma_alignment=85.0,
            stochastic_rsi=80.0,
            supertrend=90.0,
            roc=65.0,
        )
        result_many = compute_direction_signal(many_signals, 80.0, SignalDirection.BULLISH)

        assert result_many.confidence >= result_few.confidence

    def test_result_is_frozen(self) -> None:
        """DirectionSignal is frozen (immutable)."""
        signals = _make_full_signals(50.0)
        result = compute_direction_signal(signals, 50.0, SignalDirection.NEUTRAL)

        with pytest.raises(Exception):  # noqa: B017
            result.confidence = 0.99  # type: ignore[misc]

    def test_at_least_one_contributing_signal(self) -> None:
        """There is always at least one contributing signal (model enforces >= 1)."""
        # Edge case: direction is BULLISH but all signals are < 60 (no bullish indicators)
        signals = _make_signals(rsi=50.0, adx=50.0)
        result = compute_direction_signal(signals, 50.0, SignalDirection.BULLISH)

        assert len(result.contributing_signals) >= 1
