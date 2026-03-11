---
name: self-calibrate
status: backlog
created: 2026-03-11T13:35:15Z
progress: 0%
prd: .claude/prds/self-calibrate.md
github: [Will be updated when synced to GitHub]
---

# Epic: Self-Calibrating Fill Model

## Overview

Wire three disconnected pieces of existing infrastructure into a self-improving feedback loop: (1) replace mid-to-mid P&L with realistic ask-entry/bid-exit fills, (2) grade agents on contract profitability instead of stock direction, (3) enable auto-tune by default with an automatic trigger after outcome collection. No new modules, no schema migrations, no model changes — all required fields and tables already exist. The main architectural challenge is the `services/ → agents/` import boundary, resolved via DI callable injection.

## Architecture Decisions

- **DI callable for auto-tune trigger**: `OutcomeCollector.__init__()` accepts an optional `auto_tune_fn: Callable[..., Awaitable[list[Any]]] | None = None`. The CLI/API layer wires `auto_tune_weights` from `agents/orchestrator.py` at construction time. This preserves the `services/ cannot import agents/` boundary.
- **No retroactive recomputation**: Legacy outcomes keep their mid-price P&L. The 90-day auto-tune window ages out old data naturally.
- **Contract profitability as ground truth**: Replace all `stock_return_pct` references with `contract_return_pct > 0` in accuracy/calibration queries. Direction distinction (bullish vs bearish) is removed — only contract profitability matters.
- **Post-normalization degenerate weight guard**: If any auto-tuned weight exceeds 0.50 after normalization, revert to static `AGENT_VOTE_WEIGHTS` and log a warning (PRD safety requirement).

## Technical Approach

### FR-1: Realistic Fill Pricing (outcome_collector.py)

Modify `_process_active_contract()` (lines 307-317) to use ask-entry/bid-exit:
- Entry fill: `contract.ask` (from `RecommendedContract.ask`, type `Decimal`)
- Exit fill: `matching.bid` (from live option chain)
- Fallback chain: if `contract.ask` is `None`/zero → `contract.entry_mid`; if `matching.bid` is `None` → `exit_contract_mid`
- `_compute_contract_return()` (expired ITM path) is UNCHANGED — intrinsic value is not subject to spread
- `is_winner` follows the realistic fill result

### FR-2: Contract-Level Accuracy (data/_debate.py)

- `get_agent_accuracy()`: Replace 6 `stock_return_pct` references with `contract_return_pct > 0` / `contract_return_pct IS NOT NULL`. Update `HAVING COUNT(*) >= 10` → `>= 30`. Add `co.contract_return_pct IS NOT NULL` to WHERE clause.
- `get_agent_calibration()`: Same changes — swap `stock_return_pct` direction logic for `contract_return_pct > 0`. Both queries must be updated atomically for consistency.

### FR-3: Auto-Tune Default On + Auto-Trigger

- `models/config.py`: `DebateConfig.auto_tune_weights` default `False` → `True`
- `agents/orchestrator.py`:
  - `compute_auto_tune_weights()`: threshold 10 → 30 (line 945)
  - `auto_tune_weights()`: threshold 10 → 30 (line 997)
  - Add post-normalization degenerate weight guard in `compute_auto_tune_weights()`
  - `run_debate()`: Log per-agent weights when auto-tuned (lines 1458-1467)
- `services/outcome_collector.py`:
  - Add `auto_tune_fn` parameter to `__init__()` with DI pattern
  - Call `auto_tune_fn` in `run_scheduler()` after successful `collect_outcomes()`
  - Exception in auto-tune logged, never crashes scheduler

## Implementation Strategy

Three tasks executed sequentially — each is a focused change to 1-2 files:

1. **Realistic fills** — `outcome_collector.py` P&L formula + tests
2. **Contract accuracy + auto-tune config** — `_debate.py` SQL queries + `config.py` default + `orchestrator.py` thresholds/guard/logging + tests
3. **Auto-tune trigger wiring** — `outcome_collector.py` DI param + `run_scheduler()` hook + CLI/API wiring + tests

## Task Breakdown Preview

- [ ] Task 1: Realistic fill pricing — modify `_process_active_contract()` with ask/bid fills and fallback chain, add unit tests
- [ ] Task 2: Contract-level accuracy — update `get_agent_accuracy()` and `get_agent_calibration()` SQL to use `contract_return_pct`, change HAVING to 30, add `IS NOT NULL` filter, add unit tests
- [ ] Task 3: Auto-tune config + thresholds — flip `auto_tune_weights` default to True, change sample thresholds to 30, add degenerate weight guard, add per-agent weight logging in `run_debate()`, add unit tests
- [ ] Task 4: Auto-tune trigger wiring — add `auto_tune_fn` DI param to `OutcomeCollector`, call in `run_scheduler()`, wire from CLI/API layer, add unit tests

## Dependencies

- **Internal**: `RecommendedContract.ask` (Decimal field, already persisted), `ContractOutcome.exit_contract_bid` (Decimal|None, already persisted), `auto_tune_weights` table (already exists), `AgentAccuracyReport`/`AgentWeightsComparison` models (already defined)
- **External**: None — all data sources already in use
- **Data prerequisite**: 30+ graded outcomes per agent before auto-tune activates. New users get static weights silently.

## Success Criteria (Technical)

- P&L calculation uses `(exit_bid - entry_ask) / entry_ask * 100` for active contracts with proper fallback chain
- `get_agent_accuracy()` and `get_agent_calibration()` grade on `contract_return_pct > 0`
- Auto-tune activates by default; triggered automatically after outcome collection
- Degenerate weight guard (>0.50) reverts to static weights
- Per-agent weight values logged at debate start
- All existing tests pass; new tests cover fill formula, accuracy queries, auto-tune trigger
- No new modules, no schema migrations, no model changes

## Estimated Effort

- **Size**: S (Small) — 4 tasks, ~6 files modified, all targeted changes to existing logic
- **Risk**: Low — infrastructure fully in place, this is a wiring job
- **Critical path**: Architecture boundary (DI callable) is the only non-trivial design element
