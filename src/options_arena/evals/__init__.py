"""Options Arena — Evaluation harness for agent quality measurement.

Three grader types (Code, Model, Outcome), pass@k metrics, and baseline
comparison. Provides the quality measurement layer for the recommendation
pipeline.
"""

from options_arena.evals.graders import CodeGrader, ModelGrader, OutcomeGrader
from options_arena.evals.runner import run_eval_check

__all__ = [
    "CodeGrader",
    "ModelGrader",
    "OutcomeGrader",
    "run_eval_check",
]
