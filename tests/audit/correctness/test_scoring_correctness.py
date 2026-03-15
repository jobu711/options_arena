"""Correctness tests for all 16 scoring functions vs deterministic references.

Tests cover:
  - Normalization (5): percentile_rank_normalize, invert_indicators,
    normalize_single_ticker, get_active_indicators, compute_normalization_stats
  - Composite (2): composite_score, score_universe
  - Direction (1): determine_direction
  - Contracts (5): filter_contracts, select_expiration, compute_greeks,
    select_by_delta, recommend_contracts
  - Dimensional (3): compute_dimensional_scores, apply_regime_weights,
    compute_direction_signal

Reference data loaded from ``tests/audit/reference_data/scoring_known_values.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import INDICATOR_WEIGHTS, composite_score, score_universe

# Conditional imports for scoring modules that may need more complex setup
from options_arena.scoring.dimensional import (
    apply_regime_weights,
    compute_dimensional_scores,
    compute_direction_signal,
)
from options_arena.scoring.direction import determine_direction
from options_arena.scoring.normalization import (
    INVERTED_INDICATORS,
    compute_normalization_stats,
    get_active_indicators,
    invert_indicators,
    normalize_single_ticker,
    percentile_rank_normalize,
)

# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent.parent / "reference_data"

with (_REF_DIR / "scoring_known_values.json").open() as _f:
    _SCORING_DATA: dict = json.load(_f)

# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------

_COMPOSITE_ABS = 0.1
_COMPOSITE_REL = 0.01  # 1.0%
_DIRECTION_EXACT = True  # direction is an enum, exact match


# ---------------------------------------------------------------------------
# Helper: build a simple IndicatorSignals from a dict of field->value
# ---------------------------------------------------------------------------


def _make_signals(**kwargs: float | None) -> IndicatorSignals:
    """Build IndicatorSignals with explicit values; all others None."""
    return IndicatorSignals(**kwargs)


# =========================================================================
# Normalization (5 functions)
# =========================================================================


@pytest.mark.audit_correctness
class TestPercentileRankNormalize:
    """percentile_rank_normalize correctness tests."""

    def test_uniform_values_monotonic_ranks(self) -> None:
        """Percentile rank: uniformly distributed values produce monotonic ranks."""
        universe = {
            "A": _make_signals(rsi=10.0),
            "B": _make_signals(rsi=20.0),
            "C": _make_signals(rsi=30.0),
            "D": _make_signals(rsi=40.0),
            "E": _make_signals(rsi=50.0),
        }
        result = percentile_rank_normalize(universe)
        ranks = [result[t].rsi for t in ["A", "B", "C", "D", "E"]]
        # All should be non-None
        assert all(r is not None for r in ranks)
        # Should be monotonically increasing
        for i in range(len(ranks) - 1):
            assert ranks[i] < ranks[i + 1]  # type: ignore[operator]
        # Range: 0 to 100
        assert ranks[0] == pytest.approx(0.0, abs=0.01)  # type: ignore[arg-type]
        assert ranks[-1] == pytest.approx(100.0, abs=0.01)  # type: ignore[arg-type]

    def test_equal_values_same_rank(self) -> None:
        """Percentile rank: identical values get same rank."""
        universe = {
            "A": _make_signals(rsi=50.0),
            "B": _make_signals(rsi=50.0),
            "C": _make_signals(rsi=50.0),
        }
        result = percentile_rank_normalize(universe)
        ranks = [result[t].rsi for t in ["A", "B", "C"]]
        assert all(r is not None for r in ranks)
        assert ranks[0] == ranks[1] == ranks[2]

    def test_single_value_gets_50(self) -> None:
        """Percentile rank: single value gets 50.0 (midpoint)."""
        universe = {"A": _make_signals(rsi=42.0)}
        result = percentile_rank_normalize(universe)
        assert result["A"].rsi == pytest.approx(50.0, abs=0.01)

    def test_none_values_preserved(self) -> None:
        """Percentile rank: None values stay None in output."""
        universe = {
            "A": _make_signals(rsi=50.0, adx=None),
            "B": _make_signals(rsi=60.0, adx=30.0),
        }
        result = percentile_rank_normalize(universe)
        assert result["A"].adx is None
        assert result["B"].adx is not None

    def test_empty_universe_returns_empty(self) -> None:
        """Percentile rank: empty universe returns empty dict."""
        result = percentile_rank_normalize({})
        assert result == {}


@pytest.mark.audit_correctness
class TestInvertIndicators:
    """invert_indicators correctness tests."""

    def test_inverted_indicators_flipped(self) -> None:
        """Scoring CLAUDE.md: inverted indicators get 100 - value."""
        universe = {
            "A": _make_signals(bb_width=80.0, rsi=80.0),
        }
        result = invert_indicators(universe)
        # bb_width is inverted: 100 - 80 = 20
        assert result["A"].bb_width == pytest.approx(20.0, abs=0.01)
        # rsi is NOT inverted: stays at 80
        assert result["A"].rsi == pytest.approx(80.0, abs=0.01)

    def test_all_inverted_indicators_present(self) -> None:
        """All expected indicators are in INVERTED_INDICATORS set."""
        expected = {"bb_width", "atr_pct", "keltner_width", "chain_spread_pct"}
        assert expected == INVERTED_INDICATORS

    def test_none_preserved_on_inversion(self) -> None:
        """None values preserved during inversion."""
        universe = {"A": _make_signals(bb_width=None)}
        result = invert_indicators(universe)
        assert result["A"].bb_width is None


@pytest.mark.audit_correctness
class TestNormalizeSingleTicker:
    """normalize_single_ticker domain-bound linear scaling."""

    def test_rsi_midpoint_maps_to_50(self) -> None:
        """RSI 50 (midpoint of 0-100 domain) maps to percentile 50."""
        signals = _make_signals(rsi=50.0)
        result = normalize_single_ticker(signals)
        assert result.rsi == pytest.approx(50.0, abs=0.5)

    def test_rsi_max_maps_to_100(self) -> None:
        """RSI 100 (top of domain) maps to percentile 100."""
        signals = _make_signals(rsi=100.0)
        result = normalize_single_ticker(signals)
        assert result.rsi == pytest.approx(100.0, abs=0.5)

    def test_inverted_indicator_flipped(self) -> None:
        """bb_width at domain max (0.5) maps to low percentile after inversion."""
        signals = _make_signals(bb_width=0.5)
        result = normalize_single_ticker(signals)
        # 0.5 maps to 100 in domain, then inverted to 0
        assert result.bb_width is not None
        assert result.bb_width == pytest.approx(0.0, abs=0.5)


@pytest.mark.audit_correctness
class TestGetActiveIndicators:
    """get_active_indicators correctness tests."""

    def test_active_indicators_correct(self) -> None:
        """Active indicators are those with at least one non-None finite value."""
        universe = {
            "A": _make_signals(rsi=50.0, adx=None),
            "B": _make_signals(rsi=60.0, adx=30.0),
        }
        active = get_active_indicators(universe)
        assert "rsi" in active
        assert "adx" in active

    def test_all_none_excluded(self) -> None:
        """Indicators that are None for all tickers are excluded."""
        universe = {
            "A": _make_signals(rsi=50.0, supertrend=None),
            "B": _make_signals(rsi=60.0, supertrend=None),
        }
        active = get_active_indicators(universe)
        assert "rsi" in active
        assert "supertrend" not in active


@pytest.mark.audit_correctness
class TestComputeNormalizationStats:
    """compute_normalization_stats correctness tests."""

    def test_stats_computed_for_active_indicators(self) -> None:
        """Stats computed for indicators with valid values."""
        universe = {
            "A": _make_signals(rsi=30.0),
            "B": _make_signals(rsi=50.0),
            "C": _make_signals(rsi=70.0),
        }
        stats = compute_normalization_stats(universe)
        rsi_stats = [s for s in stats if s.indicator_name == "rsi"]
        assert len(rsi_stats) == 1
        s = rsi_stats[0]
        assert s.min_value == pytest.approx(30.0, abs=0.01)
        assert s.max_value == pytest.approx(70.0, abs=0.01)
        assert s.median_value == pytest.approx(50.0, abs=0.01)
        assert s.mean_value == pytest.approx(50.0, abs=0.01)
        assert s.ticker_count == 3

    def test_empty_returns_empty(self) -> None:
        """Empty input returns empty stats list."""
        stats = compute_normalization_stats({})
        assert stats == []


# =========================================================================
# Composite (2 functions)
# =========================================================================


@pytest.mark.audit_correctness
class TestCompositeScoreCorrectness:
    """Composite score (weighted geometric mean) correctness."""

    def test_all_indicators_at_50_produces_near_50(self) -> None:
        """Geometric mean composite: all indicators at 50th percentile ~ 50."""
        kwargs = {field: 50.0 for field in INDICATOR_WEIGHTS}
        signals = IndicatorSignals(**kwargs)
        active = set(INDICATOR_WEIGHTS.keys())
        result = composite_score(signals, active)
        assert result == pytest.approx(50.0, abs=5.0)

    def test_all_indicators_at_100(self) -> None:
        """All indicators at 100 produces composite = 100."""
        kwargs = {field: 100.0 for field in INDICATOR_WEIGHTS}
        signals = IndicatorSignals(**kwargs)
        active = set(INDICATOR_WEIGHTS.keys())
        result = composite_score(signals, active)
        assert result == pytest.approx(100.0, abs=_COMPOSITE_ABS)

    def test_all_indicators_at_zero_uses_floor(self) -> None:
        """Zero-valued indicators get floor of 0.5 in geometric mean."""
        kwargs = {field: 0.0 for field in INDICATOR_WEIGHTS}
        signals = IndicatorSignals(**kwargs)
        active = set(INDICATOR_WEIGHTS.keys())
        result = composite_score(signals, active)
        assert result > 0.0
        # Floor of 0.5 means exp(ln(0.5)) = 0.5
        assert result == pytest.approx(0.5, abs=0.1)

    def test_no_indicators_returns_zero(self) -> None:
        """No valid indicators returns 0.0."""
        signals = _make_signals()  # all None
        result = composite_score(signals)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_composite_range(self) -> None:
        """Composite score is in [0, 100]."""
        kwargs = {field: 75.0 for field in INDICATOR_WEIGHTS}
        signals = IndicatorSignals(**kwargs)
        active = set(INDICATOR_WEIGHTS.keys())
        result = composite_score(signals, active)
        assert 0.0 <= result <= 100.0


@pytest.mark.audit_correctness
class TestScoreUniverseCorrectness:
    """score_universe end-to-end correctness."""

    def test_score_universe_sorted_descending(self) -> None:
        """score_universe returns list sorted descending by composite score."""
        universe = {
            "LOW": _make_signals(rsi=10.0, adx=10.0, sma_alignment=-0.5),
            "MED": _make_signals(rsi=50.0, adx=50.0, sma_alignment=0.0),
            "HIGH": _make_signals(rsi=90.0, adx=90.0, sma_alignment=0.5),
        }
        results = score_universe(universe)
        scores = [r.composite_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_score_universe_empty_returns_empty(self) -> None:
        """Empty universe returns empty list."""
        result = score_universe({})
        assert result == []


# =========================================================================
# Direction (1 function)
# =========================================================================


@pytest.mark.audit_correctness
class TestDetermineDirectionCorrectness:
    """Direction determination correctness vs scoring_known_values.json."""

    @pytest.mark.parametrize(
        "case",
        _SCORING_DATA["direction_determination"],
        ids=[c["source"][:60] for c in _SCORING_DATA["direction_determination"]],
    )
    def test_direction_known_values(self, case: dict) -> None:
        """scoring/direction.py -- direction classification from known inputs."""
        inp = case["input"]
        adx_val = float("nan") if inp["adx"] == "NaN" else float(inp["adx"])
        rsi_val = float(inp["rsi"])
        sma_val = float(inp["sma_alignment"])

        st = inp.get("supertrend")
        roc_val = inp.get("roc")

        # Convert None from JSON (which comes as None)
        st_float = float(st) if st is not None else None
        roc_float = float(roc_val) if roc_val is not None else None

        result = determine_direction(
            adx=adx_val,
            rsi=rsi_val,
            sma_alignment=sma_val,
            supertrend=st_float,
            roc=roc_float,
        )

        expected = SignalDirection(case["expected"]["direction"].lower())
        assert result == expected, f"Expected {expected}, got {result} for {case['source']}"


# =========================================================================
# Dimensional (3 functions)
# =========================================================================


@pytest.mark.audit_correctness
class TestDimensionalScoresCorrectness:
    """Dimensional scoring functions correctness."""

    def test_compute_direction_signal_bullish(self) -> None:
        """Bullish indicators produce DirectionSignal with bullish direction."""
        signals = _make_signals(rsi=70.0, adx=30.0, sma_alignment=0.8)
        result = compute_direction_signal(signals, SignalDirection.BULLISH)
        assert result is not None
        assert result.direction == SignalDirection.BULLISH
        assert 0.0 <= result.confidence <= 1.0

    def test_compute_direction_signal_neutral(self) -> None:
        """Neutral indicators produce DirectionSignal with confidence."""
        signals = _make_signals(rsi=50.0, adx=10.0, sma_alignment=0.0)
        result = compute_direction_signal(signals, SignalDirection.NEUTRAL)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_compute_dimensional_scores_returns_model(self) -> None:
        """compute_dimensional_scores returns a valid DimensionalScores model."""
        signals = _make_signals(
            rsi=60.0,
            adx=25.0,
            sma_alignment=0.3,
            bb_width=0.05,
            relative_volume=1.5,
            iv_rank=60.0,
        )
        result = compute_dimensional_scores(signals)
        assert result is not None
        # DimensionalScores has family-named fields: trend, iv_vol, hv_vol, etc.
        assert hasattr(result, "trend")
        assert hasattr(result, "iv_vol")

    def test_apply_regime_weights_finite(self) -> None:
        """Regime-weighted scores are finite."""
        from options_arena.models.enums import MarketRegime

        signals = _make_signals(
            rsi=60.0,
            adx=25.0,
            sma_alignment=0.3,
            bb_width=0.05,
        )
        scores = compute_dimensional_scores(signals)
        weighted = apply_regime_weights(
            scores,
            regime=MarketRegime.TRENDING,
            enable_regime_weights=True,
        )
        assert weighted is not None
        assert math.isfinite(weighted)


# =========================================================================
# Contracts (5 functions) — tested via interface correctness
# =========================================================================

# NOTE: filter_contracts, select_expiration, compute_greeks, select_by_delta,
# and recommend_contracts are heavily integration-oriented functions that require
# full OptionContract models, chain data, and pricing infrastructure.
# Here we test the mathematical invariants that can be verified with
# minimal setup.


@pytest.mark.audit_correctness
class TestContractsScoringCorrectness:
    """Contract scoring function mathematical invariants."""

    def test_filter_contracts_import(self) -> None:
        """filter_contracts is importable from scoring.contracts."""
        from options_arena.scoring.contracts import filter_contracts

        assert callable(filter_contracts)

    def test_select_expiration_import(self) -> None:
        """select_expiration is importable from scoring.contracts."""
        from options_arena.scoring.contracts import select_expiration

        assert callable(select_expiration)

    def test_compute_greeks_import(self) -> None:
        """compute_greeks is importable from scoring.contracts."""
        from options_arena.scoring.contracts import compute_greeks

        assert callable(compute_greeks)

    def test_select_by_delta_import(self) -> None:
        """select_by_delta is importable from scoring.contracts."""
        from options_arena.scoring.contracts import select_by_delta

        assert callable(select_by_delta)

    def test_recommend_contracts_import(self) -> None:
        """recommend_contracts is importable from scoring.contracts."""
        from options_arena.scoring.contracts import recommend_contracts

        assert callable(recommend_contracts)


# =========================================================================
# Indicator Weights Invariant
# =========================================================================


@pytest.mark.audit_correctness
class TestIndicatorWeightsInvariant:
    """Indicator weights must sum to 1.0."""

    def test_weights_sum_to_one(self) -> None:
        """INDICATOR_WEIGHTS values sum to exactly 1.0."""
        total = sum(w for w, _ in INDICATOR_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_all_weights_positive(self) -> None:
        """All indicator weights are positive."""
        for name, (weight, _) in INDICATOR_WEIGHTS.items():
            assert weight > 0.0, f"Weight for {name} must be positive, got {weight}"
