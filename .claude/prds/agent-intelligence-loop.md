---
name: agent-intelligence-loop
description: Wire FinancialDatasets into scan pipeline debates + activate auto-tune agent weights from outcome accuracy data
status: planned
created: 2026-03-10T22:00:00Z
effort: L
---

# PRD: agent-intelligence-loop

## Executive Summary

Two complementary improvements that make the debate system self-improving:

1. **Complete FinancialDatasets wiring**: The service, models, context rendering, and
   single-debate paths all exist. The gap is the **scan pipeline** — when `options-arena scan`
   runs batch debates, it never fetches FD data. Fix this and close the 6 open FD issues.

2. **Activate auto-tune weights**: `compute_auto_tune_weights()` already exists in the
   orchestrator (inverse Brier score, clamped [0.05, 0.35], normalized to sum=0.85).
   `get_agent_accuracy()` already queries outcome data. But nothing **calls** these together —
   the debate always uses hardcoded `AGENT_VOTE_WEIGHTS`. Wire a scheduler + CLI command
   to compute, persist, and apply auto-tuned weights.

These combine naturally: richer fundamental data → better agent predictions → faster
accuracy convergence → better auto-tuned weights → better predictions (feedback loop).

## Problem Statement

### Gap 1: FD Enrichment Missing in Scan Pipeline

The scan pipeline (`scan/pipeline.py` → phase modules) runs batch debates via
`run_debate()` but never constructs a `FinancialDatasetsService` or passes `fd_package`.
Agents in scan-triggered debates receive no P/E, revenue, earnings, or margin data —
only yfinance-sourced fundamentals (which are sparser and less reliable).

**Evidence:**
- `grep -r "fd_package\|financial_datasets" src/options_arena/scan/` → no matches
- `cli/commands.py:787-789` correctly wires FD for single debates
- `api/routes/debate.py:189-191` correctly wires FD for API debates
- Scan pipeline is the only debate entry point without FD enrichment

### Gap 2: Auto-Tune Weights Exist But Are Never Activated

- `orchestrator.py:912` — `compute_auto_tune_weights()` is fully implemented
- `orchestrator.py:1163` — `synthesize_verdict()` accepts `vote_weights` param
- `_debate.py:234` — `get_agent_accuracy()` returns `AgentAccuracyReport` per agent
- `_debate.py:395` — `get_auto_tune_comparison()` computes manual vs tuned weights
- `models/analytics.py:773` — `AgentWeightsComparison` model exists

**But**: No code path ever calls `compute_auto_tune_weights()` and passes the result
to `synthesize_verdict()`. The function exists but is dead code in production.

### Gap 3: No Weight Persistence or Visibility

Auto-tuned weights are computed ephemerally — no SQLite storage, no CLI visibility,
no way to compare manual vs tuned over time. The API endpoint
`/api/analytics/accuracy` exists but `/api/analytics/weights` only shows a snapshot
comparison, not a time series.

## User Stories

### US1: Scan debates get fundamental enrichment
**As** a user running `options-arena scan --sector technology`,
**I want** scan-triggered debates to include P/E, revenue, and margin data,
**So that** the fundamental agent's output is as rich as single-ticker debates.

**Acceptance criteria:**
- Scan pipeline constructs `FinancialDatasetsService` alongside other services
- Each scan debate calls `fd_svc.fetch_package(ticker)` with per-ticker error isolation
- FD fetch failures don't crash the scan (never-raises contract)
- Fundamental agent context includes income/balance sheet data when available
- `MarketContext.financial_datasets_ratio()` reflects FD enrichment in scan results

### US2: Debate weights auto-tune from outcomes
**As** a power user with 50+ collected outcomes,
**I want** agent vote weights to reflect actual prediction accuracy,
**So that** agents with better track records get more influence on verdicts.

**Acceptance criteria:**
- `options-arena outcomes auto-tune` computes and persists tuned weights
- `options-arena outcomes auto-tune --dry-run` shows comparison without applying
- Agents with <10 samples keep manual baseline weights (existing guard)
- Tuned weights are clamped to [0.05, 0.35] per agent (existing guard)
- Risk agent always gets weight 0.0 (advisory-only, existing guard)
- Next `run_debate()` call uses persisted tuned weights (if available)

### US3: Weight comparison visibility
**As** a developer evaluating agent performance,
**I want** to compare manual vs auto-tuned weights with Brier scores,
**So that** I can validate whether auto-tuning improves prediction quality.

**Acceptance criteria:**
- CLI `outcomes auto-tune` prints a Rich table: agent | manual | tuned | brier | samples
- API `/api/analytics/weights/history` returns weight snapshots over time
- Web UI analytics tab shows weight comparison chart

## Requirements

### Functional Requirements

#### FR1: Scan Pipeline FD Wiring

Wire `FinancialDatasetsService` into the scan pipeline's debate phase. The service
is already constructed in `cli/commands.py` for single debates — replicate this pattern
in the scan pipeline entry point.

**Implementation approach:**
- Scan pipeline's debate orchestration (in `phase_persist.py` or the debate-triggering
  code) receives `FinancialDatasetsService` via DI from the CLI/API caller
- Per-ticker: `fd_package = await fd_svc.fetch_package(ticker)` with `return_exceptions=True`
- Pass `fd_package` to `run_debate()` — same parameter that single debates already use
- On FD fetch failure: `fd_package=None` (debate proceeds without FD data, as it does today)

**Key constraint**: FD fetches add latency. For batch scans with 50+ tickers, use
`asyncio.gather` batching or sequential-with-timeout to avoid overwhelming the API.
The service's internal rate limiter handles per-request throttling.

#### FR2: Auto-Tune Weight Computation Trigger

Create a CLI command and a programmatic API to trigger weight computation:

```python
# CLI: options-arena outcomes auto-tune [--dry-run] [--window 90]
# API: POST /api/analytics/weights/auto-tune

async def auto_tune_weights(
    repo: Repository,
    window: int = 90,
    min_samples: int = 10,
    dry_run: bool = False,
) -> list[AgentWeightsComparison]:
    """Compute auto-tuned weights from outcome accuracy data."""
    accuracy = await repo.get_agent_accuracy(window)
    tuned = compute_auto_tune_weights(accuracy)  # already exists
    comparison = await repo.get_auto_tune_comparison(window)  # already exists
    if not dry_run:
        await repo.persist_tuned_weights(tuned, window)
    return comparison
```

#### FR3: Weight Persistence (New Migration)

New SQLite table `tuned_weights` to store weight snapshots:

```sql
CREATE TABLE tuned_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at TEXT NOT NULL,          -- ISO 8601 UTC
    window_days INTEGER NOT NULL,       -- lookback window used
    sample_size INTEGER NOT NULL,       -- total outcomes used
    weights_json TEXT NOT NULL,         -- JSON: {"trend": 0.28, "volatility": 0.22, ...}
    is_active INTEGER NOT NULL DEFAULT 0  -- 1 = currently applied
);
```

Only one row has `is_active = 1` at a time. `persist_tuned_weights()` sets prior
active row to 0 and inserts new row with `is_active = 1`.

#### FR4: Debate Weight Loading

Modify `run_debate()` to optionally load persisted tuned weights:

```python
# In orchestrator.py — run_debate() preamble
if vote_weights is None and repository is not None:
    persisted = await repository.get_active_tuned_weights()
    if persisted is not None:
        vote_weights = persisted
# Falls back to AGENT_VOTE_WEIGHTS if no persisted weights
```

This is opt-in: if no tuned weights are persisted, behavior is unchanged.

#### FR5: Close FD Epic Issues (#390-#399)

Verify each open issue against the existing codebase and close those already implemented:

| Issue | Title | Status |
|-------|-------|--------|
| #394 | Models + Config | Code exists: `models/financial_datasets.py` (173 lines) |
| #395 | FinancialDatasetsService | Code exists: `services/financial_datasets.py` (344 lines) |
| #396 | MarketContext extension — 16 fd_* fields | Code exists: `models/analysis.py` (16 fd_* fields) |
| #397 | Context rendering + Fundamental agent prompt v3.0 | Code exists: `_parsing.py:617-670` |
| #398 | Integration wiring — orchestrator, API, CLI, health | Code exists across 4 files |
| #399 | Comprehensive test suite | Tests exist: 998 lines across 2 files |

**Action**: Verify each, close with "implemented in prior work" comment, close epic #390.

### Non-Functional Requirements

#### NFR1: Scan Latency Budget
- FD fetch per ticker: <2s (service has 10s timeout, typically <1s)
- 50-ticker scan with FD: <5min total (sequential FD fetches with rate limiting)
- FD failures must not increase scan duration (timeout + move on)

#### NFR2: Auto-Tune Safety
- Minimum 10 samples per agent before tuning (existing guard in `compute_auto_tune_weights`)
- Weight clamp [0.05, 0.35] prevents any agent from dominating (existing guard)
- `--dry-run` flag for safe preview before activation
- Manual `AGENT_VOTE_WEIGHTS` always available as reset baseline

#### NFR3: Backward Compatibility
- Debates without persisted weights behave identically to today
- Scan pipeline without FD API key skips FD enrichment silently
- All existing tests pass without modification

## Detailed Design

### Component Flow

```
Scan Pipeline (batch debates)
    │
    ├── [NEW] Construct FinancialDatasetsService
    ├── Per ticker:
    │   ├── [NEW] fd_package = await fd_svc.fetch_package(ticker)
    │   └── run_debate(..., fd_package=fd_package)
    │       └── build_market_context() populates fd_* fields
    │           └── render_fundamental_context() renders for agent
    │
Outcome Collection (existing)
    │
    ├── OutcomeCollector fetches T+1/T+5/T+10/T+20 prices
    └── Persists P&L per contract + agent predictions
    │
Auto-Tune Trigger (NEW)
    │
    ├── CLI: outcomes auto-tune [--dry-run] [--window 90]
    ├── get_agent_accuracy(window) → AgentAccuracyReport per agent
    ├── compute_auto_tune_weights(accuracy) → dict[str, float]
    ├── persist_tuned_weights(weights) → SQLite tuned_weights table
    └── Next run_debate() loads active weights automatically
```

### Files Modified

| File | Change | Size |
|------|--------|------|
| `scan/phase_persist.py` or debate caller | Wire FD service + per-ticker fetch | ~15 lines |
| `cli/commands.py` (scan command) | Pass FD service to scan pipeline | ~5 lines |
| `api/app.py` | Ensure FD service on `app.state` (may already exist) | ~3 lines |
| `data/_debate.py` | Add `persist_tuned_weights()`, `get_active_tuned_weights()` | ~40 lines |
| `data/migrations/030_tuned_weights.sql` | New table | ~10 lines |
| `agents/orchestrator.py` | Load persisted weights in `run_debate()` | ~8 lines |
| `cli/outcomes.py` | New `auto-tune` subcommand | ~40 lines |
| `api/routes/analytics.py` | POST endpoint for auto-tune trigger | ~15 lines |

### Files NOT Modified

- `models/financial_datasets.py` — already complete
- `services/financial_datasets.py` — already complete
- `agents/_parsing.py` — context rendering already handles fd_* fields
- `agents/fundamental_agent.py` — already receives rendered FD context
- `models/analytics.py` — `AgentWeightsComparison` already exists

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Scan debate FD enrichment | fd_* fields populated when API key present | `MarketContext.financial_datasets_ratio() > 0` in scan debates |
| Scan without API key | Unchanged behavior, no errors | `options-arena scan` with no FD key succeeds |
| Auto-tune produces valid weights | Weights sum to 0.85, each in [0.05, 0.35] | Unit test on `auto_tune_weights()` |
| Weight persistence round-trip | Persisted weights load correctly in next debate | Integration test |
| FD issues closed | #390, #394-#399 closed | `gh issue list --label epic:financialdatasets-ai` empty |
| Existing tests pass | Zero regressions | `uv run pytest tests/ -n auto -q` |
| New test coverage | 30+ tests (FD scan wiring + auto-tune + persistence) | Test count |

## Constraints & Assumptions

- **FinancialDatasets API key**: Optional. Scan pipeline gracefully degrades without it.
- **Outcome data volume**: Auto-tune is most useful with 50+ outcomes. Below that threshold,
  most agents keep manual weights (the <10 sample guard). PRD does not add an auto-scheduler —
  user triggers manually via CLI when they have enough data.
- **Single active weight set**: Only one set of tuned weights is active at a time. No
  per-ticker or per-sector weight specialization (future work).
- **No prompt changes**: Fundamental agent prompt is already v3.0 with FD context rendering.
  This PRD only wires data through; no prompt redesign needed.

## Out of Scope

- **Per-sector weight tuning** — would require sector-stratified accuracy data (insufficient samples)
- **Automatic auto-tune scheduling** — manual trigger only; future work for a cron/scheduler
- **Weight A/B testing** — comparing tuned vs manual in parallel debates (future work)
- **New FD data sources** — PRD uses existing `fetch_package()` (metrics + income + balance sheet)
- **Frontend weight management UI** — API endpoints only; web UI deferred

## Dependencies

### Internal
- `compute_auto_tune_weights()` — already implemented in `orchestrator.py:912`
- `get_agent_accuracy()` — already implemented in `_debate.py:234`
- `get_auto_tune_comparison()` — already implemented in `_debate.py:395`
- `FinancialDatasetsService.fetch_package()` — already implemented in `services/financial_datasets.py:256`
- Outcome collection pipeline — already ships outcomes to DB (migration 029)

### External
- Financial Datasets API (optional, degraded without it)

## Implementation Phases

### Wave 1: FD Scan Wiring + Epic Closure (3 issues)
1. **Wire FD service into scan pipeline** — construct service, per-ticker fetch, pass to debate
2. **Verify and close FD issues #394-#399 and epic #390** — confirm each is implemented, close
3. **Tests for scan FD wiring** — mock FD service, verify context populated in scan debates

### Wave 2: Auto-Tune Activation (4 issues)
4. **Migration 030: tuned_weights table** — schema + Repository methods
5. **`auto_tune_weights()` function + persistence** — in `data/_debate.py`
6. **Load active weights in `run_debate()`** — orchestrator preamble change
7. **CLI `outcomes auto-tune` subcommand** — with `--dry-run` and `--window` flags

### Wave 3: API + Visibility (2 issues)
8. **API endpoint POST `/api/analytics/weights/auto-tune`** — trigger + response
9. **API endpoint GET `/api/analytics/weights/history`** — weight snapshots over time

## Effort Estimate

**Total: L (3-4 days)**
- Wave 1: S (3-4 hours) — mostly wiring + verification
- Wave 2: M (1-1.5 days) — migration, persistence, orchestrator change, CLI
- Wave 3: S (3-4 hours) — 2 API endpoints
