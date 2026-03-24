"""Options Arena — Self-Improvement Learning Module.

Re-exports the public API for the learning package: weight tuning algorithms,
constants, confidence decay, contract guidance, and orchestration functions.
"""

from options_arena.learning.confidence_decay import (
    decay_confidence as decay_confidence,
)
from options_arena.learning.confidence_decay import (
    run_confidence_decay as run_confidence_decay,
)
from options_arena.learning.contract_guidance import (
    compute_contract_guidance as compute_contract_guidance,
)
from options_arena.learning.contract_guidance import (
    fetch_contract_guidance as fetch_contract_guidance,
)
from options_arena.learning.contract_guidance import (
    render_contract_guidance as render_contract_guidance,
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
from options_arena.learning.weight_tuner import (
    render_tuned_weights as render_tuned_weights,
)

__all__ = [
    "AGENT_VOTE_WEIGHTS",
    "IndicatorWeights",
    "VoteWeights",
    "auto_tune_indicator_weights",
    "auto_tune_weights",
    "compute_auto_tune_weights",
    "compute_contract_guidance",
    "compute_indicator_tune_weights",
    "decay_confidence",
    "fetch_contract_guidance",
    "render_contract_guidance",
    "render_learned_patterns",
    "render_tuned_weights",
    "run_confidence_decay",
    "run_strategy_mining",
]
