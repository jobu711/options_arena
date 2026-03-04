"""Unit tests for options_arena.scoring.direction — signal classification."""

from options_arena.models.config import ScanConfig
from options_arena.models.enums import SignalDirection
from options_arena.scoring.direction import (
    _MILD_SIGNAL_WEIGHT,
    _STRONG_SIGNAL_WEIGHT,
    ROC_THRESHOLD,
    RSI_MIDPOINT,
    SMA_BEARISH_THRESHOLD,
    SMA_BULLISH_THRESHOLD,
    determine_direction,
)


class TestDetermineDirection:
    """Tests for determine_direction()."""

    def test_strong_bullish_overbought_rsi_bullish_sma(self) -> None:
        """Strong trend + overbought RSI + bullish SMA -> BULLISH."""
        result = determine_direction(adx=30.0, rsi=80.0, sma_alignment=1.0)
        assert result is SignalDirection.BULLISH

    def test_strong_bearish_oversold_rsi_bearish_sma(self) -> None:
        """Strong trend + oversold RSI + bearish SMA -> BEARISH."""
        result = determine_direction(adx=30.0, rsi=20.0, sma_alignment=-1.0)
        assert result is SignalDirection.BEARISH

    def test_weak_trend_returns_neutral(self) -> None:
        """Weak trend (ADX=10) -> NEUTRAL regardless of other inputs."""
        result = determine_direction(adx=10.0, rsi=80.0, sma_alignment=1.0)
        assert result is SignalDirection.NEUTRAL

    def test_adx_exactly_at_threshold_passes_gate(self) -> None:
        """ADX exactly at threshold (15.0) passes the gate (< not <=).

        With neutral RSI and SMA, both scores are 0, so the result is NEUTRAL
        from the zero-score path -- not from the ADX gate.
        """
        result = determine_direction(adx=15.0, rsi=50.0, sma_alignment=0.0)
        assert result is SignalDirection.NEUTRAL

    def test_adx_at_threshold_with_signals_not_filtered(self) -> None:
        """ADX exactly at threshold with strong signals produces a direction.

        Proves the gate uses strict < (not <=), so ADX=15.0 is not filtered.
        """
        result = determine_direction(adx=15.0, rsi=80.0, sma_alignment=1.0)
        assert result is SignalDirection.BULLISH

    def test_tiebreaker_positive_sma_returns_bullish(self) -> None:
        """Tiebreaker: tied scores with positive SMA -> BULLISH.

        RSI=60 (>50, bullish+=1), SMA=-0.6 (<-0.5, bearish+=1) -> tie at 1.
        SMA_alignment=-0.6 < 0 -> tiebreaker returns BEARISH? No, that gives
        different scores. Use: RSI=55 (mild bullish), SMA=-0.8 (bearish SMA).
        Actually: bullish=1 (RSI>50), bearish=1 (SMA<-0.5). Tie, sma=-0.8<0 -> BEARISH.

        For bullish tiebreaker: RSI=45 (<50, bearish+=1), SMA=0.6 (>0.5, bullish+=1).
        Tie at 1. sma=0.6 > 0 -> BULLISH.
        """
        result = determine_direction(adx=25.0, rsi=45.0, sma_alignment=0.6)
        assert result is SignalDirection.BULLISH

    def test_tiebreaker_negative_sma_returns_bearish(self) -> None:
        """Tiebreaker: tied scores with negative SMA -> BEARISH.

        RSI=55 (>50, bullish+=1), SMA=-0.8 (<-0.5, bearish+=1).
        Tie at 1. sma=-0.8 < 0 -> BEARISH.
        """
        result = determine_direction(adx=25.0, rsi=55.0, sma_alignment=-0.8)
        assert result is SignalDirection.BEARISH

    def test_no_signals_returns_neutral(self) -> None:
        """ADX=20 (above threshold), RSI=50 (no signal), SMA=0.0 (no signal) -> NEUTRAL."""
        result = determine_direction(adx=20.0, rsi=50.0, sma_alignment=0.0)
        assert result is SignalDirection.NEUTRAL

    def test_rsi_exactly_overbought_boundary(self) -> None:
        """RSI exactly at overbought (70.0) is NOT overbought (> not >=).

        RSI=70.0 falls into the elif rsi > 50 branch -> bullish += 1 (mild).
        """
        # RSI=70 (>50 but not >70) -> bullish += 1 (mild)
        # SMA=0.0 (neutral) -> no SMA signal
        # bullish=1, bearish=0 -> BULLISH
        result = determine_direction(adx=25.0, rsi=70.0, sma_alignment=0.0)
        assert result is SignalDirection.BULLISH

    def test_rsi_exactly_oversold_boundary(self) -> None:
        """RSI exactly at oversold (30.0) is NOT oversold (< not <=).

        RSI=30.0 falls into the elif rsi < 50 branch -> bearish += 1 (mild).
        """
        # RSI=30 (<50 but not <30) -> bearish += 1 (mild)
        # SMA=0.0 (neutral) -> no SMA signal
        # bearish=1, bullish=0 -> BEARISH
        result = determine_direction(adx=25.0, rsi=30.0, sma_alignment=0.0)
        assert result is SignalDirection.BEARISH

    def test_custom_config_raises_threshold(self) -> None:
        """Custom ScanConfig with higher ADX threshold -> ADX=20 now NEUTRAL."""
        config = ScanConfig(adx_trend_threshold=25.0)
        result = determine_direction(adx=20.0, rsi=80.0, sma_alignment=1.0, config=config)
        assert result is SignalDirection.NEUTRAL

    def test_custom_config_rsi_thresholds(self) -> None:
        """Custom ScanConfig with tighter RSI thresholds changes scoring."""
        config = ScanConfig(rsi_overbought=60.0, rsi_oversold=40.0)
        # RSI=65: with default thresholds (70) this is mild bullish
        # With custom threshold (60) this is strong bullish (>60)
        # bullish += 2, SMA=0.0 -> bullish=2, bearish=0 -> BULLISH
        result = determine_direction(adx=25.0, rsi=65.0, sma_alignment=0.0, config=config)
        assert result is SignalDirection.BULLISH

    def test_sma_exactly_at_bullish_boundary_no_signal(self) -> None:
        """SMA exactly at 0.5 is NOT bullish (> not >=), so no SMA signal.

        RSI=55 (>50, bullish+=1), SMA=0.5 (not >0.5, no signal).
        bullish=1, bearish=0 -> BULLISH (from RSI alone).
        """
        result = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.5)
        assert result is SignalDirection.BULLISH

    def test_sma_exactly_at_bearish_boundary_no_signal(self) -> None:
        """SMA exactly at -0.5 is NOT bearish (< not <=), so no SMA signal.

        RSI=45 (<50, bearish+=1), SMA=-0.5 (not <-0.5, no signal).
        bearish=1, bullish=0 -> BEARISH (from RSI alone).
        """
        result = determine_direction(adx=25.0, rsi=45.0, sma_alignment=-0.5)
        assert result is SignalDirection.BEARISH

    def test_default_config_used_when_none(self) -> None:
        """When config=None, production defaults are used."""
        # Same inputs should produce same result with explicit defaults
        result_none = determine_direction(adx=30.0, rsi=80.0, sma_alignment=1.0, config=None)
        result_default = determine_direction(
            adx=30.0, rsi=80.0, sma_alignment=1.0, config=ScanConfig()
        )
        assert result_none is result_default


class TestSupertrendInput:
    """Tests for supertrend confirmation signal in determine_direction()."""

    def test_supertrend_bullish_confirms(self) -> None:
        """Supertrend +1 adds bullish confirmation on top of RSI."""
        # Without supertrend: RSI=55 (mild bullish=1), SMA=0 -> BULLISH (score 1-0)
        base = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0)
        assert base is SignalDirection.BULLISH

        # With bullish supertrend: bullish score increases (2-0)
        with_st = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0, supertrend=1.0)
        assert with_st is SignalDirection.BULLISH

    def test_supertrend_bearish_confirms(self) -> None:
        """Supertrend -1 adds bearish confirmation on top of RSI."""
        base = determine_direction(adx=25.0, rsi=45.0, sma_alignment=0.0)
        assert base is SignalDirection.BEARISH

        with_st = determine_direction(adx=25.0, rsi=45.0, sma_alignment=0.0, supertrend=-1.0)
        assert with_st is SignalDirection.BEARISH

    def test_supertrend_contradicts_rsi_creates_tie(self) -> None:
        """Supertrend contradicting RSI can create a tie.

        RSI=55 (mild bullish=1), supertrend=-1 (bearish=1) -> tie at 1.
        SMA=0.0 -> NEUTRAL (exact zero in tiebreaker).
        """
        result = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0, supertrend=-1.0)
        assert result is SignalDirection.NEUTRAL

    def test_supertrend_breaks_otherwise_neutral(self) -> None:
        """Supertrend can break a neutral state (RSI=50, SMA=0).

        RSI=50 (no signal), SMA=0.0 (no signal), supertrend=1.0 -> bullish=1.
        """
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, supertrend=1.0)
        assert result is SignalDirection.BULLISH

    def test_supertrend_none_contributes_nothing(self) -> None:
        """None supertrend preserves original behavior exactly."""
        without = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0)
        with_none = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0, supertrend=None)
        assert without is with_none

    def test_supertrend_nan_ignored(self) -> None:
        """NaN supertrend contributes nothing (like None)."""
        result = determine_direction(
            adx=25.0, rsi=55.0, sma_alignment=0.0, supertrend=float("nan")
        )
        assert result is SignalDirection.BULLISH  # same as without

    def test_supertrend_zero_contributes_nothing(self) -> None:
        """Supertrend=0.0 is neither positive nor negative -- no signal."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, supertrend=0.0)
        assert result is SignalDirection.NEUTRAL


class TestRocInput:
    """Tests for ROC (rate of change) confirmation signal."""

    def test_roc_strong_positive_bullish(self) -> None:
        """ROC > threshold adds bullish confirmation."""
        # RSI=50 (no signal), SMA=0 (no signal), roc=10% -> bullish=1
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=10.0)
        assert result is SignalDirection.BULLISH

    def test_roc_strong_negative_bearish(self) -> None:
        """ROC < -threshold adds bearish confirmation."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=-10.0)
        assert result is SignalDirection.BEARISH

    def test_roc_within_threshold_no_signal(self) -> None:
        """ROC within +/-threshold contributes nothing."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=3.0)
        assert result is SignalDirection.NEUTRAL

    def test_roc_exactly_at_threshold_no_signal(self) -> None:
        """ROC exactly at +threshold is NOT a signal (> not >=)."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=ROC_THRESHOLD)
        assert result is SignalDirection.NEUTRAL

    def test_roc_exactly_at_neg_threshold_no_signal(self) -> None:
        """ROC exactly at -threshold is NOT a signal (< not <=)."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=-ROC_THRESHOLD)
        assert result is SignalDirection.NEUTRAL

    def test_roc_none_contributes_nothing(self) -> None:
        """None ROC preserves original behavior."""
        without = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0)
        with_none = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.0, roc=None)
        assert without is with_none

    def test_roc_nan_ignored(self) -> None:
        """NaN ROC contributes nothing."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=float("nan"))
        assert result is SignalDirection.NEUTRAL

    def test_roc_inf_ignored(self) -> None:
        """Inf ROC contributes nothing."""
        result = determine_direction(adx=25.0, rsi=50.0, sma_alignment=0.0, roc=float("inf"))
        assert result is SignalDirection.NEUTRAL


class TestCombinedNewSignals:
    """Tests for supertrend + roc together with existing signals."""

    def test_all_signals_bullish_maximum(self) -> None:
        """RSI overbought + SMA bullish + supertrend +1 + ROC > 5% -> BULLISH.

        Max bullish score = 2 (RSI) + 1 (SMA) + 1 (ST) + 1 (ROC) = 5.
        """
        result = determine_direction(
            adx=30.0, rsi=80.0, sma_alignment=1.0, supertrend=1.0, roc=10.0
        )
        assert result is SignalDirection.BULLISH

    def test_all_signals_bearish_maximum(self) -> None:
        """RSI oversold + SMA bearish + supertrend -1 + ROC < -5% -> BEARISH.

        Max bearish score = 2 (RSI) + 1 (SMA) + 1 (ST) + 1 (ROC) = 5.
        """
        result = determine_direction(
            adx=30.0, rsi=20.0, sma_alignment=-1.0, supertrend=-1.0, roc=-10.0
        )
        assert result is SignalDirection.BEARISH

    def test_supertrend_and_roc_override_mild_rsi(self) -> None:
        """Supertrend + ROC bearish (2) outweigh mild RSI bullish (1).

        RSI=55 (mild bullish=1), supertrend=-1 (bearish=1), roc=-10 (bearish=1).
        bullish=1, bearish=2 -> BEARISH.
        """
        result = determine_direction(
            adx=25.0, rsi=55.0, sma_alignment=0.0, supertrend=-1.0, roc=-10.0
        )
        assert result is SignalDirection.BEARISH

    def test_conflicting_supertrend_roc(self) -> None:
        """Supertrend bullish + ROC bearish cancel each other.

        RSI=50 (no signal), SMA=0 (no signal), supertrend=1 (bullish=1),
        roc=-10 (bearish=1) -> tie at 1. SMA=0 -> NEUTRAL.
        """
        result = determine_direction(
            adx=25.0, rsi=50.0, sma_alignment=0.0, supertrend=1.0, roc=-10.0
        )
        assert result is SignalDirection.NEUTRAL

    def test_backward_compatible_all_none(self) -> None:
        """All new params as None matches legacy behavior exactly."""
        legacy = determine_direction(adx=25.0, rsi=55.0, sma_alignment=0.6)
        modern = determine_direction(
            adx=25.0,
            rsi=55.0,
            sma_alignment=0.6,
            supertrend=None,
            roc=None,
        )
        assert legacy is modern


class TestModuleConstants:
    """Verify module-level constants have expected values."""

    def test_rsi_midpoint(self) -> None:
        assert RSI_MIDPOINT == 50.0

    def test_sma_bullish_threshold(self) -> None:
        assert SMA_BULLISH_THRESHOLD == 0.5

    def test_sma_bearish_threshold(self) -> None:
        assert SMA_BEARISH_THRESHOLD == -0.5

    def test_strong_signal_weight(self) -> None:
        assert _STRONG_SIGNAL_WEIGHT == 2

    def test_mild_signal_weight(self) -> None:
        assert _MILD_SIGNAL_WEIGHT == 1

    def test_roc_threshold(self) -> None:
        assert ROC_THRESHOLD == 5.0
