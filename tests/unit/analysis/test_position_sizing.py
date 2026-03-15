"""Tests for volatility-regime-aware position sizing algorithm.

Covers all 4 tiers, linear interpolation within tiers, correlation penalty,
NaN/Inf edge cases, custom config, and model validation.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from options_arena.analysis.position_sizing import compute_position_size
from options_arena.models.analysis import PositionSizeResult
from options_arena.models.config import PositionSizingConfig


class TestTier1LowVolatility:
    """Tier 1: IV < 15% -> 25% allocation, label='low'."""

    def test_tier1_low_iv_25pct_allocation(self) -> None:
        """IV=10% (< 15%) -> Tier 1, 25% allocation."""
        result = compute_position_size(0.10)
        assert result.vol_regime_tier == 1
        assert result.vol_regime_label == "low"
        assert result.base_allocation_pct == pytest.approx(0.25)
        assert result.final_allocation_pct == pytest.approx(0.25)
        assert result.correlation_adjustment == pytest.approx(1.0)

    def test_tier1_zero_iv(self) -> None:
        """IV=0.0 is valid Tier 1."""
        result = compute_position_size(0.0)
        assert result.vol_regime_tier == 1
        assert result.vol_regime_label == "low"
        assert result.base_allocation_pct == pytest.approx(0.25)


class TestTier2ModerateVolatility:
    """Tier 2: 15% <= IV < 30% -> linear interp from 25% to 17.5%."""

    def test_tier2_boundary_iv_15pct(self) -> None:
        """IV=15% (exactly at tier2 start) -> Tier 2, allocation at top of range (25%)."""
        result = compute_position_size(0.15)
        assert result.vol_regime_tier == 2
        assert result.vol_regime_label == "moderate"
        # At the lower boundary, interpolation yields tier1_alloc (25%)
        assert result.base_allocation_pct == pytest.approx(0.25)

    def test_tier2_midpoint_linear_interpolation(self) -> None:
        """IV=22.5% (midpoint of 15-30%) -> linear interp -> ~21.25% allocation."""
        result = compute_position_size(0.225)
        assert result.vol_regime_tier == 2
        assert result.vol_regime_label == "moderate"
        # Midpoint: 0.25 + 0.5 * (0.175 - 0.25) = 0.25 - 0.0375 = 0.2125
        assert result.base_allocation_pct == pytest.approx(0.2125)

    def test_tier2_at_upper_boundary(self) -> None:
        """IV approaching 30% -> allocation approaches 17.5%."""
        result = compute_position_size(0.2999)
        assert result.vol_regime_tier == 2
        assert result.vol_regime_label == "moderate"
        # Just below 30% -> close to tier2_alloc (17.5%)
        assert result.base_allocation_pct == pytest.approx(0.175, abs=0.001)


class TestTier3ElevatedVolatility:
    """Tier 3: 30% <= IV < 50% -> linear interp from 17.5% to 10%."""

    def test_tier3_linear_interpolation(self) -> None:
        """IV=40% (midpoint of 30-50%) -> linear interp between 17.5% and 10%."""
        result = compute_position_size(0.40)
        assert result.vol_regime_tier == 3
        assert result.vol_regime_label == "elevated"
        # 0.175 + 0.5 * (0.10 - 0.175) = 0.175 - 0.0375 = 0.1375
        assert result.base_allocation_pct == pytest.approx(0.1375)

    def test_tier3_at_lower_boundary(self) -> None:
        """IV=30% (exactly at tier3 start) -> allocation at top of range (17.5%)."""
        result = compute_position_size(0.30)
        assert result.vol_regime_tier == 3
        assert result.vol_regime_label == "elevated"
        assert result.base_allocation_pct == pytest.approx(0.175)


class TestTier4ExtremeVolatility:
    """Tier 4: IV >= 50% -> 5% hard cap, label='extreme'."""

    def test_tier4_extreme_iv_hard_cap(self) -> None:
        """IV=60% (>= 50%) -> Tier 4, 5% hard cap."""
        result = compute_position_size(0.60)
        assert result.vol_regime_tier == 4
        assert result.vol_regime_label == "extreme"
        assert result.base_allocation_pct == pytest.approx(0.05)
        assert result.final_allocation_pct == pytest.approx(0.05)

    def test_tier4_at_boundary(self) -> None:
        """IV=50% (exactly at threshold) -> Tier 4."""
        result = compute_position_size(0.50)
        assert result.vol_regime_tier == 4
        assert result.vol_regime_label == "extreme"
        assert result.base_allocation_pct == pytest.approx(0.05)

    def test_tier4_very_high_iv(self) -> None:
        """IV=200% -> still Tier 4, 5%."""
        result = compute_position_size(2.0)
        assert result.vol_regime_tier == 4
        assert result.final_allocation_pct == pytest.approx(0.05)


class TestCorrelationAdjustment:
    """Correlation penalty when above threshold."""

    def test_correlation_above_threshold_applies_penalty(self) -> None:
        """correlation=0.80 > 0.70 threshold -> base * 0.50 penalty."""
        result = compute_position_size(0.10, correlation_with_portfolio=0.80)
        assert result.vol_regime_tier == 1
        assert result.base_allocation_pct == pytest.approx(0.25)
        assert result.correlation_adjustment == pytest.approx(0.50)
        assert result.final_allocation_pct == pytest.approx(0.125)

    def test_correlation_none_no_adjustment(self) -> None:
        """correlation=None -> adjustment=1.0, no penalty."""
        result = compute_position_size(0.10, correlation_with_portfolio=None)
        assert result.correlation_adjustment == pytest.approx(1.0)
        assert result.final_allocation_pct == pytest.approx(result.base_allocation_pct)

    def test_correlation_below_threshold_no_adjustment(self) -> None:
        """correlation=0.50 < 0.70 -> adjustment=1.0, no penalty."""
        result = compute_position_size(0.10, correlation_with_portfolio=0.50)
        assert result.correlation_adjustment == pytest.approx(1.0)
        assert result.final_allocation_pct == pytest.approx(result.base_allocation_pct)

    def test_correlation_exactly_at_threshold_no_penalty(self) -> None:
        """correlation=0.70 == threshold -> strictly greater required, no penalty."""
        result = compute_position_size(0.10, correlation_with_portfolio=0.70)
        assert result.correlation_adjustment == pytest.approx(1.0)


class TestNaNInfHandling:
    """Non-finite IV defaults to Tier 4 (safest default)."""

    def test_nan_iv_defaults_to_tier4(self) -> None:
        """float('nan') IV -> Tier 4 safest default (5%)."""
        result = compute_position_size(float("nan"))
        assert result.vol_regime_tier == 4
        assert result.vol_regime_label == "extreme"
        assert result.final_allocation_pct == pytest.approx(0.05)
        # annualized_iv stored as 0.0 since NaN is non-finite
        assert result.annualized_iv == pytest.approx(0.0)

    def test_inf_iv_defaults_to_tier4(self) -> None:
        """float('inf') IV -> Tier 4 safest default (5%)."""
        result = compute_position_size(float("inf"))
        assert result.vol_regime_tier == 4
        assert result.vol_regime_label == "extreme"
        assert result.final_allocation_pct == pytest.approx(0.05)

    def test_negative_inf_iv_defaults_to_tier4(self) -> None:
        """float('-inf') IV -> Tier 4 safest default."""
        result = compute_position_size(float("-inf"))
        assert result.vol_regime_tier == 4

    def test_negative_iv_defaults_to_tier4(self) -> None:
        """Negative IV (-0.10) -> Tier 4 safest default."""
        result = compute_position_size(-0.10)
        assert result.vol_regime_tier == 4
        assert result.vol_regime_label == "extreme"


class TestCustomConfig:
    """Non-default PositionSizingConfig values change tier boundaries and allocations."""

    def test_custom_config_thresholds(self) -> None:
        """Custom config with wider tiers and different allocations."""
        config = PositionSizingConfig(
            tier1_iv_max=0.20,
            tier1_alloc=0.30,
            tier2_iv_max=0.40,
            tier2_alloc=0.20,
            tier3_iv_max=0.60,
            tier3_alloc=0.10,
            tier4_alloc=0.03,
            high_corr_threshold=0.80,
            corr_penalty=0.40,
        )
        # IV=10% should be Tier 1 with 30% allocation
        result = compute_position_size(0.10, config=config)
        assert result.vol_regime_tier == 1
        assert result.base_allocation_pct == pytest.approx(0.30)

        # IV=30% should be Tier 2 (midpoint of 20-40%)
        result2 = compute_position_size(0.30, config=config)
        assert result2.vol_regime_tier == 2
        # Midpoint: 0.30 + 0.5 * (0.20 - 0.30) = 0.25
        assert result2.base_allocation_pct == pytest.approx(0.25)

        # IV=70% should be Tier 4
        result4 = compute_position_size(0.70, config=config)
        assert result4.vol_regime_tier == 4
        assert result4.base_allocation_pct == pytest.approx(0.03)

        # Correlation=0.85 > 0.80 custom threshold -> 40% penalty
        result_corr = compute_position_size(0.10, correlation_with_portfolio=0.85, config=config)
        assert result_corr.correlation_adjustment == pytest.approx(0.40)
        assert result_corr.final_allocation_pct == pytest.approx(0.30 * 0.40)


class TestModelValidation:
    """PositionSizeResult model frozen-ness and validators."""

    def test_model_frozen_and_validators_pass(self) -> None:
        """PositionSizeResult is frozen, validators accept valid data."""
        result = PositionSizeResult(
            vol_regime_tier=1,
            vol_regime_label="low",
            annualized_iv=0.10,
            base_allocation_pct=0.25,
            correlation_adjustment=1.0,
            final_allocation_pct=0.25,
            rationale="Test rationale.",
        )
        assert result.vol_regime_tier == 1
        assert result.final_allocation_pct == pytest.approx(0.25)

        # Frozen — cannot reassign
        with pytest.raises(ValidationError):
            result.vol_regime_tier = 2  # type: ignore[misc]

    def test_model_rejects_invalid_tier(self) -> None:
        """PositionSizeResult rejects tier outside [1, 4]."""
        with pytest.raises(ValidationError, match="vol_regime_tier"):
            PositionSizeResult(
                vol_regime_tier=5,
                vol_regime_label="low",
                annualized_iv=0.10,
                base_allocation_pct=0.25,
                correlation_adjustment=1.0,
                final_allocation_pct=0.25,
                rationale="Bad tier.",
            )

    def test_model_rejects_invalid_label(self) -> None:
        """PositionSizeResult rejects unknown vol_regime_label."""
        with pytest.raises(ValidationError, match="vol_regime_label"):
            PositionSizeResult(
                vol_regime_tier=1,
                vol_regime_label="unknown",
                annualized_iv=0.10,
                base_allocation_pct=0.25,
                correlation_adjustment=1.0,
                final_allocation_pct=0.25,
                rationale="Bad label.",
            )

    def test_model_rejects_nan_allocation(self) -> None:
        """PositionSizeResult rejects NaN in float fields."""
        with pytest.raises(ValidationError):
            PositionSizeResult(
                vol_regime_tier=1,
                vol_regime_label="low",
                annualized_iv=0.10,
                base_allocation_pct=float("nan"),
                correlation_adjustment=1.0,
                final_allocation_pct=float("nan"),
                rationale="NaN test.",
            )

    def test_result_has_rationale(self) -> None:
        """compute_position_size always produces a non-empty rationale."""
        result = compute_position_size(0.10)
        assert len(result.rationale) > 0

    def test_result_is_position_size_result(self) -> None:
        """Return type is PositionSizeResult."""
        result = compute_position_size(0.25)
        assert isinstance(result, PositionSizeResult)


class TestConfigValidation:
    """PositionSizingConfig validators."""

    def test_default_config_is_valid(self) -> None:
        """Default PositionSizingConfig() passes all validators."""
        config = PositionSizingConfig()
        assert math.isfinite(config.tier1_iv_max)
        assert math.isfinite(config.corr_penalty)

    def test_config_rejects_nan(self) -> None:
        """NaN values rejected by model_validator."""
        with pytest.raises(ValidationError):
            PositionSizingConfig(tier1_iv_max=float("nan"))

    def test_config_rejects_inf(self) -> None:
        """Inf values rejected by model_validator."""
        with pytest.raises(ValidationError):
            PositionSizingConfig(corr_penalty=float("inf"))


class TestZeroWidthTiers:
    """Edge case: tier boundaries equal (zero-width tier)."""

    def test_zero_width_tier2_no_division_by_zero(self) -> None:
        """When tier1_iv_max == tier2_iv_max, no division by zero occurs."""
        config = PositionSizingConfig(
            tier1_iv_max=0.20,
            tier2_iv_max=0.20,
            tier3_iv_max=0.50,
        )
        # IV at the boundary goes to tier 3 (since it's >= tier2_iv_max)
        result = compute_position_size(0.20, config=config)
        assert result.vol_regime_tier == 3

    def test_zero_width_tier3_no_division_by_zero(self) -> None:
        """When tier2_iv_max == tier3_iv_max, no division by zero occurs."""
        config = PositionSizingConfig(
            tier2_iv_max=0.30,
            tier3_iv_max=0.30,
        )
        # IV at the boundary goes to tier 4 (since it's >= tier3_iv_max)
        result = compute_position_size(0.30, config=config)
        assert result.vol_regime_tier == 4
