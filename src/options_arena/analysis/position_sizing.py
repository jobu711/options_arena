"""Volatility-regime-aware position sizing algorithm.

Maps annualized IV to allocation tiers with linear interpolation within tiers
and an optional correlation penalty. Returns a typed ``PositionSizeResult``
with allocation percentage, tier info, and rationale.

Tier mapping (defaults):
    Tier 1: IV < 15%     -> 25% allocation ("low")
    Tier 2: 15% <= IV < 30%  -> linear interp from 25% down to 17.5% ("moderate")
    Tier 3: 30% <= IV < 50%  -> linear interp from 17.5% down to 10% ("elevated")
    Tier 4: IV >= 50%    -> 5% hard cap ("extreme")

Linear interpolation within tiers: at the lower boundary of a tier, allocation
equals the previous tier's allocation. At the upper boundary, allocation equals
the tier's own allocation. This provides a smooth transition.

Correlation adjustment: when ``correlation_with_portfolio`` exceeds
``high_corr_threshold`` (default 0.70), the base allocation is multiplied by
``corr_penalty`` (default 0.50). Otherwise the adjustment factor is 1.0.

NaN/Inf handling: non-finite IV values default to Tier 4 (5% allocation) as the
safest conservative default.

Architecture rules:
- Pure computation — no I/O, no API calls, no database access.
- Imports only from ``models/`` and stdlib.
"""

from __future__ import annotations

import math

from options_arena.models.analysis import PositionSizeResult
from options_arena.models.config import PositionSizingConfig


def compute_position_size(
    annualized_iv: float,
    correlation_with_portfolio: float | None = None,
    config: PositionSizingConfig | None = None,
) -> PositionSizeResult:
    """Compute volatility-regime-aware position size.

    Parameters
    ----------
    annualized_iv
        Annualized implied volatility as a decimal fraction (e.g. 0.25 = 25%).
        Non-finite values (NaN, Inf, -Inf) and negative values default to Tier 4.
    correlation_with_portfolio
        Optional correlation of this position with the existing portfolio.
        When provided and exceeding ``config.high_corr_threshold``, the base
        allocation is reduced by ``config.corr_penalty``.
    config
        Position sizing configuration. Uses defaults if ``None``.

    Returns
    -------
    PositionSizeResult
        Frozen model with tier info, allocation, adjustment, and rationale.
    """
    if config is None:
        config = PositionSizingConfig()

    # NaN/Inf/negative IV -> Tier 4 (safest default)
    if not math.isfinite(annualized_iv) or annualized_iv < 0.0:
        tier = 4
        label = "extreme"
        base_alloc = config.tier4_alloc
        rationale = (
            f"IV is non-finite or negative ({annualized_iv}); "
            f"defaulting to Tier 4 extreme (safest, {config.tier4_alloc:.1%} allocation)."
        )
    elif annualized_iv < config.tier1_iv_max:
        # Tier 1: low volatility — full allocation
        tier = 1
        label = "low"
        base_alloc = config.tier1_alloc
        rationale = (
            f"IV {annualized_iv:.1%} < {config.tier1_iv_max:.0%} threshold; "
            f"Tier 1 low vol regime -> {config.tier1_alloc:.1%} allocation."
        )
    elif annualized_iv < config.tier2_iv_max:
        # Tier 2: moderate volatility — linear interpolation from tier1_alloc to tier2_alloc
        tier = 2
        label = "moderate"
        iv_range = config.tier2_iv_max - config.tier1_iv_max
        fraction = (annualized_iv - config.tier1_iv_max) / iv_range if iv_range > 0.0 else 1.0
        base_alloc = config.tier1_alloc + fraction * (config.tier2_alloc - config.tier1_alloc)
        rationale = (
            f"IV {annualized_iv:.1%} in [{config.tier1_iv_max:.0%}, {config.tier2_iv_max:.0%}); "
            f"Tier 2 moderate vol regime -> {base_alloc:.2%} allocation "
            f"(linear interp between {config.tier1_alloc:.1%} and {config.tier2_alloc:.1%})."
        )
    elif annualized_iv < config.tier3_iv_max:
        # Tier 3: elevated volatility — linear interpolation from tier2_alloc to tier3_alloc
        tier = 3
        label = "elevated"
        iv_range = config.tier3_iv_max - config.tier2_iv_max
        fraction = (annualized_iv - config.tier2_iv_max) / iv_range if iv_range > 0.0 else 1.0
        base_alloc = config.tier2_alloc + fraction * (config.tier3_alloc - config.tier2_alloc)
        rationale = (
            f"IV {annualized_iv:.1%} in [{config.tier2_iv_max:.0%}, {config.tier3_iv_max:.0%}); "
            f"Tier 3 elevated vol regime -> {base_alloc:.2%} allocation "
            f"(linear interp between {config.tier2_alloc:.1%} and {config.tier3_alloc:.1%})."
        )
    else:
        # Tier 4: extreme volatility — hard cap
        tier = 4
        label = "extreme"
        base_alloc = config.tier4_alloc
        rationale = (
            f"IV {annualized_iv:.1%} >= {config.tier3_iv_max:.0%} threshold; "
            f"Tier 4 extreme vol regime -> {config.tier4_alloc:.1%} hard cap."
        )

    # Correlation adjustment
    corr_adjustment = 1.0
    if (
        correlation_with_portfolio is not None
        and math.isfinite(correlation_with_portfolio)
        and correlation_with_portfolio > config.high_corr_threshold
    ):
        corr_adjustment = config.corr_penalty
        rationale += (
            f" Correlation {correlation_with_portfolio:.2f} > {config.high_corr_threshold:.2f} "
            f"threshold; applying {config.corr_penalty:.0%} penalty."
        )

    final_alloc = base_alloc * corr_adjustment

    return PositionSizeResult(
        vol_regime_tier=tier,
        vol_regime_label=label,
        annualized_iv=(
            annualized_iv if math.isfinite(annualized_iv) and annualized_iv >= 0.0 else 0.0
        ),
        base_allocation_pct=base_alloc,
        correlation_adjustment=corr_adjustment,
        final_allocation_pct=final_alloc,
        rationale=rationale,
    )
