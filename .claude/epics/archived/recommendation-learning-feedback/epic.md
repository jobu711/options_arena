---
name: recommendation-learning-feedback
status: completed
created: 2026-03-24T00:09:54Z
updated: 2026-03-24T03:11:21Z
completed: 2026-03-24T03:11:21Z
progress: 100%
prd: .claude/prds/recommendation-learning.md
parent_epic: recommendation-learning
depends_on:
  - recommendation-learning-foundation
github: https://github.com/jobu711/options_arena/issues/772
---

# Epic: recommendation-learning-feedback

## Overview

Enhance the existing learning infrastructure to leverage prediction data: enrich strategy
mining with market condition dimensions, compute contract guidance from outcome data, feed
prediction-derived accuracy into weight tuning, and inject guidance into agent prompts.
Delivers user stories US-3, US-4, and US-5. Regime awareness emerges from condition-enriched
pattern mining rather than a hand-coded classifier.

## Scope Boundary

### In Scope
- `strategy_book.py` — add ADX/volatility condition dimensions to `OutcomeWithContext` and mining pipeline
- `contract_guidance.py` — new module computing optimal delta/DTE ranges from outcomes
- `weight_tuner.py` — accept prediction-derived per-desk accuracy
- `<<<CONTRACT_GUIDANCE>>>` prompt injection block in synthesis agent
- Enhanced `learn tune-votes` output showing prediction-derived accuracy
- Enhanced `learn mine` / `learn playbook` with condition-based patterns
- Unit tests

### Out of Scope (handled by sibling epics)
- Models, migration, data CRUD (foundation epic)
- Prediction recording in scan/orchestrator (attribution epic)
- Prediction scoring logic (attribution epic)
- Attribution CLI/API (attribution epic)

## Architecture Decisions

- **Condition bucketing reuses existing patterns**: `_classify_iv()`, `_classify_dte()` from `strategy_book.py`. Add `_classify_adx()` and `_classify_vol()` following identical pattern.
- **`OutcomeWithContext` extension is backward-compatible**: new fields are `float | None` with defaults, SQL updated to LEFT JOIN indicator context. Existing callers unaffected.
- **Contract guidance is a separate module** (`learning/contract_guidance.py`) to keep `prediction_ledger.py` focused on scoring/attribution and avoid file conflicts with attribution epic.
- **Contract guidance is advisory**: rendered as `<<<CONTRACT_GUIDANCE>>>` prompt block, does not override `OptionsFilters` defaults.
- **Weight tuner interface unchanged**: `compute_auto_tune_weights()` still takes `list[AgentAccuracyReport]`, but the data source changes from `agent_predictions` to `predictions` table, providing richer per-desk accuracy.
- **Chi-squared significance** test (p < 0.05) on mined patterns with condition dimensions, minimum 20 samples per condition bucket.

## Technical Approach

### Strategy Mining Enhancement (`learning/strategy_book.py`, ~60-80 lines changed)

Extend `OutcomeWithContext` dataclass:
```python
@dataclass
class OutcomeWithContext:
    # Existing fields...
    sector: str | None
    iv_level: str | None
    dte_at_entry: int | None
    direction: str | None
    return_pct: float | None
    is_winner: bool | None
    # NEW fields for condition dimensions
    adx: float | None = None
    atr_pct: float | None = None
    rsi: float | None = None
```

New classifier functions:
```python
ADX_BUCKETS = [(0, 20, "weak"), (20, 30, "moderate"), (30, 100, "strong")]
VOL_BUCKETS = [(0, 1.5, "low"), (1.5, 3.0, "medium"), (3.0, 100, "high")]

def _classify_adx(adx: float | None) -> str | None: ...
def _classify_atr_pct(atr_pct: float | None) -> str | None: ...
```

Update `_fetch_outcomes_with_context()` SQL to LEFT JOIN indicator context from
`predictions` table (where available) or `ticker_metadata`.

Update `_generate_rules()` to include condition dimensions in rule generation,
producing patterns like "Trend desk 89% accurate when ADX > 25 and IV Rank < 30".

### Contract Guidance (`learning/contract_guidance.py`, ~120-150 lines, NEW FILE)

```python
def compute_contract_guidance(outcomes: list[ContractOutcome]) -> ContractGuidance | None:
    """Compute optimal delta/DTE ranges from outcome data.

    Buckets outcomes by delta range (0.10 increments) and DTE range (15-day increments).
    Returns ranges with highest win rate if >= 30 samples exist, else None.
    """

def render_contract_guidance(guidance: ContractGuidance) -> str:
    """Render <<<CONTRACT_GUIDANCE>>> prompt block."""
    lines = ["<<<CONTRACT_GUIDANCE>>>"]
    lines.append(f"Optimal delta range: {guidance.optimal_delta_low:.2f}-{guidance.optimal_delta_high:.2f} "
                 f"(win rate: {guidance.delta_win_rate:.0%}, n={guidance.sample_count})")
    lines.append(f"Optimal DTE range: {guidance.optimal_dte_low}-{guidance.optimal_dte_high} days "
                 f"(win rate: {guidance.dte_win_rate:.0%})")
    lines.append("<<<END_CONTRACT_GUIDANCE>>>")
    return "\n".join(lines)
```

### Prompt Injection (`agents/prompts/` or orchestrator)

Inject `<<<CONTRACT_GUIDANCE>>>` alongside existing `<<<LEARNED_PATTERNS>>>` and
`<<<TUNED_WEIGHTS>>>` blocks in the synthesis agent prompt. Follows identical injection
pattern from `strategy_book.py:render_learned_patterns()`.

### Weight Tuner (`learning/weight_tuner.py`, ~20-30 lines changed)

Update data source for `compute_auto_tune_weights()`:
- Current: queries `agent_predictions` table (legacy debate data)
- New: queries `predictions` table for per-desk accuracy with scored outcomes
- Interface unchanged: still returns `list[AgentAccuracyReport]`
- Enhanced `learn tune-votes` CLI output shows prediction-derived accuracy as basis

### Enhanced CLI Output (`cli/outcomes.py`, ~10-15 lines)

- `learn tune-votes`: show "Based on N scored predictions" in output header
- `learn mine` / `learn playbook`: condition-based patterns display naturally (existing rendering handles new dimension fields)

## Task Breakdown Preview

- [ ] Task 1: `learning/strategy_book.py` — extend `OutcomeWithContext` + classifier functions + SQL update
- [ ] Task 2: `learning/strategy_book.py` — update rule generation to include condition dimensions
- [ ] Task 3: `learning/contract_guidance.py` — compute optimal delta/DTE + render prompt block
- [ ] Task 4: `learning/weight_tuner.py` — switch data source to predictions table
- [ ] Task 5: Prompt injection — `<<<CONTRACT_GUIDANCE>>>` block in synthesis agent
- [ ] Task 6: Unit tests (strategy mining conditions, contract guidance, weight tuner, prompt rendering)

## Dependencies

- **Foundation epic**: Must be merged — provides `Prediction` model, `ContractGuidance` model, `PredictionSource` enum, data methods
- **Sibling (attribution)**: No dependency — zero shared modified files. Attribution writes predictions; feedback reads them. Both work independently once foundation's data layer exists.
- **Existing**: `strategy_book.py` patterns (reuse `_classify_*` helpers), `weight_tuner.py` interface, `outcome_collector.py` (read-only)

## Success Criteria

- Strategy mining discovers condition-specific patterns (e.g., "desk X accurate when ADX > 25")
- Chi-squared significance test enforced (p < 0.05) with minimum 20 samples per condition bucket
- Contract guidance returns `None` when < 30 outcomes, valid `ContractGuidance` when sufficient
- `<<<CONTRACT_GUIDANCE>>>` block renders correctly and respects max length
- Weight tuner produces different proposals when using prediction-derived accuracy vs. legacy data
- `learn tune-votes` shows prediction-based accuracy with sample counts
- All existing strategy mining tests still pass (backward-compatible extension)
- All tests green, mypy --strict clean, ruff clean

## Tasks Created

- [x] #779 - Extend OutcomeWithContext with condition dimensions (parallel: true)
- [x] #780 - Enrich rule generation with condition dimensions (parallel: false, depends: #779)
- [x] #781 - Contract guidance computation and rendering (parallel: true)
- [x] #782 - Weight tuner prediction-derived accuracy (parallel: true)
- [x] #783 - Prompt injection for contract guidance and tuned weights (parallel: false, depends: #781, #782)
- [x] #784 - Feedback loop integration tests (parallel: false, depends: #780, #783)

Total tasks: 6
Parallel tasks: 3 (#779, #781, #782)
Sequential tasks: 3 (#780, #783, #784)
Estimated total effort: 17-23 hours

## Test Coverage Plan

Total test files planned: 4
- `tests/unit/learning/test_strategy_book_conditions.py` (~10 test cases)
- `tests/unit/learning/test_contract_guidance.py` (~10 test cases)
- `tests/unit/learning/test_weight_tuner_predictions.py` (~8 test cases)
- `tests/unit/agents/test_synthesis_prompt_injection.py` (~9 test cases)
- `tests/integration/test_feedback_loop.py` (~7 test cases)
Total test cases planned: ~44
Critical markers: 1 (enriched mining integration)

## Estimated Effort

- ~6 tasks, ~300-400 new lines of production code
- ~44 unit + integration tests across 5 test files
- Low-medium risk — extends well-established patterns, no new external dependencies
