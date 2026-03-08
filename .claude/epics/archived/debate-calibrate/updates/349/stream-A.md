---
task: 349
stream: A
status: complete
commit: fe92e19
created: 2026-03-07T23:15:00Z
---

# Task 349: Agent Prediction Persistence — Complete

## What Was Done

### 1. Migration (`data/migrations/025_agent_predictions.sql`)
- Created `agent_predictions` table with FK to `ai_theses(id)`
- `UNIQUE(debate_id, agent_name)` constraint for idempotency
- Indexes: `idx_ap_debate`, `idx_ap_contract`
- `recommended_contract_id` FK to `recommended_contracts(id)` for future join

### 2. Model (`models/analysis.py`)
- Added `AgentPrediction(BaseModel)` with `frozen=True`
- UTC validator on `created_at` (rejects naive and non-UTC)
- Confidence validator via `validate_unit_interval()` (rejects NaN, Inf, out-of-range)
- `direction: SignalDirection | None = None` (None for risk agent)
- Re-exported from `models/__init__.py`

### 3. Repository (`data/repository.py`)
- Added `save_agent_predictions(predictions: list[AgentPrediction]) -> None`
- Uses `executemany` with `INSERT OR IGNORE` for batch insert + idempotency
- Respects architecture boundary: accepts `list[AgentPrediction]` (from `models/`), not `DebateResult` (from `agents/`)

### 4. Orchestrator Helper (`agents/orchestrator.py`)
- Added `extract_agent_predictions(debate_id, result) -> list[AgentPrediction]`
- Handles all 7 agent response types with different field names:
  - `bull_response`, `bear_response`: `direction` + `confidence`
  - `flow_response`, `fundamental_response`: `direction` + `confidence`
  - `vol_response`: `getattr(direction)` (safe for pre-#348 compatibility) + `confidence`
  - `risk_v2_response`: `direction=None` + `confidence`
  - `contrarian_response`: `dissent_direction` + `dissent_confidence`
- Exported from `agents/__init__.py`

### 5. Wiring — 3 Persistence Sites
- **Orchestrator `_persist_result()`**: Captured `debate_id = await repository.save_debate(...)`, added `save_agent_predictions()` call
- **API single-debate route**: Captured `db_debate_id`, added prediction persistence
- **API batch-debate route**: Added prediction persistence after existing `debate_id` capture

### 6. Tests (23 total)
- **14 model tests** (`test_agent_prediction_model.py`): frozen, UTC, confidence, NaN, Inf, direction optional, JSON roundtrip
- **9 persistence tests** (`test_agent_predictions.py`): migration, indexes, unique constraint, save, idempotent, FK, NULL direction, ISO datetime

## Verification
- `ruff check` + `ruff format`: clean
- `mypy --strict`: passes on all 4 modified source files
- `tests/unit/models/`: 1004 passed
- `tests/unit/data/`: 150 passed
