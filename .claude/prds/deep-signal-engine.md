---
name: deep-signal-engine
description: "Master coordination PRD — expansion from 18 to ~58 indicators, 6-agent debate, multi-dimensional scoring. Decomposed into 4 parallel epics."
status: complete
created: 2026-02-28T14:48:56Z
updated: 2026-03-01T09:06:05Z
---

# PRD: Deep Signal Engine — Master Coordination

## Executive Summary

Options Arena's analytical engine is critically narrow for an options analysis tool. It has 18 technical indicators, no true volatility modeling, a 3-agent sequential debate with limited specialization, and no options-specific analytics beyond first-order Greeks. This PRD coordinates a comprehensive expansion to ~58 indicators across 8 analytical dimensions, a 6-agent specialized debate roster with adversarial rebuttal protocol, and a multi-dimensional scoring system.

**This is a coordination document.** Implementation is split across 4 parallel epics — each designed to run in its own Claude Code instance on a dedicated branch. A shared Foundation phase defines model interfaces upfront to enable parallel work.

## Child PRDs

| Epic | PRD File | Scope | Instance |
|------|----------|-------|----------|
| **DSE-1** | `dse-volatility.md` | 13 IV/HV indicators + Vol Agent expansion | CC Instance 1 |
| **DSE-2** | `dse-flow-risk.md` | 12 flow/risk/Greeks indicators + Flow Agent | CC Instance 2 |
| **DSE-3** | `dse-trend-fund-regime.md` | 15 trend/fundamental/regime indicators + Fundamental Agent | CC Instance 3 |
| **DSE-4** | `dse-scoring-debate.md` | Scoring upgrade + 6-agent debate protocol + Contrarian Agent | CC Instance 4 |

---

## Parallel Execution Architecture

```
┌─────────────────────────────────────────────────────┐
│              Phase 0: Foundation                     │
│  All shared models, enums, config, IndicatorSignals  │
│  extension, MarketContext extension                  │
│              (single branch, merge first)            │
└────────────────────────┬────────────────────────────┘
                         │
          ┌──────────────┼──────────────┬──────────────┐
          ▼              ▼              ▼              ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
   │  DSE-1     │ │  DSE-2     │ │  DSE-3     │ │  DSE-4     │
   │ Volatility │ │ Flow/Risk  │ │ Trend/Fund │ │ Scoring/   │
   │ & IV       │ │ & Greeks   │ │ & Regime   │ │ Debate     │
   │            │ │            │ │            │ │            │
   │ Branch:    │ │ Branch:    │ │ Branch:    │ │ Branch:    │
   │ dse-1/vol  │ │ dse-2/flow │ │ dse-3/tfr  │ │ dse-4/score│
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
         │              │              │              │
         └──────────────┴──────┬───────┴──────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  Integration Merge  │
                    │  + E2E Test Suite   │
                    └─────────────────────┘
```

### Why This Split Works for Parallel Execution

1. **No file conflicts**: Each epic owns distinct files (see File Ownership Matrix below)
2. **Interface-first**: Foundation defines all model contracts. Epics implement against contracts.
3. **Independent testing**: Each epic can unit-test in isolation using mock data
4. **Graceful integration**: New indicator fields default to `None`. Scoring/debate gracefully handles missing indicators until all epics merge.

---

## File Ownership Matrix

This is the **critical contract** preventing merge conflicts. Each file is owned by exactly one epic.

### Foundation (Phase 0) Owns

| File | Action | Content |
|------|--------|---------|
| `models/enums.py` | Extend | `MarketRegime`, `VolRegime`, `IVTermStructureShape`, `RiskLevel`, `CatalystImpact`, `FlowDirection` |
| `models/scan.py` | Extend | `IndicatorSignals` — add all ~40 new optional fields (`field: float \| None = None`) |
| `models/analysis.py` | Extend | `MarketContext` extension + new agent output models: `FlowThesis`, `RiskAssessment`, `FundamentalThesis`, `ContrarianThesis` |
| `models/scoring.py` | Create | `DimensionalScores`, `DirectionSignal`, `ExtendedTradeThesis` |
| `models/config.py` | Extend | `DebateConfig` additions (phase1_parallelism, enable_regime_weights), `ScanConfig` additions |

### DSE-1: Volatility & IV Owns

| File | Action | Content |
|------|--------|---------|
| `indicators/iv_analytics.py` | **Create** | All IV-derived indicators (#19-29, #36, #37) |
| `indicators/volatility.py` | Extend | HV 20d (#20) helper, EWMA forecast (#27) |
| `pricing/iv_surface.py` | **Create** | Batch IV solving, term structure, ATM IV extraction |
| `tests/unit/indicators/test_iv_analytics.py` | **Create** | Unit tests for all IV indicators |
| `tests/unit/pricing/test_iv_surface.py` | **Create** | Unit tests for IV surface utilities |
| `agents/prompts/volatility_agent.py` | Extend | Updated prompt with new IV indicator context |

### DSE-2: Flow & Risk Owns

| File | Action | Content |
|------|--------|---------|
| `indicators/flow_analytics.py` | **Create** | GEX (#30), OI Concentration (#34), Unusual Activity (#35), Max Pain Magnet (#39), Dollar Volume Trend (#47) |
| `pricing/greeks_extended.py` | **Create** | Vanna (#31), Charm (#32), Vomma (#33) via finite difference |
| `indicators/options_specific.py` | Extend | PoP (#38), Optimal DTE (#40), Spread Quality (#45), Max Loss Ratio (#58) |
| `tests/unit/indicators/test_flow_analytics.py` | **Create** | Flow indicator tests |
| `tests/unit/pricing/test_greeks_extended.py` | **Create** | Second-order Greek tests |
| `agents/flow_agent.py` | **Create** | Flow Agent definition + prompts |

### DSE-3: Trend, Fundamental & Regime Owns

| File | Action | Content |
|------|--------|---------|
| `indicators/trend.py` | Extend | Multi-TF Alignment (#41), RSI Divergence (#42), ADX Exhaustion (#43) |
| `indicators/fundamental.py` | **Create** | Earnings EM vs IV (#48), Days to Earnings Impact (#49), Short Interest (#50), Div Impact (#51), IV Crush History (#52) |
| `indicators/regime.py` | **Create** | Market Regime (#53), VIX Term Structure (#54), Risk-On/Off (#55), Sector Momentum (#56), RS vs SPX (#44), Correlation Regime Shift (#57), Volume Profile Skew (#46) |
| `services/market_data.py` | Extend | Shared data fetchers for ^GSPC, ^VIX, ^VIX3M, sector ETFs (called once per scan) |
| `tests/unit/indicators/test_fundamental.py` | **Create** | Fundamental indicator tests |
| `tests/unit/indicators/test_regime.py` | **Create** | Regime indicator tests |
| `agents/fundamental_agent.py` | **Create** | Fundamental Agent definition + prompts |

### DSE-4: Scoring & Debate Owns

| File | Action | Content |
|------|--------|---------|
| `scoring/dimensional.py` | **Create** | DimensionalScores computation from indicator families |
| `scoring/composite.py` | Extend | Weight redistribution, regime-adjusted weight profiles |
| `scoring/direction.py` | Extend | Continuous confidence, DirectionSignal computation |
| `agents/trend_agent.py` | **Create** | Trend Agent (replaces Bull) |
| `agents/risk_agent.py` | Extend | Expanded Risk Agent with RiskAssessment output |
| `agents/contrarian_agent.py` | **Create** | Contrarian Agent (adversarial) |
| `agents/orchestrator.py` | Extend | Parallel Phase 1 → sequential Phase 2/3 debate protocol |
| `agents/prompts/` | Extend | All new/updated prompt templates |
| `tests/unit/scoring/test_dimensional.py` | **Create** | Dimensional scoring tests |
| `tests/integration/test_debate_protocol.py` | **Create** | 6-agent debate integration tests |

### Shared Files — Conflict Risk

These files are extended by Foundation and then referenced by multiple epics. **Only Foundation modifies them. Epics import from them read-only.**

- `models/enums.py` — Foundation adds enums, epics import them
- `models/scan.py` — Foundation adds fields, epics populate them
- `models/analysis.py` — Foundation adds models, epics produce/consume them
- `models/config.py` — Foundation adds config, epics read config

---

## Phase 0: Foundation

**Must complete before parallel epics start.** Estimated: 1-2 days for a single instance.

### New Enums (`models/enums.py`)

```python
class MarketRegime(StrEnum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    CRISIS = "crisis"

class VolRegime(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRISIS = "crisis"

class IVTermStructureShape(StrEnum):
    CONTANGO = "contango"
    BACKWARDATION = "backwardation"
    FLAT = "flat"

class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"

class CatalystImpact(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
```

### Extended IndicatorSignals (`models/scan.py`)

Add all ~40 new fields as optional with `None` defaults. Group by family with comments. Each epic populates its owned fields; unpopulated fields remain `None` and are handled gracefully by scoring and agents.

### New Models (`models/scoring.py`)

- `DimensionalScores` — 8 per-family sub-scores, each [0.0, 100.0]
- `DirectionSignal` — direction + confidence [0.0, 1.0] + contributing_signals

### Agent Output Models (`models/analysis.py`)

- `FlowThesis` — Flow Agent output
- `RiskAssessment` — expanded Risk Agent output
- `FundamentalThesis` — Fundamental Agent output
- `ContrarianThesis` — adversarial stress test output
- `ExtendedTradeThesis` — TradeThesis with dissent preservation

Full model definitions are in the original indicator tables within each child PRD.

### Config Extensions (`models/config.py`)

```python
# DebateConfig additions
phase1_parallelism: int = 4          # 4 for paid Groq, 2 for free tier
enable_regime_weights: bool = False  # opt-in until Phase 4

# ScanConfig additions
enable_iv_analytics: bool = True
enable_flow_analytics: bool = True
enable_fundamental: bool = True
enable_regime: bool = True
```

---

## Merge Strategy

### Branch Naming
- Foundation: `epic/dse-foundation`
- Epic 1: `epic/dse-1-volatility`
- Epic 2: `epic/dse-2-flow-risk`
- Epic 3: `epic/dse-3-trend-fund-regime`
- Epic 4: `epic/dse-4-scoring-debate`

### Merge Order
1. **Foundation** merges to `master` first
2. **Epics 1, 2, 3** branch from Foundation, merge in any order (no file conflicts)
3. **Epic 4** merges last (integrates all indicator outputs into scoring/debate)

### Conflict Prevention Rules
- Epic branches rebase on Foundation, not on each other
- `models/` files are read-only after Foundation merges — epics never modify model files
- Each epic's `scan/pipeline.py` integration is done during Integration Merge, not within the epic
- Pipeline wiring is a final integration step after all 4 epics merge

---

## Indicator Census (Full)

| Family | Current | DSE-1 | DSE-2 | DSE-3 | DSE-4 | Final |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| Volatility (IV) | 2 | **+11** | | | | 13 |
| Options Flow & OI | 2 | | **+11** | | | 13 |
| Trend & Momentum | 7 | | | **+4** | | 11 |
| Fundamental | 0.5 | | | **+5** | | 5 |
| Regime & Macro | 0 | | | **+5** | | 5 |
| Microstructure | 4 | | **+2** | **+1** | | 7 |
| Volatility (HV) | 3 | | | | | 3 |
| Risk Quantification | 0.5 | | **+1** | | | 1 |
| **TOTAL** | **18** | **+13** | **+12** | **+15** | **+0** | **58** |

DSE-4 adds zero indicators — it consumes all indicators via scoring and debate.

---

## Coverage Matrix (Before → After)

| Dimension | Before | After |
|-----------|:---:|:---:|
| Trend & Momentum | 4/5 | **5/5** |
| Volatility (IV-based) | 1/5 | **4/5** |
| Volatility (HV-based) | 2/5 | **3/5** |
| Options Flow & OI | 1/5 | **4/5** |
| Market Microstructure | 2/5 | **3/5** |
| Fundamental Context | 0.5/5 | **3/5** |
| Regime & Macro | 0/5 | **3/5** |
| Risk Quantification | 0.5/5 | **3/5** |
| **Total** | **11/40** | **28/40** |

---

## Compute Budget

| Phase | Indicators | Pipeline Impact | LLM Calls | Total |
|-------|:---:|---|:---:|---|
| Current | 18 | ~120s baseline | 3 sequential | ~120s |
| After all epics | 58 | +70s compute | 6 (4 parallel + 2 seq) | ~190s |

**58% pipeline increase**, dominated by LLM calls (agent expansion), not indicator computation.

---

## Success Criteria

1. Coverage matrix: 11/40 → 28+/40
2. Agent specialization: each owns 4+ exclusive signals
3. Debate citation density: 0.6 → 0.8+
4. IV modeling: 0 → full term structure, skew, regime
5. Every verdict includes contrarian challenge + agreement score
6. Zero increase in crash rate (never-raises preserved)
7. All existing tests pass without modification after each epic merges
8. Pipeline time < 190s for full universe scan

## Out of Scope

1. Real-time streaming data (requires paid OPRA feeds)
2. Backtesting engine (separate feature)
3. Multi-leg strategy construction (recommend type, don't build positions)
4. Portfolio-level risk (correlation, margin impact)
5. Alternative data (social sentiment, news NLP)
6. Model calibration (Heston, SABR surface fitting)
