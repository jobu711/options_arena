"""Options Arena — Scoring engine and signal aggregation.

Modules:
    normalization -- Percentile-rank normalization with tie handling and inversion.
    composite     -- Weighted geometric mean composite scoring.
    direction     -- BULLISH / BEARISH / NEUTRAL signal classification.
    contracts     -- Contract filtering, Greeks dispatch, delta targeting.
"""

from options_arena.scoring.composite import (
    INDICATOR_WEIGHTS,
    composite_score,
    score_universe,
)
from options_arena.scoring.contracts import (
    compute_greeks,
    filter_contracts,
    recommend_contracts,
    select_by_delta,
    select_expiration,
)
from options_arena.scoring.dimensional import (
    DEFAULT_FAMILY_WEIGHTS,
    FAMILY_INDICATOR_MAP,
    REGIME_WEIGHT_PROFILES,
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
    percentile_rank_normalize,
)

__all__: list[str] = [
    # normalization
    "percentile_rank_normalize",
    "invert_indicators",
    "get_active_indicators",
    "compute_normalization_stats",
    "INVERTED_INDICATORS",
    # composite
    "composite_score",
    "score_universe",
    "INDICATOR_WEIGHTS",
    # dimensional
    "compute_dimensional_scores",
    "compute_direction_signal",
    "apply_regime_weights",
    "FAMILY_INDICATOR_MAP",
    "DEFAULT_FAMILY_WEIGHTS",
    "REGIME_WEIGHT_PROFILES",
    # direction
    "determine_direction",
    # contracts
    "filter_contracts",
    "select_expiration",
    "compute_greeks",
    "select_by_delta",
    "recommend_contracts",
]
