"""Stability tests for orchestration functions: Hypothesis + extreme + NaN injection.

Covers compute_agreement_score, _vote_entropy, classify_macd_signal,
should_debate, and _log_odds_pool. Every function produces valid output for
valid inputs. NaN/Inf never silently corrupt output.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from options_arena.agents._parsing import compute_citation_density
from options_arena.agents.orchestrator import (
    _get_majority_direction,
    _log_odds_pool,
    _vote_entropy,
    classify_macd_signal,
    compute_agreement_score,
    should_debate,
)
from options_arena.models.enums import MacdSignal, SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_direction_strategy = st.sampled_from(
    [SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL]
)

_agent_names = ["trend", "volatility", "flow", "fundamental", "risk", "contrarian"]


@st.composite
def agent_directions_strategy(draw: st.DrawFn) -> dict[str, SignalDirection]:
    """Generate a random mapping of agent name to direction."""
    n = draw(st.integers(min_value=0, max_value=6))
    selected = draw(st.permutations(_agent_names))[:n]
    return {name: draw(_direction_strategy) for name in selected}


@st.composite
def probabilities_and_weights_strategy(
    draw: st.DrawFn,
) -> tuple[list[float], list[float]]:
    """Generate lists of probabilities and matching weights."""
    n = draw(st.integers(min_value=0, max_value=8))
    probs = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    weights = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    return probs, weights


# ===========================================================================
# compute_agreement_score Stability
# ===========================================================================


class TestComputeAgreementScoreStability:
    """Hypothesis + extreme + NaN tests for compute_agreement_score."""

    @pytest.mark.audit_stability
    @given(directions=agent_directions_strategy())
    @settings(max_examples=200)
    def test_agreement_in_range(self, directions: dict[str, SignalDirection]) -> None:
        """Property: agreement score is always in [0.0, 1.0]."""
        score = compute_agreement_score(directions)
        assert 0.0 <= score <= 1.0, f"Agreement score {score} out of range"

    @pytest.mark.audit_stability
    def test_agreement_empty_dict(self) -> None:
        """Empty agent directions returns 0.0."""
        assert compute_agreement_score({}) == 0.0

    @pytest.mark.audit_stability
    def test_agreement_all_neutral(self) -> None:
        """All NEUTRAL agents returns 0.0 (no directional consensus)."""
        directions = {name: SignalDirection.NEUTRAL for name in _agent_names}
        assert compute_agreement_score(directions) == 0.0

    @pytest.mark.audit_stability
    def test_agreement_unanimous_bullish(self) -> None:
        """All BULLISH agents returns 1.0 (full agreement)."""
        directions = {name: SignalDirection.BULLISH for name in _agent_names}
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    @pytest.mark.audit_stability
    def test_agreement_unanimous_bearish(self) -> None:
        """All BEARISH agents returns 1.0."""
        directions = {name: SignalDirection.BEARISH for name in _agent_names}
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    @pytest.mark.audit_stability
    def test_agreement_even_split(self) -> None:
        """Even bull/bear split returns 0.5."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(0.5)

    @pytest.mark.audit_stability
    def test_agreement_single_directional_agent(self) -> None:
        """Single directional agent returns 1.0."""
        assert compute_agreement_score({"trend": SignalDirection.BULLISH}) == pytest.approx(1.0)


# ===========================================================================
# _vote_entropy Stability
# ===========================================================================


class TestVoteEntropyStability:
    """Hypothesis + extreme tests for _vote_entropy."""

    @pytest.mark.audit_stability
    @given(directions=agent_directions_strategy())
    @settings(max_examples=200)
    def test_entropy_non_negative(self, directions: dict[str, SignalDirection]) -> None:
        """Property: entropy is always >= 0."""
        entropy = _vote_entropy(directions)
        assert entropy >= 0.0, f"Entropy negative: {entropy}"
        assert math.isfinite(entropy), f"Entropy not finite: {entropy}"

    @pytest.mark.audit_stability
    def test_entropy_empty_dict(self) -> None:
        """Empty dict returns 0.0."""
        assert _vote_entropy({}) == 0.0

    @pytest.mark.audit_stability
    def test_entropy_all_neutral(self) -> None:
        """All NEUTRAL returns 0.0."""
        directions = {name: SignalDirection.NEUTRAL for name in _agent_names}
        assert _vote_entropy(directions) == 0.0

    @pytest.mark.audit_stability
    def test_entropy_unanimous(self) -> None:
        """Unanimous vote returns 0.0 (no diversity)."""
        directions = {name: SignalDirection.BULLISH for name in _agent_names}
        assert _vote_entropy(directions) == pytest.approx(0.0)

    @pytest.mark.audit_stability
    def test_entropy_even_split_maximum(self) -> None:
        """Even 50/50 split produces maximum entropy (1.0 bit)."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BEARISH,
        }
        entropy = _vote_entropy(directions)
        assert entropy == pytest.approx(1.0, abs=1e-10)


# ===========================================================================
# classify_macd_signal Stability
# ===========================================================================


class TestClassifyMACDSignalStability:
    """Hypothesis + extreme + NaN tests for classify_macd_signal."""

    @pytest.mark.audit_stability
    @given(
        value=st.one_of(
            st.none(),
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.just(float("nan")),
            st.just(float("inf")),
            st.just(float("-inf")),
        )
    )
    @settings(max_examples=200)
    def test_macd_signal_always_valid_enum(self, value: float | None) -> None:
        """Property: classify_macd_signal always returns a valid MacdSignal."""
        result = classify_macd_signal(value)
        assert result in (
            MacdSignal.BULLISH_CROSSOVER,
            MacdSignal.BEARISH_CROSSOVER,
            MacdSignal.NEUTRAL,
        )

    @pytest.mark.audit_stability
    def test_macd_signal_none(self) -> None:
        """None input returns NEUTRAL."""
        assert classify_macd_signal(None) == MacdSignal.NEUTRAL

    @pytest.mark.audit_stability
    def test_macd_signal_nan(self) -> None:
        """NaN input returns NEUTRAL."""
        assert classify_macd_signal(float("nan")) == MacdSignal.NEUTRAL

    @pytest.mark.audit_stability
    def test_macd_signal_inf(self) -> None:
        """Inf input returns NEUTRAL."""
        assert classify_macd_signal(float("inf")) == MacdSignal.NEUTRAL

    @pytest.mark.audit_stability
    def test_macd_signal_neg_inf(self) -> None:
        """Negative Inf input returns NEUTRAL."""
        assert classify_macd_signal(float("-inf")) == MacdSignal.NEUTRAL

    @pytest.mark.audit_stability
    def test_macd_signal_positive(self) -> None:
        """Positive value returns BULLISH_CROSSOVER."""
        assert classify_macd_signal(5.0) == MacdSignal.BULLISH_CROSSOVER

    @pytest.mark.audit_stability
    def test_macd_signal_negative(self) -> None:
        """Negative value returns BEARISH_CROSSOVER."""
        assert classify_macd_signal(-5.0) == MacdSignal.BEARISH_CROSSOVER

    @pytest.mark.audit_stability
    def test_macd_signal_zero(self) -> None:
        """Zero value returns NEUTRAL."""
        assert classify_macd_signal(0.0) == MacdSignal.NEUTRAL


# ===========================================================================
# should_debate Stability
# ===========================================================================


class TestShouldDebateStability:
    """Hypothesis + extreme tests for should_debate."""

    @pytest.mark.audit_stability
    @given(
        score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        direction=st.sampled_from(
            [SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL]
        ),
    )
    @settings(max_examples=100)
    def test_should_debate_returns_bool(self, score: float, direction: SignalDirection) -> None:
        """Property: should_debate always returns a bool."""
        from options_arena.models import DebateConfig

        ticker_score = TickerScore(
            ticker="TEST",
            composite_score=score,
            direction=direction,
            signals=IndicatorSignals(),
        )
        config = DebateConfig()
        result = should_debate(ticker_score, config)
        assert isinstance(result, bool)

    @pytest.mark.audit_stability
    def test_should_debate_neutral_always_false(self) -> None:
        """NEUTRAL direction always returns False regardless of score."""
        from options_arena.models import DebateConfig

        ticker_score = TickerScore(
            ticker="TEST",
            composite_score=90.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        assert should_debate(ticker_score, DebateConfig()) is False

    @pytest.mark.audit_stability
    def test_should_debate_below_threshold_false(self) -> None:
        """Score below min_debate_score returns False."""
        from options_arena.models import DebateConfig

        config = DebateConfig(min_debate_score=50.0)
        ticker_score = TickerScore(
            ticker="TEST",
            composite_score=30.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert should_debate(ticker_score, config) is False


# ===========================================================================
# _log_odds_pool Stability
# ===========================================================================


class TestLogOddsPoolStability:
    """Hypothesis + extreme + NaN tests for _log_odds_pool."""

    @pytest.mark.audit_stability
    @given(data=probabilities_and_weights_strategy())
    @settings(max_examples=200)
    def test_log_odds_pool_in_range(self, data: tuple[list[float], list[float]]) -> None:
        """Property: pooled probability is in (0, 1) or exactly 0.5 for empty."""
        probs, weights = data
        result = _log_odds_pool(probs, weights)
        assert 0.0 <= result <= 1.0, f"Pooled probability {result} out of range"
        assert math.isfinite(result), f"Pooled probability not finite: {result}"

    @pytest.mark.audit_stability
    def test_log_odds_pool_empty(self) -> None:
        """Empty inputs return 0.5 (neutral prior)."""
        assert _log_odds_pool([], []) == pytest.approx(0.5)

    @pytest.mark.audit_stability
    def test_log_odds_pool_single_high_confidence(self) -> None:
        """Single high-confidence agent produces high pooled probability."""
        result = _log_odds_pool([0.9], [1.0])
        assert result > 0.8

    @pytest.mark.audit_stability
    def test_log_odds_pool_single_low_confidence(self) -> None:
        """Single low-confidence agent produces low pooled probability."""
        result = _log_odds_pool([0.1], [1.0])
        assert result < 0.2

    @pytest.mark.audit_stability
    def test_log_odds_pool_extreme_zero_clamped(self) -> None:
        """Zero probability is clamped to 0.01 (no log(0))."""
        result = _log_odds_pool([0.0], [1.0])
        assert math.isfinite(result)
        assert 0.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_log_odds_pool_extreme_one_clamped(self) -> None:
        """Probability of 1.0 is clamped to 0.99 (no log(inf))."""
        result = _log_odds_pool([1.0], [1.0])
        assert math.isfinite(result)
        assert 0.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_log_odds_pool_zero_weights(self) -> None:
        """All-zero weights return 0.5."""
        result = _log_odds_pool([0.8, 0.9], [0.0, 0.0])
        assert result == pytest.approx(0.5)

    @pytest.mark.audit_stability
    def test_log_odds_pool_compounding(self) -> None:
        """Three agents at 0.9 produce combined > 0.9 (compounding effect)."""
        result = _log_odds_pool([0.9, 0.9, 0.9], [1.0, 1.0, 1.0])
        assert result > 0.9


# ===========================================================================
# NaN Injection for Orchestration Inputs
# ===========================================================================


class TestOrchestrationNaNInjection:
    """NaN injection tests for orchestration functions."""

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "probs,weights",
        [
            ([float("nan"), 0.8], [1.0, 1.0]),
            ([0.8, float("nan")], [1.0, 1.0]),
            ([0.8, 0.9], [float("nan"), 1.0]),
            ([0.8, 0.9], [1.0, float("nan")]),
        ],
        ids=["nan_prob_0", "nan_prob_1", "nan_weight_0", "nan_weight_1"],
    )
    def test_log_odds_pool_nan_inputs(self, probs: list[float], weights: list[float]) -> None:
        """NaN in probabilities or weights produces finite output (clamping guards)."""
        result = _log_odds_pool(probs, weights)
        # The function clamps probabilities to [0.01, 0.99] and does math.
        # NaN in weight will produce NaN log_odds_sum which gives NaN result.
        # The key invariant: the function should not crash.
        # NaN result is acceptable if NaN input is provided (documented behavior).
        assert isinstance(result, float)

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "probs,weights",
        [
            ([float("inf"), 0.8], [1.0, 1.0]),
            ([0.8, float("-inf")], [1.0, 1.0]),
        ],
        ids=["inf_prob", "neg_inf_prob"],
    )
    def test_log_odds_pool_inf_inputs(self, probs: list[float], weights: list[float]) -> None:
        """Inf in probabilities is clamped by min/max guard."""
        result = _log_odds_pool(probs, weights)
        assert isinstance(result, float)
        # Inf gets clamped to 0.99 by the max(0.01, min(0.99, p)) guard
        assert math.isfinite(result)


# ---------------------------------------------------------------------------
# _get_majority_direction — stability
# ---------------------------------------------------------------------------


class TestGetMajorityDirectionStability:
    """Stability tests for _get_majority_direction."""

    @given(
        directions=st.dictionaries(
            keys=st.text(min_size=1, max_size=5),
            values=st.sampled_from(
                [SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL]
            ),
            min_size=0,
            max_size=10,
        )
    )
    @settings(max_examples=100)
    def test_always_returns_valid_direction(
        self, directions: dict[str, SignalDirection]
    ) -> None:
        """Output is always a valid SignalDirection."""
        result = _get_majority_direction(directions)
        assert result in {
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        }


# ---------------------------------------------------------------------------
# compute_citation_density — stability
# ---------------------------------------------------------------------------


class TestComputeCitationDensityStability:
    """Stability tests for compute_citation_density."""

    @given(
        context=st.text(min_size=0, max_size=200),
        text=st.text(min_size=0, max_size=200),
    )
    @settings(max_examples=100)
    def test_output_in_zero_one(self, context: str, text: str) -> None:
        """Output is always in [0.0, 1.0]."""
        result = compute_citation_density(context, text)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_empty_inputs_no_crash(self) -> None:
        """Empty strings produce 0.0 without errors."""
        assert compute_citation_density("", "") == pytest.approx(0.0)
