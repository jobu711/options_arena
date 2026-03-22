# Research: agent-infra-learning-decay

## PRD Summary

Strategy rules mined by `learning/strategy_book.py` have static confidence — patterns that were true months ago keep influencing recommendations at full weight. This epic adds exponential confidence decay (5% per month), outcome-triggered validation, automatic promotion/demotion at threshold boundaries, confidence-weighted prompt injection, CLI enhancements, and a rules-distill development skill.

Source: Parent PRD `agent-infrastructure-evolution.md` (Epic D), Epic file `agent-infra-learning-decay/epic.md`.

## Relevant Existing Modules

- `models/strategy.py` — `StrategyRule` (frozen, 8 fields), `StrategyCondition`, `AgentMemory`. Missing: `confidence`, `last_validated`, `validation_count` fields.
- `models/enums.py` — `RuleStatus` (CANDIDATE, APPROVED, REJECTED), `ConditionOperator` (6 members). No changes needed for decay (confidence is a float, not an enum state).
- `learning/strategy_book.py` — `mine_patterns()`, `filter_significant()`, `generate_rules()`, `render_learned_patterns()`, `run_strategy_mining()`. Key target for decay integration.
- `learning/weight_tuner.py` — `auto_tune_weights()`, `_auto_tune_indicator_weights_inner()`. Reusable never-raises orchestration pattern. Accesses outcome data via `repo.get_outcome_signal_pairs()`.
- `data/_learning.py` — `LearningMixin` with `save_strategy_rule()`, `get_strategy_rules()`, `update_rule_status()`, `save_agent_memory()`, `get_agent_memories()`. Needs new `update_rule_confidence()` method.
- `data/migrations/036_strategy_mining.sql` — Current `strategy_rules` schema (8 columns). Migration 037 already exists (`recommendation_results`). Next available: **038**.
- `services/outcome_collector.py` — `OutcomeCollector.collect_outcomes()` → `_collect_for_period()` → `repo.save_contract_outcomes()`. Integration point for decay trigger.
- `cli/agency.py` — `learn` subcommand group: `learn mine`, `learn playbook`, `learn status`, `learn weights`. Target for `learn decay` command and playbook confidence columns.
- `agents/_routing.py` — Calls `render_learned_patterns()` before desk dispatch. Injection point unchanged.
- `agents/_desk_deps.py` — `DeskDeps.learned_patterns: str = ""`. No changes needed.

## Existing Patterns to Reuse

### Never-Raises Orchestration Pattern
**Where**: `learning/weight_tuner.py:auto_tune_weights()`, `learning/strategy_book.py:run_strategy_mining()`
**How to apply**: `run_confidence_decay(repo)` wraps all decay logic in try/except, logs failures, returns empty results. Internal `_run_decay_pipeline()` may raise.

### Pure Computation + Orchestration Separation
**Where**: `strategy_book.py` — `mine_patterns()` (pure) vs `run_strategy_mining()` (orchestration)
**How to apply**: `decay_confidence()` and `validate_rules_against_outcomes()` are pure functions (no I/O). `run_confidence_decay()` is the orchestration wrapper that touches the DB.

### Frozen Model Immutable Update
**Where**: All frozen models in `models/` — new instances replace old ones
**How to apply**: `StrategyRule` stays `frozen=True`. Decay produces new `StrategyRule` instances with updated confidence. Persistence layer handles upsert by `rule_id`.

### Outcome Data Access
**Where**: `weight_tuner.py:_auto_tune_indicator_weights_inner()` uses `repo.get_outcome_signal_pairs()`
**How to apply**: New `repo.get_outcomes_for_validation()` query returns outcomes with conditions that can be cross-referenced against strategy rule conditions.

### Rich Table CLI Rendering
**Where**: `cli/outcomes.py`, `cli/agency.py` — Rich tables with typed data
**How to apply**: Add `confidence`, `last_validated`, `validation_count` columns to `learn playbook` table.

## Existing Code to Extend

### `models/strategy.py` — Add 3 Fields to StrategyRule
```python
# Current: 8 fields (rule_id, pattern, conditions, win_rate, avg_return, sample_size, status, created_at)
# Add: confidence, last_validated, validation_count
# Keep frozen=True — create new instances for updates
# Validators: isfinite() + [0.0, 1.0] for confidence, UTC for last_validated, >= 0 for validation_count
```

### `learning/strategy_book.py` — Extend render_learned_patterns()
Current implementation (lines ~319-356):
- Filters APPROVED rules only
- Outputs `<<<LEARNED_PATTERNS>>>` delimited block with pattern, win_rate, avg_return
- Truncates at pattern boundaries if > 1800 chars

Changes needed:
- Sort by confidence descending (high-confidence first)
- Exclude rules with `decayed_confidence < 0.3`
- Add confidence field to output: `Confidence: {rule.confidence:.0%}`
- High-confidence rules get stronger language; low-confidence as caveats

### `data/_learning.py` — Add Confidence Update Method
New method: `update_rule_confidence(rule_id, confidence, last_validated, validation_count, *, commit=True) -> bool`
Pattern: follows existing `update_rule_status()` — parameterized UPDATE, returns True if rowcount > 0.

### `data/migrations/038_confidence_decay.sql`
```sql
ALTER TABLE strategy_rules ADD COLUMN confidence REAL DEFAULT 0.5;
ALTER TABLE strategy_rules ADD COLUMN last_validated TEXT;
ALTER TABLE strategy_rules ADD COLUMN validation_count INTEGER DEFAULT 0;
```

### `cli/agency.py` — Extend learn Subcommand
- `learn playbook` adds columns: confidence, last_validated, validation_count
- `learn decay` new command: manually triggers decay cycle (for testing/admin)
- Both follow existing async wrapper pattern: `def cmd() -> None: asyncio.run(_cmd_async())`

## Potential Conflicts

### StrategyRule Frozen Model — LOW RISK
**Issue**: Adding fields to a frozen model requires all constructors to pass them. Existing code that creates `StrategyRule` instances must supply new fields.
**Mitigation**: All 3 new fields have defaults (`confidence=0.5`, `last_validated=None`, `validation_count=0`). Existing code works unchanged. `_row_to_strategy_rule()` in `_learning.py` needs update to read new columns.

### Migration 038 Number — LOW RISK
**Issue**: Migration 037 already exists (`recommendation_results`). The epic doc says 038 but needs verification.
**Mitigation**: Confirmed latest migration is 037. Migration 038 is the correct next number.

### Outcome Data Cross-Reference — MEDIUM RISK
**Issue**: Strategy rule conditions use `StrategyCondition(field, operator, value)` — matching these against outcome data requires interpreting the condition operator and comparing against the right outcome fields.
**Mitigation**: Build a `evaluate_condition(condition, outcome_data)` pure function that handles all 6 operators. Test exhaustively with parametrized tests.

### Concurrent Outcome Collection + Decay — LOW RISK
**Issue**: If decay runs while outcome collection is in progress, stale data may be used.
**Mitigation**: Decay runs after outcome collection completes (sequential in the orchestration flow), not in parallel. Single-threaded SQLite WAL handles isolation.

## Open Questions

1. **Decay trigger timing**: The epic says "outcome-triggered" — should decay run automatically at the end of `outcomes collect`, or should it be a separate `learn decay` command that users run manually?
   - **Recommendation**: Both. Auto-trigger after outcome collection (opt-in via config), plus manual `learn decay` command.

2. **Initial confidence for existing rules**: When migration 038 runs, existing rules get `confidence DEFAULT 0.5`. Should approved rules get a higher initial confidence (e.g., 0.8) since they were human-approved?
   - **Recommendation**: Yes — approved rules should start at 0.8 since human approval is a signal of quality. Migration should UPDATE approved rules to 0.8 after ALTER.

3. **Condition matching complexity**: How do we match `StrategyCondition` fields against outcome data? The conditions reference indicator fields (sector, IV bucket, DTE bucket, direction) — do we have those values stored alongside outcomes?
   - **Finding**: Outcomes are stored per-contract with `recommended_contract_id` FK. The scan run's ticker scores (with indicator signals) are persisted separately. Cross-referencing requires joining contract → scan_run → ticker_scores to get the indicator values at scan time.

## Recommended Architecture

### New Module: `learning/confidence_decay.py`

Pure computation functions (no I/O):
- `decay_confidence(rule: StrategyRule, now: datetime) -> float` — exponential decay formula
- `validate_rule(rule: StrategyRule, outcomes: list[OutcomeMatch]) -> ValidationResult` — cross-reference P&L
- `check_promotion(rule: StrategyRule) -> RuleStatus | None` — threshold check
- `check_demotion(rule: StrategyRule, decayed_confidence: float) -> RuleStatus | None` — threshold check

Orchestration wrapper:
- `run_confidence_decay(repo: Repository) -> DecayReport` — never-raises, catches all exceptions

### Data Flow

```
outcomes collect → save outcomes → [auto-trigger] → run_confidence_decay()
  ├── get_strategy_rules(status=APPROVED)
  ├── get_strategy_rules(status=CANDIDATE)
  ├── For each rule:
  │   ├── decay_confidence(rule, now) → decayed float
  │   ├── validate_rule(rule, matching_outcomes) → ValidationResult
  │   ├── check_promotion(rule) → APPROVED if meets threshold
  │   └── check_demotion(rule, decayed_confidence) → REJECTED if below threshold
  ├── Batch update confidence + validation counts
  └── Return DecayReport (rules_updated, promoted, demoted)
```

### Model Extension

```python
# In models/strategy.py — StrategyRule adds:
confidence: float = 0.5              # [0.0, 1.0], isfinite validated
last_validated: datetime | None = None  # UTC validated
validation_count: int = 0            # >= 0 validated
```

### Render Integration

```python
# In learning/strategy_book.py — render_learned_patterns() changes:
# 1. Filter: approved AND confidence >= 0.3
# 2. Sort: confidence DESC
# 3. Output: add "Confidence: 85%" line per rule
```

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/models/test_strategy.py` — model validation, JSON roundtrip, frozen checks
- `tests/unit/data/test_learning_mixin.py` — CRUD, status filtering, upsert
- Factory: `_make_rule(**overrides)` helper for creating test StrategyRule instances

### New Test Files (4 files, ~35 cases planned in epic)
- `tests/unit/models/test_strategy.py` — ~11 new cases: confidence validators (NaN, range), last_validated UTC, validation_count >= 0, defaults, JSON roundtrip with new fields
- `tests/unit/data/test_learning_mixin.py` — ~7 new cases: update_rule_confidence, read-back new columns, migration 038 schema
- `tests/unit/learning/test_confidence_decay.py` — ~15 new cases: decay formula (exact values, boundary, never-validated penalty), validation logic, promotion thresholds, demotion thresholds, batch processing
- `tests/unit/learning/test_strategy_book.py` — ~8 updated/new cases: render_learned_patterns with confidence sorting, exclusion below 0.3, truncation with confidence field

### Testing Conventions
- `@pytest.mark.asyncio` for async tests
- Parametrized tests for threshold boundaries (`@pytest.mark.parametrize`)
- `_make_rule()` factory extended with new fields
- SQLite in-memory DB for data layer tests

## Estimated Complexity

**Size: S-M** (Small to Medium)

**Justification**:
- Core decay logic is a small pure function (~20 lines)
- Model extension is 3 fields with standard validators (established pattern)
- Migration is 3 ALTER TABLE statements
- LearningMixin needs 1 new method (follows existing `update_rule_status()` pattern)
- `render_learned_patterns()` changes are surgical (sort + filter + 1 extra line)
- CLI changes add 1 command + 3 columns to existing table
- No new external dependencies
- No architectural boundary changes
- Clear precedent in existing codebase for every pattern needed
- Risk: condition matching against outcome data is the most complex part (MEDIUM)
