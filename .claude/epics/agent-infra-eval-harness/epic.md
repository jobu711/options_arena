---
name: agent-infra-eval-harness
status: backlog
created: 2026-03-22T16:13:36Z
progress: 0%
prd: .claude/prds/agent-infrastructure-evolution.md
parent_epic: agent-infrastructure-evolution
branch: epic/agent-infrastructure-evolution
depends_on:
  - unified-agent-system
github: https://github.com/jobu711/options_arena/issues/653
---

# Epic: agent-infra-eval-harness

## Overview

Build an evaluation framework for measuring desk agent and synthesis agent recommendation
quality. Three grader types (Code, Model, Outcome), pass@k metrics, baseline comparison,
and regression test fixtures from historical wrong recommendations. This is the
foundational quality measurement layer — without it, prompt changes are blind.

## Scope Boundary

### In Scope
- `EvalDefinition`, `EvalRun`, `EvalReport` Pydantic models
- `EvalType` (capability/regression), `GraderType` (code/model/outcome) StrEnums
- Code graders: deterministic pytest assertions on `DomainAssessment` fields
- Model graders: LLM-as-judge on qualitative fields (key_factors, summary)
- Outcome graders: direction/confidence vs actual P&L calibration
- pass@1 and pass@3 metric computation
- Baseline storage (JSON) + comparison logic (SHIP/NEEDS_WORK/BLOCKED verdict)
- SQLite persistence for eval history (migration 039)
- CLI `eval` subcommand group (define, check, report, list)
- API endpoints (`POST /api/eval/check`, `GET /api/eval/report`, `GET /api/eval/history`)
- Regression test fixture generation from historical wrong recommendations
- `tests/regression/` test suite with parametrized fixtures

### Out of Scope (handled by sibling epics)
- Structured tool responses (agent-infra-tool-response)
- Per-desk model routing and cost tracking (agent-infra-model-routing)
- Strategy rule confidence decay (agent-infra-learning-decay)

## Architecture Decisions

- Eval definitions stored as git-tracked JSON in `.claude/evals/` for reproducibility
- Eval run history persisted to SQLite via `EvalMixin` for trend analysis
- Model grader uses a different LLM provider than debate agents (avoid self-grading)
- Regression fixtures include serialized `MarketContext` + `TickerScore` snapshots
- Code graders are pure functions — no I/O, deterministic
- Tests use `pydantic_ai.models.test.TestModel` — no real API calls during eval

## Technical Approach

### Data Models (`models/eval.py`)
- `EvalDefinition`: name, eval_type, target_desk, grader_type, fixture path, expected direction/confidence
- `EvalRun`: eval_name, timestamp, passed, attempts, successes, model_used, duration_ms, details
- `EvalReport`: runs list, pass_at_1, pass_at_3, regressions list, verdict enum

### Grader Implementations
- `CodeGrader`: pytest assertions on typed assessment fields (direction, confidence bounds, trend_strength)
- `ModelGrader`: PydanticAI agent with rubric prompt judges qualitative fields
- `OutcomeGrader`: compare recommendation direction+confidence vs actual P&L from outcomes

### Persistence (`data/_eval.py`)
- `EvalMixin` on Repository — save/query eval runs
- Migration 039: `eval_runs` table + `eval_definitions` table

### CLI (`cli/eval.py`)
- `eval define <name>` — create eval definition interactively
- `eval check [--desk X]` — run evals, compare to baseline
- `eval report` — full report with pass@k, regressions, verdict
- `eval list` — all evals with status

### API (`api/routes/eval.py`)
- `POST /api/eval/check` — trigger eval run
- `GET /api/eval/report` — latest report
- `GET /api/eval/history` — historical pass rates

### Regression Testing
- `tools/generate_regression_fixtures.py` — query outcomes for high-confidence failures, serialize as JSON
- `tests/regression/test_recommendation_regression.py` — parametrized tests
- Fixtures in `tests/regression/fixtures/` (git-tracked)

## Task Breakdown Preview
- [ ] Models + enums: `EvalDefinition`, `EvalRun`, `EvalReport`, `EvalType`, `GraderType`
- [ ] Code grader: deterministic assertions on DomainAssessment fields
- [ ] Model grader: LLM-as-judge with rubric prompt
- [ ] Outcome grader: direction/confidence vs P&L calibration
- [ ] Eval runner: orchestrate graders, compute pass@k, baseline comparison
- [ ] Persistence: migration 039, EvalMixin, eval run storage
- [ ] CLI: `eval` subcommand group (define, check, report, list)
- [ ] API: eval endpoints + route registration
- [ ] Regression fixtures: generator script + parametrized test suite
- [ ] Seeding: create initial evals from existing outcome data

## Dependencies
- unified-agent-system (orchestrator + cutover complete)
- Existing outcome data in SQLite (for seeding evals and regression fixtures)

## Success Criteria
- `options-arena eval check` runs 10+ evals and reports pass@k metrics
- Eval baselines exist for all 6 desks + synthesis agent
- Regression suite has 5+ fixtures from historical wrong recommendations
- SHIP/NEEDS_WORK/BLOCKED verdict compares against stored baseline
- All tests pass: `ruff check`, `pytest`, `mypy --strict`

## Estimated Effort
- 9 tasks
- ~1,000-1,500 LOC (new module + tests)
- Largest epic in this PRD — new module with 3 grader types

## Tasks Created
- [ ] #655 - Eval data models and enums (parallel: true)
- [ ] #657 - Eval persistence layer — migration + EvalMixin (parallel: false, depends: #655)
- [ ] #660 - Code grader implementation (parallel: true, depends: #655)
- [ ] #656 - Model grader — LLM-as-judge (parallel: true, depends: #655)
- [ ] #659 - Outcome grader — P&L calibration (parallel: true, depends: #655, #657)
- [ ] #661 - Eval runner with pass@k and baseline comparison (parallel: false, depends: #657-#659)
- [ ] #658 - CLI eval subcommand group (parallel: true, depends: #661)
- [ ] #662 - API eval endpoints (parallel: true, depends: #661)
- [ ] #663 - Regression fixture generator and test suite (parallel: true, depends: #657)

Total tasks: 9
Parallel tasks: 7
Sequential tasks: 2 (#657, #661)
Estimated total effort: 23-31 hours

## Test Coverage Plan
Total test files planned: 9
Total test cases planned: ~67
