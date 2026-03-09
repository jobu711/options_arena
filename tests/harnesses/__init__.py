"""Reusable test harnesses for pricing and contract selection stress tests.

Modules:
    pricing_params  — Parameter grid generators for BSM/BAW invariant testing.
    chain_factory   — Synthetic option chain builder with configurable edge cases.
"""

from tests.harnesses.chain_factory import ChainSpec, build_chain
from tests.harnesses.pricing_params import (
    PricingParams,
    generate_property_grid,
    generate_stress_grid,
)

__all__ = [
    "ChainSpec",
    "PricingParams",
    "build_chain",
    "generate_property_grid",
    "generate_stress_grid",
]
