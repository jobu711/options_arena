"""Options Arena — Analysis & Scoring.

Re-exports public API from analysis submodules.
"""

from options_arena.analysis.correlation import compute_correlation_matrix
from options_arena.analysis.performance import compute_risk_adjusted_metrics
from options_arena.analysis.position_sizing import compute_position_size
from options_arena.analysis.valuation import compute_composite_valuation

__all__ = [
    "compute_composite_valuation",
    "compute_correlation_matrix",
    "compute_position_size",
    "compute_risk_adjusted_metrics",
]
