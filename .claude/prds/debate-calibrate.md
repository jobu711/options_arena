---
name: debate-calibrate
description: Information-partitioned ensemble with log-odds pooling to replace unanimously-correlated agent system
status: planned
created: 2026-03-07T21:49:33Z
---

# PRD: debate-calibrate

## Executive Summary

Empirical analysis of 10 v2 debates and 45 contract outcomes reveals the 6-agent debate
system is **functionally a 1-agent system**. All directional agents agree 100% of the time,
agreement score never drops below 1.0, confidence capping never triggers, and three agents
produce near-constant outputs (Fundamental: confidence=0.700 with std=0.000; Flow: 100%
bullish; Volatility: 100% "overpriced"). The system produces unanimous bullish verdicts
regardless of input.

**Root cause**: All agents receive the same complete MarketContext — including pre-computed
`COMPOSITE SCORE` and `DIRECTION` from the scan pipeline. The shared `PROMPT_RULES_APPENDIX`
explicitly anchors confidence to composite score. Asking the same LLM the same question
with the same data 6 times produces the same answer 6 times.

**Solution**: Two structural changes that make disagreement emerge naturally:
1. **Information partitioning** — each agent sees only its domain-specific fields
2. **Log-odds pooling** — mathematically proper probability aggregation replaces linear
   weighted averaging

Three follow-up improvements complete the system: volatility direction voting, relaxed
contrarian gate, and outcome attribution for self-calibrating weights.

## Problem Statement

### The independence problem

The Condorcet jury theorem — the mathematical foundation of ensemble methods — requires
**independent** voters. When voters are correlated, majority vote provides no improvement
over a single voter. The current system violates this requirement:

- All 6 agents receive identical `render_context_block()` output (~80 fields)
- The context includes `COMPOSITE SCORE: 78.6` and `DIRECTION: bullish` — conclusions
  that prime the LLM toward the scan pipeline's pre-determined answer
- `PROMPT_RULES_APPENDIX` (shared by all agents) contains: "If COMPOSITE SCORE > 70
  and direction matches: confidence MUST be at least 0.4" — hardcoding echo behavior
- Trend echoes scan direction 80% of the time; Flow and Fundamental echo it 100%
- Agreement score has been 1.0 in 10/10 debates (100% unanimous)

### The aggregation problem

Current confidence pooling uses linear weighted average:
`weighted_confidence = sum(w_i * confidence_i) / sum(w_i)`

This kills extreme signals. Three agents each 90% confident → combined 90%. Correct
math (log-odds): three independent 90% sources → combined 99.7%. The linear method
also cannot distinguish "all agents mildly agree" from "one agent is very confident
and others are uncertain."

### The measured damage

| Metric | Value |
|--------|-------|
| Unanimous agreement rate | 100% (10/10 debates) |
| Verdict direction accuracy (T+1) | 60% (3/5 outcomes) |
| Overall contract win rate (T+1) | 37.8% (17/45) |
| Bullish contract win rate | 33.3% (10/30) |
| Bearish contract win rate | 53.8% (7/13) |
| Confidence capping triggers | 0% (never) |
| Contrarian execution rate | 20% (2/10 debates) |
| Agents whose removal changes verdict | 1 of 6 (trend only) |

The system's persistent bullish bias (92% bullish verdicts) likely contributes to the
bullish win rate being 20pp worse than bearish.

## User Stories

### US-1: Independent Agent Analysis via Information Partitioning

**As** an options trader reviewing debate output,
**I want** each agent to form its own opinion from domain-specific data only,
**so that** the multi-agent debate produces genuine disagreement reflecting different
analytical lenses, not the same conclusion rephrased six times.

**Acceptance Criteria:**
- AC-1.1: Four domain-specific context renderers exist: `render_trend_context()`,
  `render_volatility_context()`, `render_flow_context()`, `render_fundamental_context()`.
- AC-1.2: Each renderer includes only the shared identity fields (ticker, price, 52w
  range, DTE, strike, delta, sector) plus its domain-specific indicators.
- AC-1.3: No domain renderer includes `COMPOSITE SCORE`, `DIRECTION`, or
  `DIRECTION CONFIDENCE`. These scan-pipeline conclusions are withheld from all agents.
- AC-1.4: The original `render_context_block()` remains for persistence, display, and
  Risk/Contrarian agents that legitimately need the full picture.
- AC-1.5: At least 2 of 4 directional agents disagree on direction in >= 20% of debates
  (measured over 30+ debate sample). Current: 0%.
- AC-1.6: Trend agent echo rate (matching scan direction) drops below 70%. Current: 80%.

### US-2: Mathematically Proper Confidence Aggregation

**As** a verdict synthesis algorithm,
**I want** agent confidence values combined via log-odds pooling,
**so that** the ensemble properly handles extreme probabilities, compounds independent
agreement, and respects the mathematical properties of probability aggregation.

**Acceptance Criteria:**
- AC-2.1: `synthesize_verdict()` uses `log_odds_pool()` instead of linear weighted average.
- AC-2.2: Three agents at 0.9 confidence produce combined > 0.95 (not 0.9).
- AC-2.3: One agent at 0.9 plus two at 0.5 produces combined ~0.7 (not 0.63).
- AC-2.4: Confidence values are clamped to [0.01, 0.99] before log-odds to prevent
  log(0) / log(inf).
- AC-2.5: `PROMPT_RULES_APPENDIX` no longer references `COMPOSITE SCORE` in its data
  anchors (agents don't receive this field).

### US-3: Ensemble Diversity Measurement

**As** a system maintainer evaluating ensemble health,
**I want** vote entropy computed and persisted alongside the agreement score,
**so that** I can distinguish genuine disagreement from random noise and measure whether
information partitioning is working.

**Acceptance Criteria:**
- AC-3.1: `ExtendedTradeThesis` gains an `ensemble_entropy: float | None` field (Shannon
  entropy of the direction vote distribution, 0.0-1.585).
- AC-3.2: Entropy = 0.0 when all agents agree (unanimous). Entropy > 0 when agents
  disagree. Max ~1.585 for equal three-way split (bullish/bearish/neutral).
- AC-3.3: Entropy is persisted in `verdict_json` and queryable for analytics.

### US-4: Volatility Direction Signal

**As** a verdict synthesis algorithm,
**I want** the volatility agent to provide a directional opinion derived from IV regime,
**so that** its vote weight contributes to direction determination instead of being dead weight.

**Acceptance Criteria:**
- AC-4.1: `VolatilityThesis` gains a `direction: SignalDirection` field with a default of
  `SignalDirection.NEUTRAL` (backward-compatible with existing serialized data).
- AC-4.2: Volatility prompt instructs directional output based on IV regime: overpriced IV
  → bearish (long options face premium headwind), underpriced → bullish, fair → neutral.
- AC-4.3: Volatility is included in `agent_directions` dict in `synthesize_verdict()`.
- AC-4.4: Volatility prompt includes calibration anchors (IV rank < 25 → lean underpriced,
  25-75 → lean fair, > 75 → lean overpriced) as defaults the LLM can override with reasoning.

### US-5: Contrarian Availability

**As** a debate system seeking robust signal,
**I want** the contrarian agent to run in the majority of debates,
**so that** consensus weakness is identified before the verdict is finalized.

**Acceptance Criteria:**
- AC-5.1: Phase 1 failure threshold for contrarian skip is raised from `>= 2` to `>= 3`
  (only skip when 3+ of 4 Phase 1 agents fail).
- AC-5.2: Contrarian execution rate >= 80% (current: 20%).

### US-6: Outcome Attribution Pipeline

**As** a system maintainer building toward self-calibrating weights,
**I want** per-agent predictions linked to actual outcomes at multiple holding periods,
**so that** Brier scores can eventually replace static `AGENT_VOTE_WEIGHTS`.

**Acceptance Criteria:**
- AC-6.1: A new `agent_predictions` table stores per-agent direction and confidence at
  debate time, linked to `recommended_contract_id` via `debate_id`.
- AC-6.2: `outcomes collect` is extended to collect T+5, T+10, and T+20 (current: T+1 only).
- AC-6.3: An analytics query computes per-agent accuracy at each holding period.
- AC-6.4: 50+ debate+outcome pairs collected before any weight changes are deployed.

## Requirements

### Functional Requirements

#### FR-1: Domain-Partitioned Context Renderers (Priority 1 — Core)

Add four domain-specific rendering functions to `_parsing.py`. Each includes a **shared
identity block** plus only the fields relevant to that agent's analytical domain.

**Shared identity block** (included in all four renderers):
```
TICKER, PRICE, 52W HIGH, 52W LOW, SECTOR, DTE, TARGET STRIKE, TARGET DELTA,
EXERCISE, DIV YIELD, NEXT EARNINGS (+ warning if <= 7 days)
```

**Explicitly excluded from all domain renderers:**
`COMPOSITE SCORE`, `DIRECTION`, `DIRECTION CONFIDENCE`, `MACD` (scan-derived conclusion).
These remain in the full `render_context_block()` for persistence and Risk/Contrarian use.

**`render_trend_context(ctx: MarketContext) -> str`**:
Shared identity + RSI(14), ADX, SMA ALIGNMENT, STOCHASTIC RSI, REL VOLUME,
dim_trend (DSE trend score), RSI DIVERGENCE.

**`render_volatility_context(ctx: MarketContext) -> str`**:
Shared identity + IV RANK, IV PERCENTILE, ATM IV 30D, BB WIDTH, ATR %,
VOL REGIME, IV-HV SPREAD, SKEW RATIO, VIX TERM STRUCTURE, EXPECTED MOVE,
EXPECTED MOVE RATIO, VEGA, VOMMA, dim_iv_vol, dim_hv_vol.

**`render_flow_context(ctx: MarketContext) -> str`**:
Shared identity + PUT/CALL RATIO, MAX PAIN DISTANCE %, GEX, UNUSUAL ACTIVITY SCORE,
NET CALL PREMIUM, NET PUT PREMIUM, OPTIONS PUT/CALL RATIO, REL VOLUME,
dim_flow, dim_microstructure.

**`render_fundamental_context(ctx: MarketContext) -> str`**:
Shared identity + P/E, FORWARD P/E, PEG, P/B, DEBT/EQUITY, REVENUE GROWTH,
PROFIT MARGIN, SHORT RATIO, SHORT % OF FLOAT, ANALYST TARGET MEAN,
ANALYST TARGET UPSIDE, ANALYST CONSENSUS, UPGRADES/DOWNGRADES, INSIDER NET BUYS,
INSIDER BUY RATIO, INSTITUTIONAL OWNERSHIP, NEWS SENTIMENT, dim_fundamental.

**Implementation notes:**
- Factor shared identity rendering into `_render_identity_block(ctx)` to avoid duplication.
- `render_context_block()` stays unchanged — used by Risk agent, Contrarian agent,
  persistence layer, and display. It is NOT called for Phase 1 agents anymore.
- Risk agent (Phase 2) and Contrarian agent (Phase 3) still receive full context via
  `render_context_block()` — they legitimately need cross-domain visibility.
- Each renderer uses the same `_render_optional()` helper for None/NaN guarding.

#### FR-2: Update Orchestrator to Use Partitioned Context (Priority 1 — Core)

In `_run_v2_agents()`, replace the single `context_text = render_context_block(context)`
with domain-specific renders for each Phase 1 agent:

```python
from options_arena.agents._parsing import (
    render_trend_context,
    render_volatility_context,
    render_flow_context,
    render_fundamental_context,
    render_context_block,  # still used for Risk + Contrarian
)

trend_text = render_trend_context(context)
vol_text = render_volatility_context(context)
flow_text = render_flow_context(context)
fund_text = render_fundamental_context(context)
full_text = render_context_block(context)  # for Risk + Contrarian
```

Pass the domain-specific text to each Phase 1 agent's `.run()` prompt. Risk and Contrarian
continue to receive `full_text`.

#### FR-3: Update PROMPT_RULES_APPENDIX (Priority 1 — Core)

Remove the `COMPOSITE SCORE` data anchors from `PROMPT_RULES_APPENDIX` since agents no
longer receive this field:

**Remove:**
```
- If COMPOSITE SCORE < 40: your confidence MUST NOT exceed 0.5
- If COMPOSITE SCORE > 70 and direction matches: confidence MUST be at least 0.4
```

**Replace with domain-neutral calibration:**
```
- Base your confidence ONLY on the indicators present in YOUR context block.
- If the data you see is ambiguous or contradictory: confidence should be 0.3-0.5.
- If the data clearly supports one direction: confidence should be 0.6-0.8.
- Only exceed 0.8 when ALL indicators in your domain align.
```

#### FR-4: Log-Odds Pooling in synthesize_verdict() (Priority 1 — Core)

Replace the linear weighted confidence average with log-odds pooling.

**Add to `orchestrator.py`:**
```python
def _log_odds_pool(
    probabilities: list[float],
    weights: list[float],
) -> float:
    """Logarithmic opinion pool (Bordley 1982).

    Combines probability estimates via weighted sum in log-odds space.
    Mathematically proper: externally Bayesian, handles extremes correctly.
    """
    combined = 0.0
    total_weight = sum(weights)
    for p, w in zip(probabilities, weights):
        p_clamped = max(0.01, min(0.99, p))  # prevent log(0)
        combined += (w / total_weight) * math.log(p_clamped / (1.0 - p_clamped))
    return 1.0 / (1.0 + math.exp(-combined))
```

**Replace in `synthesize_verdict()`:**
```python
# Before (linear pooling):
weighted_confidence = 0.0
total_weight = 0.0
for name, output in agent_outputs.items():
    weight = AGENT_VOTE_WEIGHTS.get(name, 0.1)
    if hasattr(output, "confidence"):
        weighted_confidence += weight * output.confidence
        total_weight += weight
if total_weight > 0:
    weighted_confidence /= total_weight

# After (log-odds pooling):
probs: list[float] = []
weights: list[float] = []
for name, output in agent_outputs.items():
    if hasattr(output, "confidence"):
        probs.append(output.confidence)
        weights.append(AGENT_VOTE_WEIGHTS.get(name, 0.1))
if probs:
    weighted_confidence = _log_odds_pool(probs, weights)
else:
    weighted_confidence = config.fallback_confidence
```

The confidence capping for low agreement (`agreement < 0.4 -> cap at 0.4`) remains
unchanged — it's a separate safety mechanism.

#### FR-5: Vote Entropy on ExtendedTradeThesis (Priority 2)

Add `ensemble_entropy: float | None = None` to `ExtendedTradeThesis`. Compute in
`synthesize_verdict()` from the `agent_directions` dict:

```python
def _vote_entropy(agent_directions: dict[str, SignalDirection]) -> float:
    """Shannon entropy of agent vote distribution. 0.0 = unanimous."""
    if not agent_directions:
        return 0.0
    counts: dict[str, int] = {}
    for d in agent_directions.values():
        counts[d.value] = counts.get(d.value, 0) + 1
    total = len(agent_directions)
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy
```

Add `math.isfinite()` validator on the field. Default `None` for backward compat.

#### FR-6: Volatility Direction (Priority 2)

1. Add `direction: SignalDirection = SignalDirection.NEUTRAL` to `VolatilityThesis`.
2. Update volatility prompt to output direction based on IV regime. Include calibration:
   - IV rank < 25 and no earnings within 14 days → lean "underpriced", direction bullish
   - IV rank 25-75 → lean "fair", direction neutral
   - IV rank > 75 → lean "overpriced", direction bearish
3. Include `volatility` in `agent_directions` dict in `synthesize_verdict()` (remove
   the `isinstance(output, VolatilityThesis): continue` skip).

#### FR-7: Lower Contrarian Gate (Priority 2)

Change `phase1_failures < 2` to `phase1_failures < 3` in `_run_v2_agents()`.

#### FR-8: Agent Prediction Persistence (Priority 3)

New migration `025_agent_predictions.sql`:

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
CREATE INDEX IF NOT EXISTS idx_ap_debate ON agent_predictions(debate_id);
CREATE INDEX IF NOT EXISTS idx_ap_contract ON agent_predictions(recommended_contract_id);
```

Populate in the orchestrator after verdict synthesis, before returning `DebateResult`.

#### FR-9: Multi-Period Outcome Collection (Priority 3)

Extend `OutcomeCollector` to schedule collections at T+5, T+10, and T+20 in addition
to T+1. The `contract_outcomes` table already supports `holding_days` — only the
collection scheduling logic needs extension.

### Non-Functional Requirements

- **NFR-1**: Domain renderers must produce SHORTER context than the full render (~40-60%
  of current size per agent). This REDUCES per-agent token cost.
- **NFR-2**: All existing tests must pass. New renderers need unit tests verifying field
  inclusion/exclusion.
- **NFR-3**: `VolatilityThesis.direction` defaults to `NEUTRAL` — existing `vol_json`
  records without `direction` deserialize without error.
- **NFR-4**: `ensemble_entropy` defaults to `None` — existing `verdict_json` records
  deserialize without error.
- **NFR-5**: `agent_predictions` table created via numbered migration.
- **NFR-6**: No changes to `AppSettings` or `DebateConfig` schema.
- **NFR-7**: `_log_odds_pool()` is a pure function with no side effects. Must have unit
  tests covering: all-agree, split-vote, extreme-probability, single-agent cases.

## Success Criteria

### Primary Metrics (measured after 50+ debates post-implementation)

| Metric | Current | Target | Mechanism |
|--------|---------|--------|-----------|
| Unanimous agreement rate | 100% | < 50% | Information partitioning |
| Ensemble entropy (mean) | 0.0 | > 0.4 | Information partitioning |
| Trend echo rate | 80% | < 60% | Removed DIRECTION from context |
| Fundamental confidence std | 0.000 | > 0.10 | Domain-only context, no COMPOSITE SCORE anchor |
| Flow confidence std | 0.052 | > 0.10 | Domain-only context, no COMPOSITE SCORE anchor |
| Volatility direction diversity | 0% | >= 2 distinct values | Direction field + calibration |
| Contrarian execution rate | 20% | > 80% | Gate threshold change |
| Per-agent token count | ~2,600 | < 2,000 | Shorter partitioned context |

### Secondary Metrics (measured after 100+ outcomes)

| Metric | Current | Target | Mechanism |
|--------|---------|--------|-----------|
| Contract win rate (T+1) | 37.8% | > 45% | Better ensemble signal |
| Per-agent Brier score | Not measurable | Computable | Prediction persistence |
| Holding periods available | T+1 only | T+1, T+5, T+10, T+20 | Multi-period collection |
| Agents whose removal changes verdict | 1/6 | >= 3/6 | Independent votes |
| Bullish bias in verdicts | 92% bullish | < 70% | Agents form own direction |

### Validation Protocol

After implementation, run 50+ debates across diverse tickers (mix of bullish/bearish
scan directions, multiple sectors). Compute:
1. Pairwise Q-statistic between all agent direction outputs — target < 0.5 (current: ~1.0)
2. Ambiguity decomposition: diversity_ratio > 0.1 (current: 0.0)
3. Compare log-odds pooled confidence vs actual win rates (calibration curve)

## Architecture

### Before (Correlated Ensemble)

```
MarketContext (100% of fields, including COMPOSITE SCORE + DIRECTION)
    ├─→ Trend      → bullish 0.80 ─┐
    ├─→ Volatility → (no dir)      ─┤
    ├─→ Flow       → bullish 0.74 ─┤──→ linear avg ──→ bullish 0.73
    ├─→ Fundamental→ bullish 0.70 ─┤
    ├─→ Risk       → (no dir)      ─┤
    └─→ Contrarian → (skipped 80%) ─┘
```

### After (Information-Partitioned Ensemble)

```
MarketContext (partitioned by domain — no conclusions)
    ├─→ Trend      (RSI,ADX,SMA)           → bullish 0.75 ─┐
    ├─→ Volatility (IV,ATR,vol_regime)     → bearish 0.65 ─┤
    ├─→ Flow       (GEX,P/C,premiums)      → bullish 0.80 ─┤─→ log-odds ─→ bullish 0.68
    ├─→ Fundamental(PE,earnings,SI)        → neutral 0.45 ─┤   + entropy
    ├─→ Risk       (FULL context)          → (position sizing)
    └─→ Contrarian (FULL context + priors) → (stress test)
```

### Why This Works (Condorcet + Bordley)

1. **Information asymmetry → independence**: Each agent sees different data. Trend sees
   RSI/ADX but not PE ratios. Fundamental sees earnings but not GEX. They reach different
   conclusions because they're analyzing different evidence — not because prompts force them
   to disagree.

2. **Log-odds → proper aggregation**: When two independent agents both see bullish signals
   in their domains, log-odds compounds the evidence. When they disagree, the confident
   agent matters more than the uncertain one. This is mathematically optimal for
   aggregating probability estimates.

3. **No contrarian hack needed**: With 4 agents seeing different data, natural disagreement
   replaces forced dissent. The contrarian agent remains as a meta-analyst (it sees ALL
   prior outputs) but isn't the only source of dissent.

4. **Lower token cost**: Each agent receives ~40-60% of the current context. Per-agent
   tokens decrease from ~2,600 to ~1,500. Total debate cost may decrease despite
   contrarian running more often.

## Constraints & Assumptions

### Constraints

- **Groq rate limits**: Partitioned context is SHORTER than full context, so token budget
  improves (8,192 `num_ctx` remains sufficient).
- **No new LLM providers**: Calibrates existing Groq/Llama 3.3 70B setup.
- **Backward compatibility**: Existing debate records still deserialize. New fields on
  models have defaults.
- **Risk/Contrarian need full context**: These agents legitimately require cross-domain
  visibility. Only Phase 1 agents are partitioned.

### Assumptions

- Information partitioning is sufficient to break LLM correlation. If Llama 3.3 70B
  produces identical outputs even with different input data, the problem is deeper
  (model limitation) and out of scope.
- The field categorization (which indicators belong to which domain) is stable. Some
  overlap is acceptable (e.g., REL VOLUME appears in both trend and flow contexts).
- Log-odds pooling with static `AGENT_VOTE_WEIGHTS` is an interim step. The weights
  become self-calibrating once Brier score data accumulates (FR-8/FR-9 pipeline).

## Out of Scope

- **Brier-adaptive weight updating** — requires 50+ outcomes post-implementation. This PRD
  builds the data pipeline; adaptive weights are a follow-up PRD.
- Adding new agents (7th, 8th)
- Multi-LLM provider support
- Backtesting framework for historical replay
- Frontend changes to visualize agent disagreement or entropy
- Changes to the scan pipeline's direction scoring
- LMSR prediction market mechanism (research-grade, not production-ready)

## Dependencies

### Internal

| Dependency | Module | Required By |
|------------|--------|-------------|
| `render_context_block()` | `agents/_parsing.py` | FR-1 (extend, don't break) |
| `_render_optional()`, `_render_regime_label()` | `agents/_parsing.py` | FR-1 (reuse) |
| `PROMPT_RULES_APPENDIX` | `agents/_parsing.py` | FR-3 |
| `_run_v2_agents()` | `agents/orchestrator.py` | FR-2 |
| `synthesize_verdict()` | `agents/orchestrator.py` | FR-4, FR-5, FR-6 |
| `VolatilityThesis` | `models/analysis.py` | FR-6 |
| `ExtendedTradeThesis` | `models/analysis.py` | FR-5 |
| Migration runner | `data/database.py` | FR-8 |
| `OutcomeCollector` | outcome collection service | FR-9 |

### External

None. All changes are internal.

## Implementation Order

Issues should be created in this dependency order:

### Wave 1: Core Structural Changes (FR-1 through FR-4)
These four FRs form a single coherent change. They should ship together because
partitioned context without updated prompt rules would reference missing fields,
and log-odds pooling is the correct aggregation for independent agents.

1. **FR-1**: Domain-partitioned context renderers in `_parsing.py`
2. **FR-2**: Orchestrator wiring — pass domain text to Phase 1 agents
3. **FR-3**: Remove COMPOSITE SCORE anchors from `PROMPT_RULES_APPENDIX`
4. **FR-4**: `_log_odds_pool()` replaces linear average in `synthesize_verdict()`

### Wave 2: Enhanced Signal (FR-5 through FR-7)
Independent improvements that increase ensemble diversity further.

5. **FR-5**: Vote entropy field on `ExtendedTradeThesis`
6. **FR-6**: Volatility direction field + prompt + verdict integration
7. **FR-7**: Lower contrarian gate threshold (one-line change)

### Wave 3: Measurement Infrastructure (FR-8, FR-9)
Data pipeline for future self-calibrating weights.

8. **FR-8**: `agent_predictions` migration + persistence
9. **FR-9**: Multi-period outcome collection

### Wave 4: Validation
10. Run 50+ debates, collect outcomes, measure success criteria against targets.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Partitioned context confuses agents (missing expected fields) | Medium | High | Each domain renderer is self-contained; agents already handle missing optional fields via null guards |
| Log-odds produces extreme confidence (0.99+) | Medium | Low | Clamp to [0.01, 0.99] input + existing agreement capping |
| Agents with less context produce worse individual accuracy | Medium | Medium | Expected — ensemble accuracy improves even if individual accuracy drops, per ambiguity decomposition |
| Volatility direction field breaks deserialization of old data | Low | High | Default `NEUTRAL`; test roundtrip with old `vol_json` |
| Information partitioning is insufficient — agents still agree | Low | Medium | If so, signals a Llama 3.3 limitation; escalate to model evaluation |
| More disagreement → lower confidence → users perceive system as less decisive | Medium | Low | Correct behavior; lower confidence on contested verdicts IS the right answer |
