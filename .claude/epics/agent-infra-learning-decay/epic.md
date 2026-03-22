---
name: agent-infra-learning-decay
status: backlog
created: 2026-03-22T16:13:36Z
progress: 0%
prd: .claude/prds/agent-infrastructure-evolution.md
parent_epic: agent-infrastructure-evolution
branch: epic/agent-infrastructure-evolution
depends_on:
  - unified-agent-system
github: https://github.com/jobu711/options_arena/issues/672
---

# Epic: agent-infra-learning-decay

## Overview

Strategy rules mined by `learning/strategy_book.py` currently have static confidence.
Patterns that were true 6 months ago but no longer hold keep influencing recommendations
at full weight. This epic adds exponential confidence decay, outcome-triggered validation,
automatic promotion/demotion, and a rules-distill development skill for extracting
cross-cutting principles from agent prompts.

## Scope Boundary

### In Scope
- Extend `StrategyRule` model with `confidence`, `last_validated`, `validation_count` fields
- Migration 038: add confidence columns to `strategy_rules` table
- `decay_confidence()` — exponential decay (5% per month since last validation)
- Validation trigger: when `outcomes collect` runs, cross-reference P&L against rule conditions
- Auto-promotion: confidence >= 0.8 AND validation_count >= 5 → `approved`
- Auto-demotion: decayed confidence < 0.3 → `rejected`
- Extend `render_learned_patterns()` to weight pattern prominence by confidence
- Update `learn playbook` CLI to show confidence scores and last validation dates
- New `.claude/prompts/rules-distill.md` development skill

### Out of Scope (handled by sibling epics)
- Eval framework (agent-infra-eval-harness)
- Structured tool responses (agent-infra-tool-response)
- Per-desk model routing (agent-infra-model-routing)

## Architecture Decisions

- **Outcome-triggered decay only**: Confidence decay runs when `outcomes collect` processes
  new data — not on a timer. Avoids unnecessary processing.
- **Immutable update pattern**: `StrategyRule` stays `frozen=True`. Decay produces new
  model instances; persistence layer handles upsert.
- **Exponential decay**: `confidence * (0.95 ** months_since_validation)`. Never-validated
  rules get a 50% penalty. Simple, predictable, easy to reason about.
- **Confidence-weighted prompt injection**: `render_learned_patterns()` sorts by confidence
  descending. High-confidence rules get stronger language; low-confidence rules appear as
  caveats. Rules below 0.3 are excluded from injection entirely.
- **Rules-distill is a dev skill**, not production code — `.claude/prompts/` artifact only

## Technical Approach

### Model Extension (`models/strategy.py`)
Extend `StrategyRule` with 3 new fields:
- `confidence: float = 0.5` — [0.0, 1.0], isfinite + range validated
- `last_validated: datetime | None = None` — UTC validated
- `validation_count: int = 0` — non-negative

### Migration (`data/migrations/038_confidence_decay.sql`)
```sql
ALTER TABLE strategy_rules ADD COLUMN confidence REAL DEFAULT 0.5;
ALTER TABLE strategy_rules ADD COLUMN last_validated TEXT;
ALTER TABLE strategy_rules ADD COLUMN validation_count INTEGER DEFAULT 0;
```

### Decay Logic (`learning/confidence_decay.py`)
- `decay_confidence(rule, now)` → float — pure function, no I/O
- `validate_rules_against_outcomes(rules, outcomes)` — cross-reference conditions vs P&L
- `auto_promote_demote(rules, repo)` — apply thresholds, persist status changes
- `run_confidence_decay(repo)` — orchestration wrapper, never-raises

### Learning Integration (`learning/strategy_book.py`)
- Extend `render_learned_patterns()` to sort by confidence, exclude < 0.3
- Hook decay into `outcomes collect` flow via learning module entry point

### CLI Enhancement
- `learn playbook --show-confidence` — display confidence + last_validated columns
- `learn decay` — manually trigger decay (for testing/admin)

### Rules Distill Skill (`.claude/prompts/rules-distill.md`)
- Phase 1: Glob prompt files + solution docs
- Phase 2: LLM cross-reads, identifies principles in 2+ sources
- Phase 3: User approval, append to `.claude/rules/`

## Task Breakdown Preview
- [ ] Model extension: add confidence/last_validated/validation_count to StrategyRule
- [ ] Migration 038: add columns to strategy_rules table
- [ ] Decay logic: decay_confidence() + validate_rules_against_outcomes()
- [ ] Auto-promote/demote: threshold-based status changes with persistence
- [ ] Render integration: confidence-weighted pattern injection in render_learned_patterns()
- [ ] CLI enhancement: learn playbook confidence display + learn decay command
- [ ] Rules-distill skill: .claude/prompts/rules-distill.md
- [ ] Tests: decay math, promotion/demotion thresholds, render ordering

## Dependencies
- unified-agent-system (learned patterns injected into recommendation desk prompts)
- Existing outcome data in SQLite (for validation trigger)

## Success Criteria
- Strategy rules show confidence scores in `learn playbook` output
- Confidence decay runs when `outcomes collect` processes new data
- Rules not re-validated in 3+ months show decayed confidence
- Auto-promotion fires at confidence >= 0.8 + validation_count >= 5
- Auto-demotion fires at decayed confidence < 0.3
- `render_learned_patterns()` excludes rules below 0.3 confidence
- All tests pass: `ruff check`, `pytest`, `mypy --strict`

## Estimated Effort
- 6 tasks
- ~200-300 LOC modified (strategy_book, strategy model) + 100 new (decay logic, skill)

## Tasks Created
- [ ] #675 - Model Extension — Add Confidence Fields to StrategyRule (parallel: true)
- [ ] #678 - Migration 038 — Confidence Columns and Repository Update (parallel: false)
- [ ] #680 - Decay Logic — confidence_decay.py Core Functions (parallel: false)
- [ ] #674 - Render Integration — Confidence-Weighted Pattern Injection (parallel: true)
- [ ] #676 - CLI Enhancement — Playbook Confidence Display and Decay Command (parallel: false)
- [ ] #677 - Rules-Distill Development Skill (parallel: true)

Total tasks: 6
Parallel tasks: 3 (#675, #674, #677)
Sequential tasks: 3 (#678, #680, #676)
Estimated total effort: 10-12 hours

## Dependency Graph
```
#675 (Model) ──┬──→ #678 (Migration) ──→ #680 (Decay Logic) ──→ #676 (CLI + Outcomes)
               └──→ #674 (Render)
#677 (Skill) ─── (independent)
```

## Test Coverage Plan
Total test files planned: 4
Total test cases planned: ~35
- tests/unit/models/test_strategy.py (~11 new cases)
- tests/unit/data/test_learning_mixin.py (~7 new cases)
- tests/unit/learning/test_confidence_decay.py (~15 new cases)
- tests/unit/learning/test_strategy_book.py (~8 updated/new cases)
