---
name: dse-scoring-debate
description: "DSE Epic 4 — Multi-dimensional scoring, regime-adjusted weights, 6-agent debate protocol, Contrarian Agent"
status: backlog
created: 2026-02-28T10:22:58Z
parent: deep-signal-engine
---

# DSE-4: Scoring Engine & Debate Protocol

## Objective

Upgrade the scoring system from a single composite number to multi-dimensional family sub-scores with regime-adjusted weights. Redesign the debate protocol from 3 sequential agents to 6 specialized agents with parallel-first execution and adversarial stress-testing. Deploy Trend Agent (replaces Bull), expanded Risk Agent, and Contrarian Agent. Build the verdict synthesis with dissent preservation.

**This is the integration epic** — it consumes all indicators from DSE-1/2/3 and wires them into scoring and debate. Can develop and test against `None` indicator values during parallel phase; full integration after other epics merge.

**Branch**: `epic/dse-4-scoring-debate`
**Depends on**: Foundation (Phase 0) merged to master
**Parallel with**: DSE-1, DSE-2, DSE-3
**Merge order**: Last (after DSE-1, DSE-2, DSE-3)

---

## File Ownership

**This epic ONLY creates or modifies these files.**

| File | Action | Notes |
|------|--------|-------|
| `scoring/dimensional.py` | **Create** | DimensionalScores computation from indicator families |
| `scoring/composite.py` | Extend | Weight redistribution + regime-adjusted weight profiles |
| `scoring/direction.py` | Extend | Continuous confidence + DirectionSignal computation |
| `agents/trend_agent.py` | **Create** | Trend Agent (replaces Bull — direction-agnostic) |
| `agents/risk_agent.py` | Extend | Expanded with RiskAssessment output + quantified metrics |
| `agents/contrarian_agent.py` | **Create** | Adversarial Contrarian Agent |
| `agents/orchestrator.py` | Extend | 6-agent parallel-first debate protocol |
| `agents/prompts/trend_agent.py` | **Create** | Trend Agent prompt template |
| `agents/prompts/risk_agent.py` | Extend | Updated Risk prompt with new metrics |
| `agents/prompts/contrarian_agent.py` | **Create** | Contrarian prompt template |
| `tests/unit/scoring/test_dimensional.py` | **Create** | Dimensional scoring tests |
| `tests/unit/scoring/test_direction_ext.py` | **Create** | Direction confidence tests |
| `tests/integration/test_debate_protocol.py` | **Create** | 6-agent debate integration tests |

**Read-only imports** (do NOT modify):
- `models/` — Foundation-owned (all models, enums, config)
- `indicators/` — DSE-1, DSE-2, DSE-3 owned
- `pricing/` — DSE-1, DSE-2 owned
- `services/` — DSE-3 extends

---

## Part 1: Multi-Dimensional Scoring

### DimensionalScores Computation (`scoring/dimensional.py`)

Compute a sub-score per analytical family using the existing weighted geometric mean formula, scoped to indicators within each family.

```python
FAMILY_INDICATOR_MAP: dict[str, list[str]] = {
    "trend": [
        "rsi", "stoch_rsi", "williams_r", "adx", "roc",
        "supertrend", "sma_alignment",
        "multi_tf_alignment", "rsi_divergence", "adx_exhaustion", "rs_vs_spx",
    ],
    "iv_vol": [
        "iv_rank", "iv_percentile",
        "iv_hv_spread", "hv_20d", "iv_term_slope", "vol_regime",
        "ewma_vol_forecast", "vol_cone_percentile",
        "put_skew_index", "call_skew_index", "skew_ratio",
        "expected_move", "expected_move_ratio",
    ],
    "hv_vol": ["bb_width", "atr_pct", "keltner_width"],
    "flow": [
        "put_call_ratio", "max_pain_distance",
        "gex", "oi_concentration", "unusual_activity_score",
        "max_pain_magnet", "dollar_volume_trend",
    ],
    "microstructure": [
        "obv_trend", "ad_trend", "relative_volume", "vwap_deviation",
        "spread_quality", "volume_profile_skew",
    ],
    "fundamental": [
        "earnings_em_ratio", "days_to_earnings_impact",
        "short_interest_ratio", "div_ex_date_impact", "iv_crush_history",
    ],
    "regime": [
        "vix_term_structure", "risk_on_off_score",
        "sector_relative_momentum", "correlation_regime_shift",
    ],
    "risk": ["pop", "optimal_dte_score", "spread_quality", "max_loss_ratio"],
}


def compute_dimensional_scores(
    signals: IndicatorSignals,
    weights: dict[str, float],
) -> DimensionalScores:
    """Compute per-family sub-scores using weighted geometric mean.

    Gracefully handles None indicators — skips them and redistributes
    weight within the family. If all indicators in a family are None,
    the family score is None.
    """
```

**Key behavior**: When indicator epics haven't merged yet, their fields are all `None`. Dimensional scoring gracefully skips them and computes from available indicators. This enables independent testing during parallel development.

### Weight Redistribution

| Family | Current Weight | New Weight | Delta |
|--------|:---:|:---:|:---:|
| Trend & Momentum | 0.36 | 0.22 | -0.14 |
| Volatility (IV) | 0.12 | 0.20 | +0.08 |
| Volatility (HV) | 0.14 | 0.10 | -0.04 |
| Options Flow & OI | 0.10 | 0.18 | +0.08 |
| Microstructure | 0.15 | 0.10 | -0.05 |
| Fundamental | 0.00 | 0.08 | +0.08 |
| Regime & Macro | 0.00 | 0.05 | +0.05 |
| Moving Averages | 0.13 | 0.05 | -0.08 |
| Risk | 0.00 | 0.02 | +0.02 |
| **Total** | **1.00** | **1.00** | **0** |

### Regime-Adjusted Weight Profiles

4 profiles keyed to `MarketRegime` from indicator #53:

```python
REGIME_WEIGHT_PROFILES: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TRENDING: {
        # Boost: trend, momentum. Dampen: mean-reversion signals
    },
    MarketRegime.MEAN_REVERTING: {
        # Boost: oscillators, mean-reversion. Dampen: trend-following
    },
    MarketRegime.VOLATILE: {
        # Boost: volatility, risk. Dampen: momentum
    },
    MarketRegime.CRISIS: {
        # Boost: risk, flow, regime. Dampen: technicals
    },
}
```

All profiles sum to 1.0. **Opt-in**: `ScanConfig.enable_regime_weights: bool = False`. Default uses `TRENDING` profile (closest to current static weights).

### Direction Confidence (`scoring/direction.py`)

Replace 3-class discrete direction with continuous confidence gradient:

```python
def compute_direction_signal(
    signals: IndicatorSignals,
    regime: MarketRegime | None = None,
) -> DirectionSignal:
    """Compute directional pressure as continuous score.

    bullish_pressure = Σ(bullish_signal_i × weight_i)
    bearish_pressure = Σ(bearish_signal_i × weight_i)
    net_pressure = bullish - bearish → [-1.0, +1.0]
    confidence = abs(net_pressure)
    direction = BULLISH if net > threshold, BEARISH if < -threshold, else NEUTRAL
    """
```

Contributing signals: RSI, ADX, Supertrend, SMA Alignment, Multi-TF Alignment (#41), RSI Divergence (#42), Market Regime (#53).

**Backward compatibility**: `TickerScore.direction` stays `SignalDirection` enum. `DirectionSignal` is an additional field.

---

## Part 2: Agent Roster

### Agent 1: Trend Agent (`agents/trend_agent.py`) — Replaces Bull

| Attribute | Detail |
|-----------|--------|
| **Role** | Analyze directional momentum and trend strength. Argues the case (bullish OR bearish) based on trend signals. NOT always bullish. |
| **Exclusive** | Multi-TF Alignment (#41), RSI Divergence (#42), ADX Exhaustion (#43), RS vs SPX (#44), Sector Momentum (#56), Volume Profile Skew (#46) |
| **Shared** | RSI, ADX, Supertrend, SMA Alignment, ROC |
| **Output** | `AgentResponse` (existing) |
| **Key Question** | "Is there a tradeable directional edge, and how strong is it?" |
| **Fallback** | trend_score from DimensionalScores + direction confidence |
| **Signal count** | 6 exclusive + 5 shared = 11 |

### Agent 4: Risk Agent (`agents/risk_agent.py`) — Expanded

| Attribute | Detail |
|-----------|--------|
| **Role** | Quantify downside risk, position sizing, tail exposure, and liquidity risk. |
| **Exclusive** | PoP (#38), Optimal DTE (#40), Spread Quality (#45), Charm (#32), Div Impact (#51), Max Loss (#58) |
| **Shared** | All Greeks (delta, gamma, theta, vega, rho), Earnings Impact (#49) |
| **Output** | `RiskAssessment` (new — from Foundation) |
| **Key Question** | "What is the worst-case scenario, and is the risk/reward acceptable?" |
| **Fallback** | risk_score + PoP + max loss calculations |
| **Signal count** | 6 exclusive + 6 shared = 12 |

### Agent 6: Contrarian Agent (`agents/contrarian_agent.py`) — New

| Attribute | Detail |
|-----------|--------|
| **Role** | Adversarial stress-tester. Always challenges emerging consensus. |
| **Input** | All 5 prior agent outputs + DimensionalScores + MarketContext |
| **Output** | `ContrarianThesis` (from Foundation) |
| **Key Question** | "What is everyone missing? Where is the consensus wrong?" |
| **Fallback** | Identify highest-confidence agent, generate counter-arguments from dimensional scores that contradict it. |
| **Unique value** | Only agent that sees ALL prior outputs. Specifically prompted to find disagreements. |

---

## Part 3: Debate Protocol Redesign

### Current Protocol
```
Bull → Bear → Risk  (3 sequential LLM calls)
```

### New Protocol: Parallel-First with Adversarial Synthesis

```
Phase 1 (parallel):  Trend + Volatility + Flow + Fundamental  →  4 LLM calls
Phase 2 (sequential): Risk Agent (sees all Phase 1 outputs)   →  1 LLM call
Phase 3 (sequential): Contrarian Agent (sees all 5 outputs)   →  1 LLM call
Phase 4 (algorithmic): Verdict Synthesis (no LLM)             →  0 LLM calls
                                                          Total: 6 LLM calls
```

### Orchestrator Changes (`agents/orchestrator.py`)

```python
async def run_debate(
    context: MarketContext,
    dimensional: DimensionalScores,
    config: DebateConfig,
) -> ExtendedTradeThesis:
    """6-agent debate with parallel Phase 1."""

    # Phase 1: Independent analysis (parallel)
    phase1_agents = [trend_agent, volatility_agent, flow_agent, fundamental_agent]
    parallelism = config.phase1_parallelism  # 4 for paid, 2 for free Groq

    if parallelism >= 4:
        phase1_results = await asyncio.gather(
            *[agent.run(context) for agent in phase1_agents],
            return_exceptions=True,
        )
    else:
        # Batch into groups of `parallelism`
        phase1_results = await _batched_gather(phase1_agents, context, parallelism)

    # Phase 2: Risk assessment (sequential, sees Phase 1)
    risk_result = await risk_agent.run(context, phase1_results)

    # Phase 3: Adversarial challenge (sequential, sees all)
    all_results = [*phase1_results, risk_result]
    contrarian_result = await contrarian_agent.run(context, all_results, dimensional)

    # Phase 4: Verdict synthesis (algorithmic)
    return synthesize_verdict(all_results, contrarian_result, dimensional)
```

### Graceful Degradation

| Phase 1 Failures | Behavior |
|:-:|---|
| 0 | Normal: 4 agents → Risk → Contrarian |
| 1 | Continue with 3 + Risk + Contrarian. Log warning. |
| 2 | Continue with 2 + Risk. Skip Contrarian (insufficient diversity). |
| 3 | Single-agent mode + data-driven thesis. |
| 4 | Full data-driven fallback (existing behavior). |

Track via `DebateResult.agents_completed: int`.

### Groq Rate Limit Strategy

- Groq free tier: 30 RPM, 6,000 TPM for Llama 3.3 70B
- Phase 1 parallel: 4 simultaneous. If rate-limited → degrade to 2+2 batches
- Token budget: ~2,000 tokens/agent × 6 = 12,000 tokens/debate
- Configurable: `DebateConfig.phase1_parallelism: int = 4`

---

## Part 4: Verdict Synthesis

### ExtendedTradeThesis

```python
class ExtendedTradeThesis(TradeThesis):
    contrarian_dissent: ContrarianThesis | None
    agent_agreement_score: float         # [0.0, 1.0]
    dissenting_agents: list[str]
    dimensional_scores: DimensionalScores
```

### Agreement Score Computation

```python
def compute_agreement_score(agent_outputs: list[AgentOutput]) -> float:
    """How aligned are agents on direction?

    Extract direction from each agent output.
    Agreement = fraction of agents agreeing with majority direction.
    """
```

### Confidence Capping

When `agent_agreement_score < 0.4`, cap thesis `confidence` at 0.50 regardless of individual agent confidence. High disagreement = low conviction.

### Weighted Vote

```python
AGENT_VOTE_WEIGHTS = {
    "trend": 0.25,
    "volatility": 0.20,
    "flow": 0.20,
    "fundamental": 0.15,
    "risk": 0.15,
    "contrarian": 0.05,  # Low weight but preserved as dissent
}
```

---

## Testing Requirements

### Unit Tests — Dimensional Scoring

1. **All indicators present**: Verify family sub-scores computed correctly
2. **Partial indicators (None)**: Verify graceful skip and weight redistribution
3. **All None in family**: Family score = None
4. **Weight profiles**: Each regime profile sums to 1.0
5. **Regression**: Existing composite score unchanged with new weight system (migration path)

### Unit Tests — Direction Confidence

1. **Strong bull**: RSI 75 + ADX 40 + aligned → high bullish confidence
2. **Strong bear**: RSI 25 + downtrend + divergence → high bearish confidence
3. **Neutral**: Mixed signals → low confidence, NEUTRAL direction
4. **Regime effect**: Same signals with different regime → different thresholds

### Integration Tests — Debate Protocol

1. **Happy path**: 6 agents complete, verify ExtendedTradeThesis structure
2. **1 agent failure**: Verify 5-agent degradation
3. **2 agent failures**: Verify skip Contrarian
4. **Total failure**: Verify data-driven fallback
5. **Rate limiting**: Verify parallelism degradation (4 → 2+2 batches)
6. **Agreement scoring**: High agreement (>0.8), low agreement (<0.4 → confidence cap)

### Mock LLM Strategy

All agent tests use mock Groq responses. The debate protocol tests verify:
- Correct agent ordering (parallel Phase 1, then sequential 2/3)
- Context passing (each phase receives prior outputs)
- Fallback activation on failure
- Token budget adherence

---

## Merge Boundaries — DO NOT TOUCH

- `indicators/iv_analytics.py` — DSE-1
- `indicators/volatility.py` — DSE-1
- `pricing/iv_surface.py` — DSE-1
- `indicators/flow_analytics.py` — DSE-2
- `pricing/greeks_extended.py` — DSE-2
- `indicators/options_specific.py` — DSE-2
- `indicators/trend.py` — DSE-3
- `indicators/fundamental.py` — DSE-3
- `indicators/regime.py` — DSE-3
- `services/market_data.py` — DSE-3
- `models/` — Foundation only

---

## Dependencies

### From Foundation
- `DimensionalScores`, `DirectionSignal`, `ExtendedTradeThesis` models
- `RiskAssessment`, `ContrarianThesis` models
- `MarketRegime`, `RiskLevel` enums
- Config: `DebateConfig`, `enable_regime_weights`

### From Existing Code
- `scoring/composite.py` — existing geometric mean formula (extend, don't replace)
- `scoring/direction.py` — existing direction logic (extend with confidence)
- `scoring/normalization.py` — percentile-rank framework (no changes needed)
- `agents/orchestrator.py` — existing debate flow (refactor to 6-agent)
- `agents/bear_agent.py` — existing (deprecated by Trend Agent, but kept for fallback)

### Cross-Epic (at Integration)
- DSE-1 provides: 13 IV indicators for `iv_vol_score` + Volatility Agent expansion
- DSE-2 provides: 12 flow/risk indicators for `flow_score`, `risk_score` + Flow Agent
- DSE-3 provides: 15 trend/fund/regime indicators for remaining scores + Fundamental Agent + Market Regime for weight adjustment
- All indicators default to `None` during parallel development — scoring handles this gracefully

---

## Integration Merge Checklist

After DSE-1, DSE-2, DSE-3 have all merged, this epic's final merge must verify:

1. [ ] All 40 new `IndicatorSignals` fields are populated in scan pipeline
2. [ ] DimensionalScores has non-None values for all 8 families
3. [ ] All 6 agents receive correct indicator context in prompts
4. [ ] Debate protocol completes with all 6 agents (mock LLM)
5. [ ] Graceful degradation works with real Groq (1, 2, 3, 4 failures)
6. [ ] Existing tests pass (backward compatibility)
7. [ ] Composite score regression: same inputs → same output as before weight change
8. [ ] Pipeline time < 190s for full universe scan
