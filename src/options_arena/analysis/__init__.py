"""Options Arena — Analysis & Scoring.

Re-exports public API from analysis submodules.
"""

from options_arena.analysis.correlation import compute_correlation_matrix
from options_arena.analysis.performance import compute_risk_adjusted_metrics
from options_arena.analysis.position_sizing import compute_position_size
from options_arena.analysis.valuation import (
    FDData,
    compute_composite_valuation,
    compute_ev_ebitda_relative,
    compute_owner_earnings_dcf,
    compute_residual_income,
    compute_three_stage_dcf,
)

__all__ = [
    "FDData",
    "compute_composite_valuation",
    "compute_correlation_matrix",
    "compute_ev_ebitda_relative",
    "compute_owner_earnings_dcf",
    "compute_position_size",
    "compute_residual_income",
    "compute_risk_adjusted_metrics",
    "compute_three_stage_dcf",
]
