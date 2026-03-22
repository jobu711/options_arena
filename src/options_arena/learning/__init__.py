"""Options Arena — Self-Improvement Learning Module.

Re-exports the public API for the learning package: weight tuning algorithms,
constants, confidence decay, and orchestration functions.
"""

from options_arena.learning.confidence_decay import (
    decay_confidence as decay_confidence,
)
from options_arena.learning.confidence_decay import (
    run_confidence_decay as run_confidence_decay,
)
from options_arena.learning.strategy_book import (
    render_learned_patterns as render_learned_patterns,
)
from options_arena.learning.strategy_book import (
    run_strategy_mining as run_strategy_mining,
)
from options_arena.learning.weight_tuner import (
    AGENT_VOTE_WEIGHTS as AGENT_VOTE_WEIGHTS,
)
from options_arena.learning.weight_tuner import (
    IndicatorWeights as IndicatorWeights,
)
from options_arena.learning.weight_tuner import (
    VoteWeights as VoteWeights,
)
from options_arena.learning.weight_tuner import (
    auto_tune_indicator_weights as auto_tune_indicator_weights,
)
from options_arena.learning.weight_tuner import (
    auto_tune_weights as auto_tune_weights,
)
from options_arena.learning.weight_tuner import (
    compute_auto_tune_weights as compute_auto_tune_weights,
)
from options_arena.learning.weight_tuner import (
    compute_indicator_tune_weights as compute_indicator_tune_weights,
)

__all__ = [
    "AGENT_VOTE_WEIGHTS",
    "IndicatorWeights",
    "VoteWeights",
    "auto_tune_indicator_weights",
    "auto_tune_weights",
    "compute_auto_tune_weights",
    "compute_indicator_tune_weights",
    "decay_confidence",
    "render_learned_patterns",
    "run_confidence_decay",
    "run_strategy_mining",
]
