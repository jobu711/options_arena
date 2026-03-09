"""Edge case tests for contract selection using synthetic chains.

Tests cover:
    1. All zero-bid contracts
    2. All bid>ask stale quotes (Bug Fix 1 regression)
    3. NaN delta injected (Bug Fix 2 regression)
    4. Extremely wide spreads
    5. OI = 0 on all contracts
    6. Single valid contract
    7. All deep ITM (delta > 0.80)
    8. Mixed: some NaN delta + some valid
"""

import math
from decimal import Decimal

import pytest

from options_arena.models.config import PricingConfig
from options_arena.scoring.contracts import (
    _compute_liquidity_score,
    filter_contracts,
    select_by_delta,
)
from tests.harnesses.chain_factory import ChainSpec, build_chain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_config() -> PricingConfig:
    """PricingConfig with production defaults."""
    return PricingConfig()


# ---------------------------------------------------------------------------
# 1. All zero-bid contracts
# ---------------------------------------------------------------------------


class TestZeroBidContracts:
    """Contracts with bid=0 but ask>0 get zero-bid exemption in filter_contracts,
    but should have liquidity_score = 0 (mid=0 -> spread_component=0)."""

    def test_zero_bid_liquidity_score(self) -> None:
        spec = ChainSpec(
            num_strikes=5,
            zero_bid_indices=[0, 1, 2, 3, 4],
        )
        chain = build_chain(spec)
        cfg = _default_config()
        for contract in chain:
            score = _compute_liquidity_score(contract, cfg.max_spread_pct)
            # Mid is (0 + ask)/2 > 0, spread/mid is large, so spread_component ≈ 0
            # OI component is positive. Score should be small but valid.
            assert 0.0 <= score <= 1.0, f"Score out of [0,1]: {score}"

    def test_both_bid_and_ask_zero_filtered_out(self) -> None:
        """Contracts with bid=0 AND ask=0 are filtered as truly dead."""
        spec = ChainSpec(num_strikes=3, base_bid=0.0, base_ask=0.0)
        # build_chain doesn't set ask=0 by default; build manually
        from options_arena.models.enums import SignalDirection

        chain = build_chain(spec)
        # Override: set both bid and ask to 0 by rebuilding
        dead_chain = [
            c.model_copy(update={"bid": Decimal("0"), "ask": Decimal("0"), "last": Decimal("0")})
            for c in chain
        ]
        filtered = filter_contracts(dead_chain, SignalDirection.BULLISH, _default_config())
        assert len(filtered) == 0, "Dead contracts (bid=0, ask=0) should all be filtered"


# ---------------------------------------------------------------------------
# 2. Stale bid>ask quotes (Bug Fix 1 regression test)
# ---------------------------------------------------------------------------


class TestStaleBidGtAsk:
    """When bid > ask (stale quote), spread is negative, spread_pct < 0,
    and spread_component would be > 1.0 without the upper-bound clamp."""

    def test_spread_component_clamped_to_one(self) -> None:
        """Verify _compute_liquidity_score returns <= 1.0 for stale quotes."""
        spec = ChainSpec(
            num_strikes=5,
            stale_bid_gt_ask_indices=[0, 1, 2, 3, 4],
        )
        chain = build_chain(spec)
        cfg = _default_config()
        for contract in chain:
            score = _compute_liquidity_score(contract, cfg.max_spread_pct)
            assert 0.0 <= score <= 1.0, (
                f"Liquidity score {score} out of [0,1] for bid={contract.bid}, ask={contract.ask}"
            )

    def test_stale_quote_penalized(self) -> None:
        """A stale-quote contract (bid > ask) gets spread_component = 0.0,
        penalizing stale data. Score comes only from the OI component."""
        spec_stale = ChainSpec(num_strikes=1, stale_bid_gt_ask_indices=[0])
        stale = build_chain(spec_stale)[0]
        cfg = _default_config()
        score = _compute_liquidity_score(stale, cfg.max_spread_pct)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0,1] for stale quote"
        # spread_component is 0.0 (penalized), so total = 0.0 * 0.7 + oi * 0.3
        # Score should be small — only the OI component contributes
        assert score <= 0.3, f"Stale quote score {score} too high — spread_component should be 0.0"


# ---------------------------------------------------------------------------
# 3. NaN delta (Bug Fix 2 regression test)
# ---------------------------------------------------------------------------


class TestNaNDelta:
    """NaN delta from pricing edge cases must be dropped before sorting."""

    def test_all_nan_delta_returns_none(self) -> None:
        """If all contracts have NaN delta, select_by_delta returns None."""
        spec = ChainSpec(
            num_strikes=5,
            nan_delta_indices=[0, 1, 2, 3, 4],
        )
        chain = build_chain(spec)
        result = select_by_delta(chain, _default_config())
        assert result is None, "Expected None when all deltas are NaN"

    def test_nan_delta_skipped_in_sort(self) -> None:
        """Contracts with NaN delta are excluded; valid contracts still selected."""
        spec = ChainSpec(
            num_strikes=5,
            nan_delta_indices=[0, 2, 4],  # NaN on indices 0, 2, 4
            base_delta=0.35,  # Valid delta on indices 1, 3
        )
        chain = build_chain(spec)
        result = select_by_delta(chain, _default_config())
        assert result is not None, "Valid contracts should be selectable"
        assert result.greeks is not None
        assert math.isfinite(result.greeks.delta), "Selected contract has NaN delta!"


# ---------------------------------------------------------------------------
# 4. Extremely wide spreads
# ---------------------------------------------------------------------------


class TestWideSpread:
    """Contracts with extremely wide bid-ask spreads (>max_spread_pct)
    should be filtered out by filter_contracts."""

    def test_all_wide_spread_filtered(self) -> None:
        from options_arena.models.enums import SignalDirection

        spec = ChainSpec(
            num_strikes=5,
            wide_spread_indices=[0, 1, 2, 3, 4],
        )
        chain = build_chain(spec)
        cfg = _default_config()
        filtered = filter_contracts(chain, SignalDirection.BULLISH, cfg)
        assert len(filtered) == 0, "All wide-spread contracts should be filtered"


# ---------------------------------------------------------------------------
# 5. OI = 0 on all contracts
# ---------------------------------------------------------------------------


class TestZeroOI:
    """Contracts with open_interest < min_oi (default 100) are filtered."""

    def test_all_zero_oi_filtered(self) -> None:
        from options_arena.models.enums import SignalDirection

        spec = ChainSpec(
            num_strikes=5,
            zero_oi_indices=[0, 1, 2, 3, 4],
        )
        chain = build_chain(spec)
        cfg = _default_config()
        filtered = filter_contracts(chain, SignalDirection.BULLISH, cfg)
        assert len(filtered) == 0, "All zero-OI contracts should be filtered"


# ---------------------------------------------------------------------------
# 6. Single valid contract
# ---------------------------------------------------------------------------


class TestSingleValidContract:
    """A single valid contract should be returned by select_by_delta."""

    def test_single_contract_returned(self) -> None:
        spec = ChainSpec(
            num_strikes=1,
            base_delta=0.35,  # Within primary range [0.20, 0.50]
        )
        chain = build_chain(spec)
        result = select_by_delta(chain, _default_config())
        assert result is not None, "Single valid contract should be selected"
        assert result.ticker == "TEST"


# ---------------------------------------------------------------------------
# 7. All deep ITM (delta > 0.80)
# ---------------------------------------------------------------------------


class TestAllDeepITM:
    """When all contracts have delta outside primary+fallback range,
    select_by_delta returns None."""

    def test_all_deep_itm_returns_none(self) -> None:
        spec = ChainSpec(
            num_strikes=5,
            base_delta=0.95,  # Outside fallback max (0.80)
        )
        chain = build_chain(spec)
        result = select_by_delta(chain, _default_config())
        assert result is None, "All deep ITM contracts should yield None"


# ---------------------------------------------------------------------------
# 8. Mixed: some NaN delta + some valid
# ---------------------------------------------------------------------------


class TestMixedNaNAndValid:
    """Mix of NaN and valid deltas — valid contracts sorted correctly."""

    def test_mixed_selects_best_valid(self) -> None:
        """With 3 NaN and 2 valid, the valid one closest to target is picked."""
        spec = ChainSpec(
            num_strikes=5,
            nan_delta_indices=[0, 1, 2],
            base_delta=0.35,
        )
        chain = build_chain(spec)
        result = select_by_delta(chain, _default_config())
        assert result is not None, "Should select from valid contracts"
        assert result.greeks is not None
        assert math.isfinite(result.greeks.delta)
        # Should be one of contracts at index 3 or 4
        valid_strikes = {chain[3].strike, chain[4].strike}
        assert result.strike in valid_strikes, f"Selected unexpected strike {result.strike}"

    def test_nan_delta_not_in_candidates(self) -> None:
        """Ensure NaN-delta contracts are never in the candidate list."""
        spec = ChainSpec(
            num_strikes=10,
            nan_delta_indices=[0, 3, 5, 7, 9],
            base_delta=0.35,
        )
        chain = build_chain(spec)
        # select_by_delta should work without error (no NaN in sort key)
        result = select_by_delta(chain, _default_config())
        if result is not None:
            assert result.greeks is not None
            assert math.isfinite(result.greeks.delta)


# ---------------------------------------------------------------------------
# Liquidity score bounds
# ---------------------------------------------------------------------------


class TestLiquidityScoreBounds:
    """_compute_liquidity_score always returns a value in [0.0, 1.0]."""

    @pytest.mark.parametrize(
        "max_spread_pct",
        [0.0, -0.5, float("nan"), float("inf")],
        ids=["zero", "negative", "nan", "inf"],
    )
    def test_degenerate_max_spread(self, max_spread_pct: float) -> None:
        """Score must be in [0,1] even for degenerate max_spread_pct values."""
        spec = ChainSpec(num_strikes=1)
        contract = build_chain(spec)[0]
        score = _compute_liquidity_score(contract, max_spread_pct)
        assert 0.0 <= score <= 1.0, (
            f"Score {score} out of [0,1] for max_spread_pct={max_spread_pct}"
        )

    def test_normal_contract_score_in_bounds(self) -> None:
        """Normal contract with tight spread has score in [0,1]."""
        spec = ChainSpec(num_strikes=1, base_bid=5.0, base_ask=5.10)
        contract = build_chain(spec)[0]
        score = _compute_liquidity_score(contract, 0.10)
        assert 0.0 <= score <= 1.0
        assert score > 0.5, "Tight spread should give high liquidity score"
