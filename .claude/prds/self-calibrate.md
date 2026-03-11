---
name: self-calibrate
description: Self-calibrating feedback loop — realistic fills, contract-level accuracy, and auto-triggered weight adaptation
status: planned
created: 2026-03-11T02:28:44Z
---

# PRD: Self-Calibrating Fill Model

## Executive Summary

Adapt NautilusTrader's core philosophy — **the backtest must match reality** — into a
self-improving feedback loop for Options Arena. Three precise changes connect existing
but disconnected infrastructure: realistic fill pricing, contract-level accuracy grading,
and auto-triggered weight recalibration. The system gets better at recommending options
the more it's used.

## Problem Statement

Options Arena's analysis-to-outcome pipeline has a compounding accuracy problem:

1. **P&L is fiction.** All backtesting uses `mid = (bid + ask) / 2` for entry and exit.
   Real traders pay the ask and sell at the bid. On a contract with 20% spread, mid-to-mid
   shows +10% when the real round-trip is -10%. Every performance number is systematically
   overstated, making it impossible to know which recommendations actually work.

2. **Agent grading measures the wrong thing.** The auto-tune system grades agents on whether
   the *stock* moved in the predicted direction (`stock_return_pct > 0`). But agents recommend
   *option contracts*, not stocks. An agent can correctly call direction and still lose money
   due to IV crush, theta decay, or poor strike selection. The feedback signal is disconnected
   from the outcome that matters.

3. **The calibration loop is dead.** `auto_tune_weights()` exists but: (a) defaults to off
   (`DebateConfig.auto_tune_weights = False`), (b) is never automatically triggered, and
   (c) uses the wrong ground truth per item 2. The system never learns.

These three issues compound: inaccurate P&L → wrong accuracy grades → stale weights → no
improvement. Fixing any one alone has limited value. Fixing all three creates a virtuous cycle.

## User Stories

### Primary User: Discretionary Options Trader

**US-1: Honest backtesting**
> As a trader reviewing my scan history, I want P&L numbers that reflect what I would
> actually experience including spread costs, so I can trust the system's track record.

Acceptance criteria:
- P&L uses entry `ask` (for long entry) and exit `bid` (for long exit)
- Existing outcome data is not retroactively changed — new formula applies to newly collected outcomes
- `options-arena outcomes summary` and `outcomes backtest` reflect realistic fills
- API analytics endpoints return realistic P&L

**US-2: Smart agent weighting**
> As a trader running debates, I want the system to automatically weight agents based on
> which ones have historically produced profitable contract recommendations, not just
> directional calls.

Acceptance criteria:
- Auto-tune uses `contract_return_pct` as ground truth instead of `stock_return_pct`
- Auto-tune activates by default (no opt-in required)
- Minimum 30 graded outcomes per agent before overriding static weights
- Effective weights are logged at debate start so user can see adaptation
- `options-arena outcomes summary` shows per-agent contract-level accuracy

**US-3: Automatic recalibration**
> As a trader who runs scans regularly, I want agent weights to update automatically as
> outcomes accumulate, without me remembering to trigger anything.

Acceptance criteria:
- After each outcome collection cycle, auto-tune is triggered if sample threshold is met
- Weights are persisted to `auto_tune_weights` table
- Next debate automatically picks up the latest weights
- If insufficient data, static weights are used silently (no error)

## Requirements

### Functional Requirements

#### FR-1: Realistic Fill Pricing

**Current state:** `outcome_collector.py:311-316` computes `contract_return_pct` as
`(exit_contract_mid - entry_mid) / entry_mid * 100`.

**Change:** Replace with `(exit_contract_bid - entry_ask) / entry_ask * 100` for long
positions. Entry ask = `RecommendedContract.ask`. Exit bid = `ContractOutcome.exit_contract_bid`.

Guard conditions:
- If `exit_contract_bid` is `None` (legacy data), fall back to `exit_contract_mid`
- If `RecommendedContract.ask` is zero or `None`, fall back to `entry_mid`
- Expired ITM: continue using intrinsic value (exercise is not subject to spread)
- Expired OTM: continue using -100% (correct as-is)

Files:
- `src/options_arena/services/outcome_collector.py` — `_process_active_contract()`, `_compute_contract_return()`

#### FR-2: Contract-Level Accuracy Ground Truth

**Current state:** `data/_debate.py:260-332` grades agents via SQL using
`co.stock_return_pct > 0` for bullish and `< 0` for bearish.

**Change:** Replace ground truth with `co.contract_return_pct > 0` — did the recommended
contract actually make money?

Brier score formula stays the same: `(confidence - outcome)^2` where outcome is now 1.0
when the contract was profitable and 0.0 when it wasn't.

Files:
- `src/options_arena/data/_debate.py` — `get_agent_accuracy()` query

#### FR-3: Auto-Tune Default On + Auto-Trigger

**Current state:** `DebateConfig.auto_tune_weights = False`. `auto_tune_weights()` is
never called automatically. `OutcomeCollector.run_scheduler()` collects outcomes then
loops back to sleep with no hook.

**Changes:**
1. Default `auto_tune_weights` to `True` in `models/config.py:341`
2. Raise minimum sample threshold from 10 to 30 in `compute_auto_tune_weights()`
3. Add auto-tune trigger in `outcome_collector.py` after `collect_outcomes()` returns,
   inside `run_scheduler()` (after line 487)
4. Log effective weights at debate start in `run_debate()` when auto-tuned weights are loaded

Auto-tune trigger pseudocode:
```python
outcomes = await self.collect_outcomes()
logger.info("Scheduled outcome collection complete: %d outcomes", len(outcomes))
if outcomes and self._repo:
    try:
        comparisons = await auto_tune_weights(self._repo, window_days=90)
        if comparisons:
            logger.info("Auto-tune weights updated: %d agents recalibrated", len(comparisons))
    except Exception:
        logger.exception("Auto-tune failed, will retry next cycle")
```

Files:
- `src/options_arena/models/config.py` — `DebateConfig.auto_tune_weights` default
- `src/options_arena/agents/orchestrator.py` — `compute_auto_tune_weights()` threshold, `run_debate()` logging
- `src/options_arena/services/outcome_collector.py` — `run_scheduler()` hook

### Non-Functional Requirements

- **Backwards compatibility:** Legacy outcome data (collected with mid pricing) is not
  retroactively recomputed. The new formula applies only to newly collected outcomes.
  Auto-tune may use a mix of old and new P&L data until old data ages out of the 90-day window.
- **Performance:** Auto-tune adds one SQL query (~10ms) per collection cycle. No impact
  on debate latency.
- **Safety:** If auto-tune produces degenerate weights (any agent > 0.50), fall back to
  static weights and log a warning.
- **Observability:** Log auto-tune activation, per-agent weight changes, and whether
  static or adaptive weights are used for each debate.

## Success Criteria

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Backtest mean return | Overstated (mid-mid) | 5-15% lower (honest) | `outcomes backtest` before/after |
| Agent accuracy correlation | Stock direction | Contract profitability | Compare hit rates on both metrics |
| Auto-tune activation | Never (manual only) | Automatic after 30+ outcomes | Check `auto_tune_weights` table |
| Weight adaptation | Static forever | Measurably different from defaults after 50+ debates | Log comparison |

## Constraints & Assumptions

- **Assumes long-only positions.** Options Arena currently only recommends buying calls/puts,
  not selling. If short positions are added later, the fill model reverses (sell at bid to
  open, buy at ask to close).
- **Assumes holding_days=10 for accuracy grading.** The current query filters on
  `co.holding_days = 10`. This is retained — 10 trading days is a reasonable horizon for
  the options being recommended (typically 20-45 DTE).
- **No retroactive recomputation.** Old outcomes keep their mid-price P&L. The 90-day
  auto-tune window means old data ages out naturally.

## Out of Scope

- **Portfolio-level awareness** — tracking open positions, concentration analysis, correlated
  risk. Separate epic.
- **Data staleness enforcement** — gating debates on data freshness. Separate issue.
- **Execution cost display in CLI/UI** — showing expected spread cost per contract. Natural
  follow-up but not part of this feedback loop.
- **Short position fill modeling** — covered/naked writes. Not currently supported by OA.
- **Multi-timeframe accuracy** — grading at T+1, T+5, T+20 in addition to T+10. Future
  enhancement.
- **Configurable fill model toggle** — no mid/realistic switch. Realistic fills only.

## Dependencies

- **Internal:** Existing outcome collection pipeline (`OutcomeCollector`), auto-tune
  infrastructure (`auto_tune_weights()`, `compute_auto_tune_weights()`), agent accuracy
  query (`get_agent_accuracy()`), `RecommendedContract` and `ContractOutcome` models.
- **External:** None — all data sources are already in use.
- **Data prerequisite:** At least 30 graded outcomes per agent before auto-tune activates.
  Users who have been running scans + outcome collection for several weeks will see
  immediate benefit. New users will use static weights until the threshold is met.

## Implementation Notes

### Files to Modify (6 files, all small changes)

1. `src/options_arena/services/outcome_collector.py`
   - `_process_active_contract()`: ask/bid fill formula
   - `run_scheduler()`: auto-tune trigger after collection

2. `src/options_arena/data/_debate.py`
   - `get_agent_accuracy()`: swap `stock_return_pct` → `contract_return_pct` in SQL

3. `src/options_arena/models/config.py`
   - `DebateConfig.auto_tune_weights`: default `False` → `True`

4. `src/options_arena/agents/orchestrator.py`
   - `compute_auto_tune_weights()`: minimum samples 10 → 30
   - `run_debate()`: log effective weights when using auto-tuned weights

5. Tests for realistic fill P&L calculation
6. Tests for contract-return-based accuracy query
7. Tests for auto-tune trigger in scheduler

### Feedback Loop Diagram

```
Scan → Debate (adaptive weights) → Recommend contract
                                        ↓
                             Track outcome (realistic fills)
                                        ↓
                             Grade agents (contract P&L truth)
                                        ↓
                             Recalibrate weights ──→ next Debate
```
