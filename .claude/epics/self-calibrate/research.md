# Research: self-calibrate

## PRD Summary

Three targeted changes to create a self-improving feedback loop:
1. **Realistic fill pricing** — Replace mid-to-mid P&L with ask-entry / bid-exit for long positions
2. **Contract-level accuracy** — Grade agents on `contract_return_pct > 0` instead of `stock_return_pct` direction
3. **Auto-tune default on + auto-trigger** — Enable by default, raise threshold to 30, trigger after outcome collection

The PRD specifies 6 files, all small changes. Infrastructure is already in place — this is a wiring job, not a build job.

## Relevant Existing Modules

| Module | File(s) | Role |
|--------|---------|------|
| `services/` | `outcome_collector.py` | Computes P&L (`_process_active_contract` lines 307-317), hosts `run_scheduler()` loop (lines 467-492) |
| `data/` | `_debate.py` | Agent accuracy SQL (`get_agent_accuracy()` lines 260-332, `get_agent_calibration()` line 334+) |
| `agents/` | `orchestrator.py` | `compute_auto_tune_weights()` (line 936), `auto_tune_weights()` (line 971), weight loading in `run_debate()` (lines 1458-1467) |
| `models/` | `config.py` | `DebateConfig.auto_tune_weights: bool = False` (line 341) |
| `models/` | `analytics.py` | `RecommendedContract`, `ContractOutcome`, `AgentAccuracyReport`, `AgentWeightsComparison` |

## Existing Patterns to Reuse

### 1. NaN/Inf Defense Pattern
`ContractOutcome` already has `validate_optional_return_finite` on `stock_return_pct` and `contract_return_pct`. The new fill formula `(exit_bid - entry_ask) / entry_ask * 100` must guard `entry_ask == 0` before computing.

### 2. Never-Raises Service Pattern
`OutcomeCollector` and all `run_scheduler()` paths catch exceptions and log. The auto-tune trigger must follow:
```python
try:
    comparisons = await auto_tune_fn(self._repo, window_days=90)
except Exception:
    logger.exception("Auto-tune failed, will retry next cycle")
```

### 3. Decimal Arithmetic
`RecommendedContract.ask` is `Decimal`. `ContractOutcome.exit_contract_bid` is `Decimal | None`. The fill formula must use `Decimal` arithmetic throughout, converting to `float` only at the return point.

### 4. Batch Isolation
`_collect_for_period()` has per-contract `try/except`. The auto-tune trigger runs once after all periods complete, not inside the per-contract loop.

### 5. DI Constructor Pattern
`OutcomeCollector.__init__` already takes `config, repository, market_data, options_data`. Adding an optional `auto_tune_fn` callable follows the same pattern.

## Existing Code to Extend

### `_process_active_contract()` — P&L calculation (lines 307-317)
```python
# CURRENT: mid-to-mid
exit_contract_mid = (matching.bid + matching.ask) / Decimal("2")
if contract.entry_mid and contract.entry_mid > 0:
    contract_return = float(
        (exit_contract_mid - contract.entry_mid) / contract.entry_mid * Decimal("100")
    )
```
**Change:** Use `contract.ask` as entry fill, `matching.bid` as exit fill, with fallback chain.

### `_compute_contract_return()` (lines 413-424)
Called ONLY from `_process_expired_contract()` for ITM intrinsic-value exits. **Leave unchanged** — expired ITM uses intrinsic value (not subject to spread). The active path has its own inline calculation.

### `get_agent_accuracy()` SQL (lines 283-316)
6 occurrences of `co.stock_return_pct > 0` / `co.stock_return_pct < 0` in two CASE expressions. Replace all with `co.contract_return_pct > 0` / `co.contract_return_pct IS NOT NULL`. Also update `HAVING COUNT(*) >= 10` to `>= 30`.

### `get_agent_calibration()` (line 334+)
Contains identical `stock_return_pct` grading logic. Must be updated in parallel for consistency.

### `compute_auto_tune_weights()` (line 936)
`r.sample_size >= 10` threshold at line 945. Also at line 997 in `auto_tune_weights()`. Both change to `>= 30`.

### `run_debate()` weight loading (lines 1458-1467)
Currently logs "Using auto-tuned vote weights for {ticker}" — needs per-agent weight logging.

### `run_scheduler()` (lines 467-492)
Auto-tune hook inserted after line 487 (after "Scheduled outcome collection complete").

## Potential Conflicts

### 1. Architecture Boundary: `services/` cannot import from `agents/`
**Critical.** The PRD's pseudocode places `auto_tune_weights()` call inside `OutcomeCollector.run_scheduler()`, but `services/` cannot import from `agents/`.

**Resolution (recommended):** Inject `auto_tune_fn: Callable[..., Awaitable[list]] | None = None` into `OutcomeCollector.__init__()` via DI. The CLI layer (which CAN import from both `services/` and `agents/`) wires the callable at construction time. This matches the existing DI pattern and keeps `services/` clean.

### 2. Legacy Data Transition
Changing accuracy grading to `contract_return_pct` will exclude rows where it's `NULL` (older data collected without options chain data). This reduces sample counts and may drop agents below the 30-sample threshold. **Acceptable by PRD design** — old data ages out of the 90-day window naturally.

### 3. Default Config Change
`auto_tune_weights: False → True` changes behavior for any `DebateConfig()` default-constructed instance. Users without 30+ outcomes per agent get static weights silently (correct — `auto_tune_weights()` returns `[]` when no eligible agents). No breaking change.

### 4. `get_agent_calibration()` Consistency
If only `get_agent_accuracy()` is updated, calibration and accuracy will use different ground truth. Both must be updated atomically.

### 5. PRD Safety Guard — VERIFIED: GUARD NEEDED
PRD requires: if any auto-tuned agent weight > 0.50, revert to static weights. Current `compute_auto_tune_weights()` clamps to `[0.05, 0.35]` pre-normalization, but post-normalization can exceed 0.50. Worst case: one agent at 0.35, four at 0.05 → `(0.35/0.55)*0.85 = 0.5409`. **An explicit post-normalization guard must be added.**

## Resolved Questions

1. **Architecture boundary** — DI callable injection. `OutcomeCollector.__init__()` accepts optional `auto_tune_fn: Callable | None = None`. CLI/API layer wires the callable.
2. **Accuracy grading** — Pure contract profitability (`contract_return_pct > 0`). Direction distinction removed.
3. **`get_agent_calibration()`** — Update alongside `get_agent_accuracy()` for consistency.

## Recommended Architecture

### Implementation Approach

1. **FR-1 (Realistic Fills):** Modify inline P&L calculation in `_process_active_contract()` with fallback chain: `(contract.ask, matching.bid)` → `(contract.entry_mid, exit_contract_mid)` when fields are None/zero. Leave `_compute_contract_return()` and expired paths unchanged.

2. **FR-2 (Contract Accuracy):** Replace 6 `stock_return_pct` references in `get_agent_accuracy()` SQL with `contract_return_pct > 0`. Add `co.contract_return_pct IS NOT NULL` to WHERE clause. Apply same changes to `get_agent_calibration()`. Update `HAVING` threshold to 30.

3. **FR-3 (Auto-Tune):**
   - Change `DebateConfig.auto_tune_weights` default to `True`
   - Change sample threshold from 10 to 30 in `compute_auto_tune_weights()` and `auto_tune_weights()`
   - Add `auto_tune_fn: Callable | None = None` to `OutcomeCollector.__init__()`
   - Wire the callable from CLI/API layer at construction time
   - Add per-agent weight logging in `run_debate()` when auto-tuned weights differ from manual
   - Add post-normalization degenerate weight guard: if any agent > 0.50, return `AGENT_VOTE_WEIGHTS` and log warning

### No Schema Migration Needed
All required fields already exist: `RecommendedContract.ask`, `ContractOutcome.exit_contract_bid`, `auto_tune_weights` table. Zero new columns or tables.

### No Model Changes Needed
`RecommendedContract`, `ContractOutcome`, and all analytics models have correct fields. Downstream API endpoints and CLI display code work unchanged.

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/services/test_outcome_collector.py` — `make_contract()` factory already includes `bid`, `ask`, `entry_mid` fields
- `tests/unit/services/test_outcome_scheduler.py` — scheduler lifecycle, `CancelledError`, error recovery
- `tests/unit/agents/test_auto_tune_orchestration.py` — `auto_tune_weights()` flow, `_report()` helper with `sample_size=50`
- All async tests use `@pytest.mark.asyncio`, `AsyncMock`, `pytest.approx()` for floats

### New Tests Needed
1. **Realistic fill P&L** (`test_outcome_collector.py`):
   - Active contract with ask entry + bid exit → correct return
   - Fallback to mid when `ask == 0`
   - Fallback to `exit_contract_mid` when `exit_contract_bid is None`
   - Verify `is_winner` follows realistic fill, not mid-price
   - Expired ITM path unchanged (still uses intrinsic value)

2. **Contract-return accuracy** (`test_outcome_repository.py` or new `test_agent_accuracy.py`):
   - Agents graded on `contract_return_pct > 0` (profitable contract = correct)
   - NULL `contract_return_pct` rows excluded from accuracy
   - HAVING threshold = 30
   - `get_agent_calibration()` consistent with `get_agent_accuracy()`

3. **Auto-tune trigger** (`test_outcome_scheduler.py`):
   - `run_scheduler()` calls `auto_tune_fn` after successful collection
   - `auto_tune_fn` failure doesn't crash scheduler
   - `auto_tune_fn=None` skips trigger silently
   - Sample threshold 30 in `compute_auto_tune_weights()`

4. **Weight logging** (`test_auto_tune_orchestration.py`):
   - `run_debate()` logs per-agent weights when auto-tuned
   - Degenerate weight guard (>0.50) reverts to static

## Estimated Complexity

**S (Small)** — 6 files modified, all targeted changes to existing logic. No new modules, no schema migrations, no model changes. Infrastructure is fully in place. The main complexity is the architecture boundary resolution for the auto-tune trigger (DI callable injection) and ensuring the 3 threshold changes (SQL HAVING + 2 Python guards) are updated atomically. Estimated 3-5 issues in the epic.
