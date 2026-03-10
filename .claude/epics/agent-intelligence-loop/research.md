# Research: agent-intelligence-loop

## PRD Summary

Two complementary improvements to make the debate system self-improving:
1. **Complete FinancialDatasets wiring** — close 6 open FD issues (#394-#399, epic #390)
2. **Activate auto-tune weights** — CLI command + API endpoint to compute, persist, and apply auto-tuned agent vote weights from outcome accuracy data

## Critical PRD Corrections

Research revealed several PRD assumptions are inaccurate. These must be corrected before decomposition:

| PRD Claim | Actual Finding | Impact |
|-----------|---------------|--------|
| "Scan pipeline runs batch debates via `run_debate()`" | Scan pipeline does NOT invoke debates. It only scores tickers + selects contracts. Debates are separate CLI/API invocations. | **FD scan wiring gap is a misunderstanding** — batch debates via CLI (`_debate_batch_async`) and API already wire `fd_svc` correctly |
| FR4: "Modify `run_debate()` to load persisted weights" | Already implemented at `orchestrator.py:1373-1382` — loads `get_latest_auto_tune_weights()` when `config.auto_tune_weights=True` | **FR4 is already done** |
| FR3: "New migration 030: `tuned_weights` table" | Migration 028 already created `auto_tune_weights` table with row-per-agent schema. `save_auto_tune_weights()` and `get_latest_auto_tune_weights()` already exist in `_debate.py` | **No new migration needed** |
| "`get_auto_tune_comparison()` at `_debate.py:395`" | Method does NOT exist. What exists is `get_latest_auto_tune_weights()` at line 393 | **Comparison logic must be built from existing primitives** |
| "`DebateConfig.auto_tune_weights` needs adding" | Already exists in `config.py:341` as `auto_tune_weights: bool = False` | **Config already done** |

## Actual Gaps (What Truly Needs Building)

### Gap 1: `auto-tune` CLI Subcommand (PRIMARY)
- `outcomes auto-tune [--dry-run] [--window 90]` does not exist
- Must call `compute_auto_tune_weights()` + `save_auto_tune_weights()`
- The computation function and persistence methods exist but nothing connects them
- `compute_auto_tune_weights()` in `orchestrator.py:912` is dead code in production

### Gap 2: Auto-Tune API Endpoints
- `POST /api/analytics/weights/auto-tune` — trigger computation + persist
- `GET /api/analytics/weights/history` — weight snapshots over time
- Neither endpoint exists

### Gap 3: FD Issue Closure
- Issues #394-#399 and epic #390 reference work that appears already implemented
- Need verification pass + close with "implemented in prior work" comments

### Gap 4: Tests
- New tests for `auto-tune` CLI subcommand
- New tests for auto-tune API endpoints
- Integration test for full round-trip: compute → persist → load in debate

## Relevant Existing Modules

- `agents/orchestrator.py` — `compute_auto_tune_weights()` (line 912), `run_debate()` (line 1280), `AGENT_VOTE_WEIGHTS` (line 902), auto-tune loading (lines 1373-1382)
- `data/_debate.py` — `get_agent_accuracy()` (line 234), `get_latest_auto_tune_weights()` (line 393), `save_auto_tune_weights()` (line 432)
- `cli/outcomes.py` — existing subcommands: collect, summary, agent-accuracy, calibration, agent-weights, backtest, equity-curve
- `api/routes/analytics.py` — 12 existing endpoints including `GET /agent-weights`
- `models/analytics.py` — `AgentWeightsComparison` (line 773), `AgentAccuracyReport` (line 654)
- `models/config.py` — `DebateConfig.auto_tune_weights: bool = False` (line 341), `FinancialDatasetsConfig` (line 526)
- `services/financial_datasets.py` — `FinancialDatasetsService.fetch_package()` (returns `FinancialDatasetsPackage | None`)
- `data/migrations/028_auto_tune_weights.sql` — table already exists

## Existing Patterns to Reuse

### CLI Subcommand Pattern (from `outcomes.py`)
```python
@outcomes_app.command()
def auto_tune(
    dry_run: bool = typer.Option(False, "--dry-run", help="..."),
    window: int = typer.Option(90, "--window", help="..."),
) -> None:
    asyncio.run(_auto_tune_async(dry_run, window))
```

### API Endpoint Pattern (from `analytics.py`)
```python
@router.post("/weights/auto-tune")
async def trigger_auto_tune(
    repo: Repository = Depends(get_repo),
    window: int = Query(90, ge=1),
    dry_run: bool = Query(False),
) -> list[AgentWeightsComparison]:
```

### Auto-Tune Flow Pattern (connect existing pieces)
```python
accuracy = await repo.get_agent_accuracy(window_days=window)
tuned = compute_auto_tune_weights(accuracy)  # orchestrator.py:912
comparisons = [
    AgentWeightsComparison(
        agent_name=name,
        manual_weight=AGENT_VOTE_WEIGHTS.get(name, 0.0),
        auto_weight=tuned.get(name, 0.0),
        brier_score=next((a.brier_score for a in accuracy if a.agent_name == name), None),
        sample_size=next((a.sample_size for a in accuracy if a.agent_name == name), 0),
    )
    for name in tuned
]
if not dry_run:
    await repo.save_auto_tune_weights(comparisons, window_days=window)
```

## Existing Code to Extend

| File | What Exists | What Needs Adding |
|------|------------|-------------------|
| `cli/outcomes.py` | 7 subcommands | `auto-tune` subcommand (~40 lines) |
| `api/routes/analytics.py` | 12 endpoints | `POST /weights/auto-tune`, `GET /weights/history` (~30 lines) |

## Files NOT Modified (Confirmed Complete)

- `models/financial_datasets.py` — FDPackage model complete (173 lines)
- `services/financial_datasets.py` — service complete (344 lines)
- `agents/orchestrator.py` — `compute_auto_tune_weights()` + auto-tune loading in `run_debate()` both complete
- `data/_debate.py` — persistence methods complete
- `models/analytics.py` — `AgentWeightsComparison` + `AgentAccuracyReport` complete
- `models/config.py` — `DebateConfig.auto_tune_weights` + `FinancialDatasetsConfig` complete
- `data/migrations/028_auto_tune_weights.sql` — table exists
- `scan/` — no changes needed (scan doesn't debate)

## Potential Conflicts

- **PRD scope mismatch**: PRD describes 9 issues across 3 waves but research shows ~50% is already implemented. Epic decomposition must account for this to avoid creating issues for completed work.
- **`get_auto_tune_comparison()` pseudocode**: PRD references a method that doesn't exist. The comparison must be constructed inline from `get_agent_accuracy()` + `compute_auto_tune_weights()` + `AGENT_VOTE_WEIGHTS`.

## Open Questions — RESOLVED

1. **FD scan enrichment**: CONFIRMED NO GAP. `_scan_async()` in CLI renders results table and exits — zero debate calls. API scan route only runs `OutcomeCollector` after scan. `POST /api/debate/batch` accepts `scan_id` but is a separate user-initiated call that already wires `fd_svc`. No scan-to-auto-debate flow exists.
2. **Weight history schema**: `WeightSnapshot` model wrapping `computed_at`, `window_days`, `list[AgentWeightsComparison]`. Query groups `auto_tune_weights` rows by `created_at` DESC, limits to N snapshots.
3. **Web UI scope**: ADDED. New "Weight Tuning" tab on AnalyticsPage with current weights table, Auto-Tune trigger button, and weight evolution line chart (Chart.js via PrimeVue `Chart`).

## Recommended Architecture

Given that most infrastructure exists, the epic reduces to:

**Wave 1: Verify + Close FD Issues** (S — 1-2 hours)
- Verify #394-#399 are implemented, close with comments, close epic #390

**Wave 2: Auto-Tune CLI + API** (M — half day)
- `outcomes auto-tune` CLI subcommand connecting existing primitives
- `POST /api/analytics/weights/auto-tune` API endpoint
- `GET /api/analytics/weights/history` API endpoint
- Tests for all new code

**No Wave 3 needed** — FR4 (debate weight loading) is already done.

## Test Strategy Preview

- Existing test patterns: `tests/unit/agents/test_weight_computation.py` (9 tests), `tests/integration/test_calibration_pipeline.py` (6 tests)
- CLI test pattern: mock `Repository` methods, verify Rich table output
- API test pattern: `TestClient` with mocked dependencies via `app.dependency_overrides`
- Integration: round-trip test — compute → persist → load → verify in debate config

## Estimated Complexity

**M (Medium)** — significantly smaller than the PRD's L estimate because:
- ~50% of the work described in the PRD is already implemented
- No new models, services, or migrations needed
- Core implementation is connecting existing pieces + adding 2 thin entry points (CLI + API)
- FD scan wiring appears to be a non-issue
- ~15-20 new tests, not 30+
