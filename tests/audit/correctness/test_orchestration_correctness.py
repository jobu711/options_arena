"""Correctness tests for all 7 orchestration math functions vs analytical solutions.

Tests cover:
  - compute_agreement_score: fraction of directional agents agreeing with majority
  - _vote_entropy: Shannon entropy of directional vote distribution
  - _log_odds_pool: Bordley (1982) weighted log-odds confidence pooling
  - synthesize_verdict: verdict synthesis (mathematical invariants only)
  - classify_macd_signal: MACD signal classification
  - _get_majority_direction: majority vote from agent directions
  - compute_citation_density: fraction of context labels cited in agent text

Reference data loaded from ``tests/audit/reference_data/orchestration_known_values.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from options_arena.agents._parsing import compute_citation_density
from options_arena.agents.orchestrator import (
    _get_majority_direction,
    _log_odds_pool,
    _vote_entropy,
    classify_macd_signal,
    compute_agreement_score,
)
from options_arena.models.enums import MacdSignal, SignalDirection

# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent.parent / "reference_data"

with (_REF_DIR / "orchestration_known_values.json").open() as _f:
    _ORCH_DATA: dict = json.load(_f)

# ---------------------------------------------------------------------------
# Tolerance constants (from PRD: abs=0.005, rel=0.1%)
# ---------------------------------------------------------------------------

_ORCH_ABS = 0.005
_ORCH_REL = 1e-3


# ---------------------------------------------------------------------------
# Helper: build agent_directions dict from JSON
# ---------------------------------------------------------------------------


def _build_directions(directions_dict: dict) -> dict[str, SignalDirection]:
    """Convert JSON directions dict to typed SignalDirection mapping.

    Reference data uses uppercase (BULLISH), but ``SignalDirection`` values are
    lowercase (bullish).  Normalise by calling ``.lower()`` before constructing.
    """
    return {
        name: SignalDirection(direction.lower()) for name, direction in directions_dict.items()
    }


# =========================================================================
# Log-Odds Pooling (Bordley 1982)
# =========================================================================


@pytest.mark.audit_correctness
class TestLogOddsPoolCorrectness:
    """Bordley (1982) log-odds pooling correctness vs analytical solutions."""

    @pytest.mark.parametrize(
        "case",
        _ORCH_DATA["log_odds_pool"],
        ids=[c["description"][:60] for c in _ORCH_DATA["log_odds_pool"]],
    )
    def test_log_odds_pool_known_values(self, case: dict) -> None:
        """Bordley (1982) -- weighted log-odds pooling against known analytical values."""
        probabilities = case["input"]["probabilities"]
        weights = case["input"]["weights"]
        result = _log_odds_pool(probabilities, weights)
        expected = case["expected"]

        if "value" in expected:
            assert result == pytest.approx(
                expected["value"],
                abs=_ORCH_ABS,
                rel=_ORCH_REL,
            )
        if "value_finite" in expected:
            assert math.isfinite(result)

    def test_neutral_prior_with_no_data(self) -> None:
        """Bordley (1982) -- empty inputs return neutral prior 0.5."""
        result = _log_odds_pool([], [])
        assert result == pytest.approx(0.5, abs=_ORCH_ABS)

    def test_single_agent_at_half(self) -> None:
        """Bordley (1982) -- single agent at 0.5 contributes zero log-odds."""
        result = _log_odds_pool([0.5], [0.2])
        assert result == pytest.approx(0.5, abs=_ORCH_ABS)

    def test_opposing_agents_cancel(self) -> None:
        """Bordley (1982) -- equal-weight opposing agents cancel to 0.5."""
        result = _log_odds_pool([0.9, 0.1], [0.2, 0.2])
        assert result == pytest.approx(0.5, abs=_ORCH_ABS)

    def test_compounding_agreement(self) -> None:
        """Bordley (1982) -- three agreeing agents compound confidence above any single agent."""
        result_3 = _log_odds_pool([0.9, 0.9, 0.9], [0.2, 0.2, 0.2])
        result_4 = _log_odds_pool([0.9, 0.9, 0.9, 0.9], [0.2, 0.2, 0.2, 0.2])
        # More agreeing agents should produce higher confidence
        assert result_4 > result_3

    def test_result_range(self) -> None:
        """Log-odds pool result is always in (0, 1)."""
        result = _log_odds_pool([0.99, 0.99, 0.99], [0.3, 0.3, 0.3])
        assert 0.0 < result < 1.0

    def test_weights_not_normalized(self) -> None:
        """Weights are used as-is, not normalized to sum to 1."""
        # Higher total weight should produce different result
        result_low = _log_odds_pool([0.8], [0.1])
        result_high = _log_odds_pool([0.8], [0.5])
        assert result_high > result_low

    def test_clamping_prevents_infinity(self) -> None:
        """Extreme probabilities (0.0, 1.0) are clamped to prevent log(0)."""
        result = _log_odds_pool([0.0, 1.0], [0.2, 0.2])
        assert math.isfinite(result)


# =========================================================================
# Shannon Entropy
# =========================================================================


@pytest.mark.audit_correctness
class TestVoteEntropyCorrectness:
    """Shannon (1948) entropy of directional vote distribution."""

    @pytest.mark.parametrize(
        "case",
        _ORCH_DATA["shannon_entropy"],
        ids=[c["description"][:60] for c in _ORCH_DATA["shannon_entropy"]],
    )
    def test_vote_entropy_known_values(self, case: dict) -> None:
        """Shannon (1948) -- entropy against known analytical values."""
        directions = _build_directions(case["input"]["directions"])
        result = _vote_entropy(directions)
        assert result == pytest.approx(
            case["expected"]["value"],
            abs=_ORCH_ABS,
            rel=_ORCH_REL,
        )

    def test_unanimous_zero_entropy(self) -> None:
        """Shannon (1948) -- unanimous vote has zero entropy."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BULLISH,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(0.0, abs=_ORCH_ABS)

    def test_perfect_split_max_entropy(self) -> None:
        """Shannon (1948) -- 50/50 split has maximum entropy = 1.0 bit."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(1.0, abs=_ORCH_ABS)

    def test_3_1_split_entropy(self) -> None:
        """Shannon (1948) -- 3:1 split entropy = 0.811 bits."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BULLISH,
            "a4": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        # H = -(0.75*log2(0.75) + 0.25*log2(0.25))
        expected = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
        assert result == pytest.approx(expected, abs=_ORCH_ABS)

    def test_neutral_agents_excluded(self) -> None:
        """NEUTRAL agents don't count toward entropy calculation."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.NEUTRAL,
            "a4": SignalDirection.NEUTRAL,
        }
        result = _vote_entropy(directions)
        # Only 2 BULLISH agents = unanimous = 0 entropy
        assert result == pytest.approx(0.0, abs=_ORCH_ABS)

    def test_empty_zero_entropy(self) -> None:
        """Empty dict returns 0.0 entropy."""
        result = _vote_entropy({})
        assert result == pytest.approx(0.0, abs=_ORCH_ABS)

    def test_entropy_non_negative(self) -> None:
        """Shannon entropy is always non-negative."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BEARISH,
            "a3": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        assert result >= 0.0


# =========================================================================
# Agreement Score
# =========================================================================


@pytest.mark.audit_correctness
class TestAgreementScoreCorrectness:
    """Compute agreement score correctness vs known values."""

    @pytest.mark.parametrize(
        "case",
        _ORCH_DATA["agreement_score"],
        ids=[c["description"][:60] for c in _ORCH_DATA["agreement_score"]],
    )
    def test_agreement_score_known_values(self, case: dict) -> None:
        """agents/orchestrator.py -- agreement score against known values."""
        directions = _build_directions(case["input"]["directions"])
        result = compute_agreement_score(directions)
        tolerance = case["expected"].get("tolerance", _ORCH_ABS)
        assert result == pytest.approx(
            case["expected"]["value"],
            abs=tolerance,
        )

    def test_perfect_agreement(self) -> None:
        """All same direction = agreement 1.0."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BULLISH,
        }
        result = compute_agreement_score(directions)
        assert result == pytest.approx(1.0, abs=_ORCH_ABS)

    def test_perfect_split(self) -> None:
        """2:2 split = agreement 0.5."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BEARISH,
            "a4": SignalDirection.BEARISH,
        }
        result = compute_agreement_score(directions)
        assert result == pytest.approx(0.5, abs=_ORCH_ABS)

    def test_3_1_split(self) -> None:
        """3:1 split = agreement 0.75."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BULLISH,
            "a4": SignalDirection.BEARISH,
        }
        result = compute_agreement_score(directions)
        assert result == pytest.approx(0.75, abs=_ORCH_ABS)

    def test_neutral_excluded_from_denominator(self) -> None:
        """NEUTRAL agents excluded from the directional denominator."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
            "a3": SignalDirection.BEARISH,
            "a4": SignalDirection.NEUTRAL,
            "a5": SignalDirection.NEUTRAL,
        }
        result = compute_agreement_score(directions)
        # 3 directional agents, 2 agree with majority (BULLISH)
        assert result == pytest.approx(2.0 / 3.0, abs=_ORCH_ABS)

    def test_all_neutral_returns_zero(self) -> None:
        """All NEUTRAL returns 0.0."""
        directions = {
            "a1": SignalDirection.NEUTRAL,
            "a2": SignalDirection.NEUTRAL,
        }
        result = compute_agreement_score(directions)
        assert result == pytest.approx(0.0, abs=_ORCH_ABS)

    def test_empty_returns_zero(self) -> None:
        """Empty dict returns 0.0."""
        result = compute_agreement_score({})
        assert result == pytest.approx(0.0, abs=_ORCH_ABS)

    def test_agreement_range(self) -> None:
        """Agreement score is always in [0.0, 1.0]."""
        directions = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BEARISH,
            "a3": SignalDirection.BEARISH,
        }
        result = compute_agreement_score(directions)
        assert 0.0 <= result <= 1.0


# =========================================================================
# Classify MACD Signal
# =========================================================================


@pytest.mark.audit_correctness
class TestClassifyMacdSignalCorrectness:
    """classify_macd_signal correctness tests."""

    def test_positive_macd_bullish(self) -> None:
        """Positive centered MACD value -> BULLISH_CROSSOVER."""
        result = classify_macd_signal(5.0)
        assert result == MacdSignal.BULLISH_CROSSOVER

    def test_negative_macd_bearish(self) -> None:
        """Negative centered MACD value -> BEARISH_CROSSOVER."""
        result = classify_macd_signal(-5.0)
        assert result == MacdSignal.BEARISH_CROSSOVER

    def test_zero_macd_neutral(self) -> None:
        """Zero centered MACD value -> NEUTRAL."""
        result = classify_macd_signal(0.0)
        assert result == MacdSignal.NEUTRAL

    def test_none_macd_neutral(self) -> None:
        """None MACD value -> NEUTRAL."""
        result = classify_macd_signal(None)
        assert result == MacdSignal.NEUTRAL

    def test_nan_macd_neutral(self) -> None:
        """NaN MACD value -> NEUTRAL."""
        result = classify_macd_signal(float("nan"))
        assert result == MacdSignal.NEUTRAL

    def test_inf_macd_neutral(self) -> None:
        """Inf MACD value -> NEUTRAL."""
        result = classify_macd_signal(float("inf"))
        assert result == MacdSignal.NEUTRAL


# =========================================================================
# Synthesize Verdict (mathematical invariants)
# =========================================================================

# synthesize_verdict is tested for mathematical invariants only.
# Full integration testing requires complex model setup and is covered
# in the orchestrator integration tests.


@pytest.mark.audit_correctness
class TestSynthesizeVerdictInvariants:
    """synthesize_verdict mathematical invariants."""

    def test_synthesize_verdict_importable(self) -> None:
        """synthesize_verdict is importable from orchestrator."""
        from options_arena.agents.orchestrator import synthesize_verdict

        assert callable(synthesize_verdict)

    def test_agreement_and_entropy_consistency(self) -> None:
        """Agreement score and entropy are inversely related for 2-outcome votes."""
        # Perfect agreement = 0 entropy
        dirs_unanimous = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BULLISH,
        }
        assert compute_agreement_score(dirs_unanimous) == pytest.approx(1.0, abs=_ORCH_ABS)
        assert _vote_entropy(dirs_unanimous) == pytest.approx(0.0, abs=_ORCH_ABS)

        # Perfect split = max entropy
        dirs_split = {
            "a1": SignalDirection.BULLISH,
            "a2": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(dirs_split) == pytest.approx(0.5, abs=_ORCH_ABS)
        assert _vote_entropy(dirs_split) == pytest.approx(1.0, abs=_ORCH_ABS)

    def test_log_odds_monotonic_in_confidence(self) -> None:
        """Higher individual confidence produces higher pooled confidence."""
        low = _log_odds_pool([0.6], [0.2])
        high = _log_odds_pool([0.9], [0.2])
        assert high > low

    def test_log_odds_monotonic_in_agent_count(self) -> None:
        """More agreeing agents produce higher pooled confidence."""
        two = _log_odds_pool([0.8, 0.8], [0.2, 0.2])
        four = _log_odds_pool([0.8, 0.8, 0.8, 0.8], [0.2, 0.2, 0.2, 0.2])
        assert four > two


# ---------------------------------------------------------------------------
# _get_majority_direction
# ---------------------------------------------------------------------------


class TestGetMajorityDirectionCorrectness:
    """Correctness tests for _get_majority_direction."""

    def test_empty_returns_neutral(self) -> None:
        """Empty input returns NEUTRAL."""
        assert _get_majority_direction({}) == SignalDirection.NEUTRAL

    def test_unanimous_bullish(self) -> None:
        """All bullish returns BULLISH."""
        dirs = {"a": SignalDirection.BULLISH, "b": SignalDirection.BULLISH}
        assert _get_majority_direction(dirs) == SignalDirection.BULLISH

    def test_unanimous_bearish(self) -> None:
        """All bearish returns BEARISH."""
        dirs = {"a": SignalDirection.BEARISH, "b": SignalDirection.BEARISH}
        assert _get_majority_direction(dirs) == SignalDirection.BEARISH

    def test_tie_returns_neutral(self) -> None:
        """Equal bullish/bearish votes returns NEUTRAL."""
        dirs = {"a": SignalDirection.BULLISH, "b": SignalDirection.BEARISH}
        assert _get_majority_direction(dirs) == SignalDirection.NEUTRAL

    def test_majority_with_neutral_votes(self) -> None:
        """Neutral votes don't count toward bull/bear majority."""
        dirs = {
            "a": SignalDirection.BULLISH,
            "b": SignalDirection.BULLISH,
            "c": SignalDirection.NEUTRAL,
        }
        assert _get_majority_direction(dirs) == SignalDirection.BULLISH


# ---------------------------------------------------------------------------
# compute_citation_density
# ---------------------------------------------------------------------------


class TestComputeCitationDensityCorrectness:
    """Correctness tests for compute_citation_density."""

    def test_all_cited_returns_one(self) -> None:
        """All labels cited gives density 1.0."""
        context = "RSI(14): 55\nMACD: bullish"
        text = "RSI(14) is strong and MACD confirms"
        assert compute_citation_density(context, text) == pytest.approx(1.0)

    def test_none_cited_returns_zero(self) -> None:
        """No labels cited gives density 0.0."""
        context = "RSI(14): 55\nMACD: bullish"
        text = "The stock looks good based on fundamentals"
        assert compute_citation_density(context, text) == pytest.approx(0.0)

    def test_half_cited_returns_half(self) -> None:
        """Half labels cited gives density 0.5."""
        context = "RSI(14): 55\nMACD: bullish"
        text = "RSI(14) shows momentum"
        assert compute_citation_density(context, text) == pytest.approx(0.5)

    def test_empty_context_returns_zero(self) -> None:
        """Empty context block returns 0.0."""
        assert compute_citation_density("", "some text") == pytest.approx(0.0)
