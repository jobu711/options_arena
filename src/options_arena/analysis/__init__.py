"""Options Arena — Analysis & Scoring.

Re-exports public API from analysis submodules.
"""

from options_arena.analysis.performance import compute_risk_adjusted_metrics

__all__ = ["compute_risk_adjusted_metrics"]
