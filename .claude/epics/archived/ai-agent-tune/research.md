# Research: ai-agent-tune

## PRD Summary

Build a closed-loop agent tuning system that: (1) measures per-agent prediction accuracy against real outcomes, (2) auto-adjusts `AGENT_VOTE_WEIGHTS`, (3) extracts all 6 remaining inline prompts to `agents/prompts/`, (4) adds few-shot examples with regression tests, and (5) exposes calibration metrics via CLI + API. 5 implementation phases, XL effort.

## Relevant Existing Modules

- **`agents/`** — 6-agent PydanticAI debate system (Trend, Volatility, Flow, Fundamental, Risk, Contrarian). Orchestrator coordinates phases, synthesizes verdict via log-odds pooling with `AGENT_VOTE_WEIGHTS`.
- **`agents/prompts/`** — Only 2 of 8 prompts extracted (trend_agent.py, contrarian_agent.py). 6 remain inline in their agent modules.
- **`agents/_parsing.py`** — Shared infrastructure: `PROMPT_RULES_APPENDIX` (v3.0), `RISK_STRATEGY_TREE`, `compute_citation_density()`, output validators (`build_cleaned_*` helpers).
- **`agents/orchestrator.py`** — `AGENT_VOTE_WEIGHTS` defined at line 919, used at line 1157 in `synthesize_verdict()`. `extract_agent_predictions()` already extracts per-agent predictions from debate results.
- **`models/analysis.py`** — `AgentPrediction` model (frozen, line 816-844) with `debate_id`, `agent_name`, `direction`, `confidence`, `created_at`.
- **`models/analytics.py`** — 9 existing analytics result models (WinRateResult, ScoreCalibrationBucket, etc.) — pattern to follow for new calibration models.
- **`models/config.py`** — `AppSettings` with nested `AnalyticsConfig(BaseModel)`. Has `holding_periods`, `batch_size`, `collection_timeout`.
- **`services/outcome_collector.py`** — `OutcomeCollector` fetches outcomes at T+1/T+5/T+10/T+20. Returns typed `ContractOutcome` models.
- **`data/repository.py`** — 6 existing analytics query methods (win_rate, score_calibration, etc.) at line 999+. Pattern: async, parameterized SQL, returns `list[Model]`.
- **`data/migrations/`** — Latest is `025_agent_predictions.sql`. Next number: **026**.
- **`cli/outcomes.py`** — `outcomes collect` and `outcomes summary` subcommands. Typer sync wrappers around async internals.
- **`api/routes/analytics.py`** — 6 existing `/api/analytics/*` endpoints with rate limiting and `Depends(get_repo)`.

## Existing Patterns to Reuse

- **Prompt extraction pattern**: `agents/prompts/trend_agent.py` exports `TREND_SYSTEM_PROMPT` constant, imports `PROMPT_RULES_APPENDIX` from `_parsing.py`, concatenates at module level. All 6 new prompt files follow this pattern.
- **Analytics model pattern**: `models/analytics.py` frozen Pydantic models with `ConfigDict(frozen=True)`, field validators for numerics (`math.isfinite()`), confidence bounds. New `AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData` follow this pattern.
- **Repository query pattern**: `repository.py` analytics methods use `conn.execute()` → `cursor.fetchall()` → reconstruct typed models from `aiosqlite.Row`. New calibration queries follow this.
- **CLI command pattern**: `outcomes.py` uses Typer subcommand group, sync wrappers with `asyncio.run()`, Rich tables for display, service lifecycle in `finally` blocks.
- **API endpoint pattern**: `analytics.py` routes use `@router.get()`, `@limiter.limit("60/minute")`, `Depends(get_repo)`, return typed models.
- **Config pattern**: Nested `BaseModel` submodels in `AppSettings(BaseSettings)`. Env override via `ARENA_ANALYTICS__FIELD_NAME`.

## Existing Code to Extend

- **`agents/orchestrator.py:1157`** — `AGENT_VOTE_WEIGHTS.get(name, 0.1)` lookup. Injection point for auto-tune: read from DB when `auto_tune_weights` config enabled.
- **`models/analytics.py`** — Add `AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData` models alongside existing analytics models.
- **`models/config.py`** — Add `auto_tune_weights: bool = False` to `AnalyticsConfig` (or `DebateConfig`).
- **`data/repository.py`** — Add ~6 new async methods for agent accuracy queries, calibration buckets, auto-tune weight persistence.
- **`cli/outcomes.py`** — Add `agent-accuracy`, `calibration`, `agent-weights` subcommands.
- **`api/routes/analytics.py`** — Add 3 new endpoints: `/api/analytics/agent-accuracy`, `/api/analytics/agent-calibration`, `/api/analytics/agent-weights`.
- **`agents/_parsing.py`** — Remove `RISK_STRATEGY_TREE` (moves to `agents/prompts/risk.py`). Keep `PROMPT_RULES_APPENDIX`.

## Inline Prompts to Extract (6 of 8)

| Agent | File | Lines | Version | Complexity | Notes |
|-------|------|-------|---------|------------|-------|
| Bull | `bull.py:28-61` | ~34 | v2.1 | Low | Simple extraction |
| Bear | `bear.py:29-65` | ~36 | v2.0 | Medium | Has dynamic prompt decorator |
| Risk | `risk.py:28-87` | ~48 + 9 | v2.1 | High | Strategy tree moves here |
| Volatility | `volatility.py:28-100+` | ~130 | v3.0 | High | Very detailed, 6 subsections |
| Flow | `flow_agent.py:29-77` | ~48 | v2.0 | Medium | Has dynamic prompt decorator |
| Fundamental | `fundamental_agent.py:28-93` | ~65 | v3.0 | High | 3 subsections |

Already extracted (no changes): `trend_agent.py` (v1.0), `contrarian_agent.py` (v1.0).

## Potential Conflicts

- **Dynamic prompts**: Bear, Risk, and Flow agents use `@agent.system_prompt(dynamic=True)` decorators that inject runtime data (`opponent_argument`, `bull_response`, `bear_response`). Extraction must preserve these decorators in the agent files — only the static prompt constant moves to `prompts/`.
- **Token budget growth**: Volatility prompt is already ~130 lines. Adding few-shot examples may push it past 2000 tokens. Monitor with `tiktoken` during Phase 4.
- **Test imports**: 30+ test files reference agent modules. Prompt extraction should not change public API — agents still export the same `Agent` instances. Tests checking prompt content directly will need updates.
- **RISK_STRATEGY_TREE relocation**: Currently in `_parsing.py`, used only by `risk.py`. Moving to `agents/prompts/risk.py` changes the import path. Only `risk.py` imports it, so impact is limited.
- **Auto-tune weight sum constraint**: `AGENT_VOTE_WEIGHTS` sum intentionally < 1.0 (0.85). Auto-tuned weights must respect this constraint. Floor (0.05) + cap (0.35) + risk=0.0 + sum<1.0 all need validation.

## Open Questions

1. **Config location for auto_tune_weights**: Add to `AnalyticsConfig` or `DebateConfig`? PRD says `DebateConfig.auto_tune_weights` but `AnalyticsConfig` already owns calibration concerns. **Recommendation**: Follow PRD — use `DebateConfig`.
2. **scan_run_id column in agent_predictions**: Migration 025 does NOT have `scan_run_id`. The PRD mentions indexing on `(agent_name, scan_run_id)` but the current schema links via `debate_id` → `recommended_contracts` → `scan_runs`. May need a JOIN rather than a direct index. Investigate migration 025 schema.
3. **Minimum sample threshold**: PRD says 10 outcomes. Should this be configurable via `AnalyticsConfig.min_sample_size`? **Recommendation**: Yes, add as config field with default 10.
4. **Holding period for accuracy**: Which holding period defines "accuracy"? T+1 is too noisy, T+20 is too slow. **Recommendation**: Use T+5 as default, make configurable.

## Recommended Architecture

### Phase 1 (Prompt Extraction)
- Create 6 new files in `agents/prompts/` following `trend_agent.py` pattern
- Each exports `{AGENT}_SYSTEM_PROMPT` constant
- Agent files import constant, remove inline definition
- Move `RISK_STRATEGY_TREE` from `_parsing.py` to `prompts/risk.py`
- Zero behavior change — exact same prompt text

### Phase 2 (Calibration Infrastructure)
- New models in `models/analytics.py`: `AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData`
- Migration `026_agent_calibration.sql`: index on `agent_predictions(agent_name)`, `auto_tune_weights` table
- Repository methods: JOIN `agent_predictions` → `recommended_contracts` → `contract_outcomes` for accuracy computation
- New service: `services/accuracy_calibrator.py` (pure computation, no I/O — takes prediction+outcome pairs, returns metrics)
- CLI: 3 new `outcomes` subcommands
- API: 3 new `/api/analytics/` endpoints

### Phase 3 (Prompt Quality Suite)
- `tests/unit/agents/test_prompt_structure.py`: version header, token count, required sections for all 8 prompts
- `tests/unit/agents/test_prompt_quality.py`: `TestModel`-based output validation, citation density > 20%
- Parameterized tests: one test function, 8 prompt constants

### Phase 4 (Few-Shot Examples)
- Add golden examples to each prompt (anonymized real output)
- Version bump v1.x → v2.0 for all prompts
- Token budget increase from 1500 to 2000
- Measure citation density before/after

### Phase 5 (Auto-Tune Weights)
- Brier score computation: `mean((confidence - outcome)^2)`
- Weight formula: normalized inverse Brier (lower = higher weight)
- Floor 0.05, cap 0.35, risk=0.0, sum < 1.0
- `DebateConfig.auto_tune_weights: bool = False`
- Orchestrator reads from DB when enabled, falls back to manual `AGENT_VOTE_WEIGHTS`

## Test Strategy Preview

- **Existing patterns**: `pytest-asyncio`, in-memory `:memory:` databases, model fixtures (`make_*()` functions), dependency mocking
- **Prompt tests**: Parametrized across all 8 constants — structure + quality
- **Calibration tests**: Unit tests for Brier score computation, calibration bucketing, weight normalization
- **Repository tests**: `tests/unit/data/` pattern — in-memory DB, seed data, assert on typed models
- **CLI tests**: Mock repository, assert Rich output
- **API tests**: `httpx.AsyncClient` with `TestClient`, mock dependencies
- **Integration**: E2E from prediction → outcome → accuracy report

## Estimated Complexity

**XL (1.5-2 weeks)** — justified by:
- 5 distinct implementation phases with dependencies
- 6 prompt files to extract + 6 agent files to refactor (mechanical but wide surface area)
- New service layer (`accuracy_calibrator.py`) with non-trivial statistics
- 3 new CLI commands + 3 new API endpoints
- New DB migration + ~6 repository methods
- 50+ new tests across prompt regression + calibration + integration
- Auto-tune weight integration into orchestrator (high-stakes code path)

## Files to Create/Modify

| File | Action | Phase |
|------|--------|-------|
| `agents/prompts/bull.py` | CREATE | 1 |
| `agents/prompts/bear.py` | CREATE | 1 |
| `agents/prompts/risk.py` | CREATE | 1 |
| `agents/prompts/volatility.py` | CREATE | 1 |
| `agents/prompts/flow.py` | CREATE | 1 |
| `agents/prompts/fundamental.py` | CREATE | 1 |
| `agents/prompts/__init__.py` | MODIFY | 1 |
| `agents/bull.py` | MODIFY (import) | 1 |
| `agents/bear.py` | MODIFY (import) | 1 |
| `agents/risk.py` | MODIFY (import) | 1 |
| `agents/volatility.py` | MODIFY (import) | 1 |
| `agents/flow_agent.py` | MODIFY (import) | 1 |
| `agents/fundamental_agent.py` | MODIFY (import) | 1 |
| `agents/_parsing.py` | MODIFY (remove RISK_STRATEGY_TREE) | 1 |
| `models/analytics.py` | MODIFY (add 3 models) | 2 |
| `models/config.py` | MODIFY (add auto_tune field) | 2 |
| `data/migrations/026_agent_calibration.sql` | CREATE | 2 |
| `data/repository.py` | MODIFY (add ~6 methods) | 2 |
| `services/accuracy_calibrator.py` | CREATE | 2 |
| `cli/outcomes.py` | MODIFY (add 3 commands) | 2 |
| `api/routes/analytics.py` | MODIFY (add 3 endpoints) | 2 |
| `tests/unit/agents/test_prompt_structure.py` | CREATE | 3 |
| `tests/unit/agents/test_prompt_quality.py` | CREATE | 3 |
| `tests/unit/services/test_accuracy_calibrator.py` | CREATE | 2 |
| `agents/orchestrator.py` | MODIFY (auto-tune injection) | 5 |
