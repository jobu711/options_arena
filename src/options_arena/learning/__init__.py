"""Options Arena — Self-Improvement Learning Module.

Re-exports the public API for the learning package: weight tuning algorithms,
constants, and orchestration functions.
"""

from options_arena.learning.weight_tuner import (
    AGENT_VOTE_WEIGHTS as AGENT_VOTE_WEIGHTS,
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
    "VoteWeights",
    "auto_tune_indicator_weights",
    "auto_tune_weights",
    "compute_auto_tune_weights",
    "compute_indicator_tune_weights",
]
