# Research: agent-calibration

## PRD Summary

Build a closed-loop calibration system that measures per-agent prediction accuracy against
real outcomes, exposes calibration metrics via CLI and API, and auto-adjusts
`AGENT_VOTE_WEIGHTS` based on empirical performance. Leverages existing `AgentPrediction`
(migration 025), `OutcomeCollector`, and `ContractOutcome` infrastructure.

## Relevant Existing Modules

- `models/analysis.py` — `AgentPrediction` model (frozen, lines 816-844): `debate_id`, `agent_name`, `direction: SignalDirection | None`, `confidence: float`, `created_at: datetime`
- `models/analytics.py` — `ContractOutcome`, `RecommendedContract`, 6 analytics result models (all frozen, validated)
- `models/config.py` — `DebateConfig` (22 fields, lines 309-340), nested in `AppSettings`
- `agents/orchestrator.py` — `AGENT_VOTE_WEIGHTS` (line 919), `synthesize_verdict()` (line 1109), `extract_agent_predictions()` (lines 777-834), `_log_odds_pool()` (lines 1013-1075)
- `data/repository.py` — `save_agent_predictions()` (line 349), 6 analytics queries (lines 999-1320), all return typed models
- `data/migrations/` — 25 migrations; latest is `025_agent_predictions.sql`
- `services/outcome_collector.py` — `OutcomeCollector` class, collects T+1/T+5/T+10/T+20 P&L
- `cli/outcomes.py` — `outcomes collect` and `outcomes summary` commands (sync Typer + `asyncio.run()`)
- `api/routes/analytics.py` — 9 existing endpoints, rate-limited 60/min, DI via `Depends(get_repo)`

## Existing Patterns to Reuse

- **Frozen analytics models**: All 6 existing result models in `analytics.py` are `frozen=True` with `math.isfinite()` validators and `field_serializer` for Decimal fields. New models (`AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData`, `AgentWeightsComparison`) follow this pattern.
- **Repository query pattern**: `async with conn.execute(SQL) as cursor: rows = await cursor.fetchall()` → map to typed models. GROUP BY aggregation with optional WHERE clauses for time windows.
- **API endpoint pattern**: `@router.get()` + `@limiter.limit("60/minute")` + `Depends(get_repo)` → return typed model directly (FastAPI auto-serializes).
- **CLI Rich table pattern**: `Table(title=...)`, `add_column(style=...)`, `add_row(...)`, `console.print(table)`. Sync Typer command wrapping `asyncio.run()`.
- **Analytics model export**: All models exported from `models/__init__.py` for top-level import.
- **INSERT OR IGNORE idempotency**: `save_agent_predictions()` uses UNIQUE constraint for dedup.

## Existing Code to Extend

- `models/analytics.py` — Add 4 new frozen models after existing result models (~line 600+)
- `models/config.py` — Add `auto_tune_weights: bool = False` to `DebateConfig`
- `data/repository.py` — Add 4 new query methods after existing analytics queries (~line 1320+)
- `agents/orchestrator.py` — Add `vote_weights: dict[str, float] | None = None` param to `synthesize_verdict()`; load auto-tuned weights in `run_debate()` when config enabled
- `api/routes/analytics.py` — Add 3 new GET endpoints after existing ones (~line 140+)
- `cli/outcomes.py` — Add 3 new subcommands: `agent-accuracy`, `calibration`, `agent-weights`
- `models/__init__.py` — Export new models
- `data/migrations/` — Add `026_agent_accuracy_index.sql` (composite index), `027_auto_tune_weights.sql` (weight history table)

## Database JOIN Path

```
agent_predictions.recommended_contract_id
  → contract_outcomes.recommended_contract_id
```

Direct FK path exists: `agent_predictions` already has `recommended_contract_id` column (migration 025).
For direction accuracy, compare `agent_predictions.direction` against stock price movement from
`contract_outcomes.stock_return_pct` (positive = bullish correct, negative = bearish correct).

Fallback path (if `recommended_contract_id` is NULL on some predictions):
```
agent_predictions.debate_id → ai_theses.id
  → [reconstruct via scan context] → recommended_contracts.id
  → contract_outcomes.recommended_contract_id
```

## Database Schema (Existing)

### agent_predictions (migration 025)
```sql
CREATE TABLE IF NOT EXISTS agent_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id INTEGER NOT NULL REFERENCES ai_theses(id),
    recommended_contract_id INTEGER REFERENCES recommended_contracts(id),
    agent_name TEXT NOT NULL,
    direction TEXT,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(debate_id, agent_name)
);
```

### contract_outcomes (migration 012)
```sql
CREATE TABLE IF NOT EXISTS contract_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommended_contract_id INTEGER NOT NULL REFERENCES recommended_contracts(id),
    exit_stock_price TEXT, exit_contract_mid TEXT, exit_contract_bid TEXT, exit_contract_ask TEXT,
    exit_date TEXT, stock_return_pct REAL, contract_return_pct REAL, is_winner INTEGER,
    holding_days INTEGER, dte_at_exit INTEGER, collection_method TEXT NOT NULL, collected_at TEXT NOT NULL,
    UNIQUE(recommended_contract_id, holding_days)
);
```

## New Migrations Needed

### 026: Composite index for accuracy queries
```sql
CREATE INDEX IF NOT EXISTS idx_ap_name_created ON agent_predictions(agent_name, created_at);
```

### 027: Auto-tune weights history table
```sql
CREATE TABLE IF NOT EXISTS auto_tune_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    manual_weight REAL NOT NULL,
    auto_weight REAL NOT NULL,
    brier_score REAL,
    sample_size INTEGER NOT NULL,
    window_days INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atw_created ON auto_tune_weights(created_at);
```

## AGENT_VOTE_WEIGHTS (Current)

```python
AGENT_VOTE_WEIGHTS: dict[str, float] = {
    "trend": 0.25,
    "volatility": 0.20,
    "flow": 0.20,
    "fundamental": 0.15,
    "contrarian": 0.05,
    "risk": 0.0,  # Advisory-only, does not vote on direction
}
# Sum of directional weights: 0.85 (Bordley 1982 log-odds pooling)
```

## Potential Conflicts

- **None identified**. All changes are additive:
  - New models, new migrations, new queries, new endpoints, new CLI commands
  - `synthesize_verdict()` gets optional `vote_weights` param (backward compatible)
  - `DebateConfig.auto_tune_weights` defaults to `False` (no behavior change)
  - Existing orchestrator tests pass unchanged

## Open Questions

1. ~~**Holding period for accuracy**~~: **Resolved — T+10** (`holding_days=10`) is the canonical holding period for direction accuracy evaluation.
2. **Agent name mapping**: `extract_agent_predictions()` currently uses "bull" for trend output and skips bear (static fallback). The PRD references 6 agents: trend, volatility, flow, fundamental, contrarian, risk. Need to verify the exact `agent_name` values stored in DB match the PRD's expected names.
3. **Weight persistence granularity**: Store one row per agent per computation (as designed in migration 027), or one JSON blob per computation? Per-agent rows are easier to query but more rows.

## Recommended Architecture

```
Wave 1 (Foundation):
  - 4 new Pydantic models in analytics.py
  - Migration 026 (composite index)
  - DebateConfig.auto_tune_weights field

Wave 2 (Repository Queries):
  - get_agent_accuracy(window_days) → list[AgentAccuracyReport]
  - get_agent_calibration(agent_name) → AgentCalibrationData
  - get_auto_tuned_weights(window_days) → list[AgentWeightsComparison]
  - save_auto_tuned_weights(weights) → None

Wave 3 (CLI + API):
  - 3 CLI subcommands under outcomes_app
  - 3 GET API endpoints under /api/analytics/

Wave 4 (Auto-Tune Integration):
  - Migration 027 (auto_tune_weights table)
  - Weight computation function (Brier score → normalized weights)
  - Orchestrator integration (inject weights into synthesize_verdict)
  - agent-weights CLI command

Wave 5 (Tests):
  - ~35+ tests across repository, API, CLI, weight computation
```

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/data/test_agent_predictions.py` (12 tests, async fixtures, in-memory DB), `tests/unit/data/test_analytics_queries.py` (JOIN queries), `tests/unit/api/test_analytics_routes.py` (mock repo via Depends override), `tests/unit/models/test_analytics.py` (frozen model validation)
- **New test files**: `test_agent_accuracy.py` (repository), `test_agent_calibration_routes.py` (API), `test_outcomes_calibration.py` (CLI), `test_weight_computation.py` (unit)
- **Mocking**: `AsyncMock()` for repository in API tests, `Database(":memory:")` for repository tests
- **Fixtures**: `@pytest_asyncio.fixture` for DB setup with seeded predictions + outcomes

## Estimated Complexity

**L (Large)** — 5 waves, 15-18 issues, ~35+ tests

Justification:
- Wave 1 (S): Pure model/config additions, 1 migration
- Wave 2 (L): Complex JOIN queries with time windows, Brier score computation, 10-sample minimum logic
- Wave 3 (M): 6 new interface points (3 CLI + 3 API), following established patterns
- Wave 4 (L): Weight computation algorithm, orchestrator integration with backward compatibility
- Wave 5 (M): Comprehensive test suite for all new paths
