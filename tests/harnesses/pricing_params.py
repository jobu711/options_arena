"""Parameter grid generators for BSM/BAW pricing stress tests.

Provides ``PricingParams`` dataclass and two grid generators:
    - ``generate_property_grid()`` — ~640 combos for invariant testing (CI-fast).
    - ``generate_stress_grid()`` — ~2K combos for brute-force numerical stability.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from options_arena.models.enums import OptionType


@dataclass(frozen=True)
class PricingParams:
    """A single set of pricing parameters for BSM/BAW evaluation."""

    S: float
    K: float
    T: float
    r: float
    q: float
    sigma: float
    option_type: OptionType

    @property
    def moneyness(self) -> float:
        """S/K ratio — 1.0 is ATM, >1 ITM call / OTM put."""
        return self.S / self.K


def generate_property_grid() -> list[PricingParams]:
    """Generate ~640 parameter combos for financial invariant testing.

    Covers ATM, ITM, OTM, varied sigma, varied T, with and without dividends.
    Designed to complete in <30s for CI.
    """
    spot = 100.0
    # S/K ratios: deep OTM, OTM, ATM, ITM, deep ITM
    moneyness_ratios = [0.70, 0.90, 1.00, 1.10, 1.30]
    sigmas = [0.10, 0.30, 0.60, 1.50]
    times = [0.01, 0.08, 0.25, 1.0]  # ~4d, ~1mo, ~3mo, 1yr
    rates = [0.02, 0.05]
    dividends = [0.0, 0.02]
    option_types = [OptionType.CALL, OptionType.PUT]

    grid: list[PricingParams] = []
    for moneyness, sigma, T, r, q, opt_type in itertools.product(
        moneyness_ratios, sigmas, times, rates, dividends, option_types,
    ):
        K = spot / moneyness  # S/K = moneyness → K = S/moneyness
        grid.append(PricingParams(S=spot, K=K, T=T, r=r, q=q, sigma=sigma, option_type=opt_type))

    return grid


def generate_stress_grid() -> list[PricingParams]:
    """Generate ~2K parameter combos for brute-force numerical stability.

    Includes extreme S/K ratios, solver-boundary sigma, near-zero T,
    and varied rates/dividends. Intended for ``@pytest.mark.slow``.
    """
    spot = 100.0
    # 9 S/K ratios: very deep OTM to very deep ITM
    moneyness_ratios = [0.20, 0.50, 0.70, 0.90, 1.00, 1.10, 1.30, 1.50, 2.00]
    # 8 sigma values: near-zero to extreme
    sigmas = [1e-5, 0.01, 0.10, 0.30, 0.60, 1.50, 3.0, 4.99]
    # 7 T values: near-expiry to long-dated
    times = [1e-4, 0.003, 0.01, 0.08, 0.25, 1.0, 3.0]
    option_types = [OptionType.CALL, OptionType.PUT]

    # Full product would be 9*8*7*4*3*2 = 12096, sample down to ~2K
    # Use every combo but skip some rate/dividend combos
    grid: list[PricingParams] = []
    for moneyness, sigma, T, opt_type in itertools.product(
        moneyness_ratios, sigmas, times, option_types,
    ):
        # Pick a representative subset of (r, q) pairs
        rq_pairs = [(0.02, 0.0), (0.05, 0.0), (0.05, 0.02)]
        for r, q in rq_pairs:
            K = spot / moneyness
            grid.append(
                PricingParams(S=spot, K=K, T=T, r=r, q=q, sigma=sigma, option_type=opt_type)
            )

    return grid
