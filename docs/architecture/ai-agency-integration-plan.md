# AI Agency Evolution — Open Source Integration Plan

Companion to `.claude/prds/ai-agency-evolution.md`. Maps the open source options
trading ecosystem to Options Arena's agency evolution strategy.

Research date: 2026-03-13. 45 projects evaluated across 8 categories.

---

## Current Architecture vs. Agency Target

| Dimension | Current State | Agency Target |
|-----------|--------------|---------------|
| Agent autonomy | Zero — all data pre-fetched, agents are pure text generators | Tool-calling — agents fetch data on demand via `@agent.tool` |
| Memory | Stateless across runs | Three-tier: working, long-term patterns, reflective meta-learning |
| Learning | Outcome data collected but never fed back | Auto-tuned weights, prompt A/B testing, strategy mining |
| Inter-agent comms | One-way via orchestrator (deps injection) | Advisor routes queries to desks, desks can request peer input |
| Initiative | User-triggered only | Proactive monitoring with alerts on watchlist conditions |

---

## Repos to Cherry-Pick — Mapped to PRD Epics

### Epic 1: Desk Foundation (DeskDeps, @agent.tool)

**Primary source: TradingAgents**
- URL: https://github.com/TauricResearch/TradingAgents
- Stars: ~32,000 | Last active: Feb 2026 | License: Apache-2.0
- Cherry-pick: **Tool-per-role scoping pattern**. Their agents register domain-specific
  tools — Fundamentals Analyst gets SEC/earnings tools, Technical Analyst gets indicator
  tools, Sentiment Analyst gets news tools. Each agent only sees tools relevant to its
  domain.
- Apply as: Map their per-role tool registration to PydanticAI's `tools=[...]` parameter
  on `Agent()`. Trend desk gets OHLCV + indicator tools. Volatility desk gets vol
  surface + IV tools. Flow desk gets chain summary + unusual activity tools.
- Ignore: LangGraph orchestration framework (we use PydanticAI), their data models
  (we have Pydantic v2 typed models throughout).

**Secondary source: FinRobot**
- URL: https://github.com/AI4Finance-Foundation/FinRobot
- Stars: ~6,400 | Last active: Mar 2025 | License: MIT
- Cherry-pick: **API-to-tool wrapping pattern**. They expose SEC, Finnhub, FMP APIs as
  typed tool functions that LLMs can call. The pattern: thin wrapper around existing
  API client → returns structured text the LLM can parse.
- Apply as: Wrap existing `services/` methods in `agents/tools/` package. Tools return
  `str` (agent-consumable) but internally use typed Pydantic models. Tools never raise —
  return error strings on failure (matches our never-raises convention).
- Ignore: Smart Scheduler for model selection (we already have `build_debate_model()`
  with provider dispatch).

**Tool scoping map (derived from TradingAgents pattern):**

```
Desk            Tools                                     Service Source
─────────────── ───────────────────────────────────────── ────────────────────
Trend           fetch_quote, fetch_related_ohlcv,        MarketDataService
                compute_indicator_on_demand               indicators/
Volatility      fetch_quote, fetch_vol_surface_slice,    OptionsDataService,
                compute_iv_for_strike, garch_forecast     analysis/
Flow            fetch_quote, fetch_chain_summary,        OptionsDataService
                fetch_unusual_activity
Fundamental     fetch_quote, fetch_earnings_history,     MarketDataService,
                fetch_sector_comparison                   IntelligenceService
Risk            fetch_quote, fetch_correlation,          MarketDataService,
                fetch_portfolio_exposure                  Repository
Contrarian      fetch_quote, fetch_debate_history        Repository
Research (new)  All tools from all desks                 All services
```

**Architecture boundary evolution**: Currently `agents/` cannot import `services/`.
The evolution is runtime DI — service instances injected through `DeskDeps` dataclass,
not import-time coupling. This preserves testability (inject mocks) and decoupling.

---

### Epic 2: Advisor + Routing

**Pattern source: TradingAgents**
- Cherry-pick: Their agent pipeline structure (Analysts → Researchers → Trader). The
  Advisor agent is analogous to their "Trader" agent that synthesizes specialist outputs.
- Apply as: Advisor receives user query → classifies intent (desk targets + query type +
  tickers) → dispatches to relevant desks via `asyncio.gather` → synthesizes responses.
- V1 classification: Rule-based keyword matching + regex ticker extraction (not LLM-based).
  Upgrade path to LLM classification later.

**No direct repo dependency.** The routing pattern is simple enough to implement natively.

---

### Epic 3: All Desks Online

**Pattern source: TradingAgents (agent specialization)**
- Each TradingAgents specialist has a well-defined domain with exclusive tools. Apply the
  same principle: each Options Arena desk has tools it alone can access, preventing
  cross-domain hallucination.

**New Research Desk — pattern source: FinRobot**
- FinRobot's CoT (Chain-of-Thought) prompting pattern is relevant for the Research desk,
  which needs to perform multi-step analysis (fetch data → compute → analyze → synthesize).
- Apply as: Research desk uses ReAct-style prompting with all tools available and a
  higher tool call budget (5-8 vs 3 for specialist desks).

---

### Epic 4: Monitoring & Alerts

**No direct repo to cherry-pick.** Options Arena's existing infrastructure handles this:
- `OutcomeScheduler` pattern (scheduled async tasks)
- `WebSocketProgressBridge` pattern (async queue → WebSocket delivery)
- Watchlist CRUD already in `Repository`

**Reference only: SmartMoneyTracker**
- URL: https://github.com/hongtao510/SmartMoneyTracker
- Stars: ~38 | Unmaintained
- Reference: Their four unusual activity signals (high volume, call/put imbalance,
  buy/sell direction, IV jumps) inform what watchlist triggers to implement.
- Do not use as dependency or code source.

---

### Epic 5: Self-Improvement Phase 1 — Weight Tuning

**Pattern source: FinRL (reward signal design)**
- URL: https://github.com/AI4Finance-Foundation/FinRL
- Stars: ~14,200 | Last active: Mar 2026 | License: MIT
- Cherry-pick: **Reward signal design**. FinRL's reward = `log(portfolio_value_t /
  portfolio_value_{t-1})`. Options Arena's equivalent: contract P&L from
  `ContractOutcome` + Brier score from agent predictions.
- Apply as: The existing `compute_auto_tune_weights()` already computes inverse-Brier
  vote weights. Extend to cover indicator weights — correlate individual indicator
  values with outcome P&L to derive per-indicator effectiveness scores.
- Key insight from FinRL: composite score calibration should be driven by historical
  returns, not hand-tuned constants.
- Ignore: DRL framework (gym, stable-baselines3, PPO/SAC). RL is architecturally wrong
  for LLM agents — action space too simple, reward too delayed and noisy.

**What already exists (just needs connecting):**
- `AgentAccuracyReport` — per-agent direction hit rate + Brier score
- `CalibrationBucket` — confidence calibration curves
- `compute_auto_tune_weights()` — inverse-Brier vote weights
- `WeightSnapshot` — weight history tracking
- `auto_tune_weights()` — full accuracy → weights → persist flow

---

### Epic 6: Self-Improvement Phase 2 — Prompt A/B Testing

**Pattern source: FinGPT (model update methodology)**
- URL: https://github.com/AI4Finance-Foundation/FinGPT
- Stars: ~18,800 | Active | License: MIT
- Cherry-pick: **LoRA fine-tuning methodology** — but only as a FUTURE consideration.
  For now, cherry-pick the evaluation methodology: how FinGPT measures fine-tuned model
  quality against baselines (F1, accuracy, loss curves).
- Apply as: Prompt A/B testing framework. Tag each debate with the prompt version used.
  After 30+ samples per variant, compare accuracy metrics and promote the winner.
  Track prompt version → outcome correlation in SQLite.
- When to consider actual fine-tuning: After 5,000+ debates with outcomes. LoRA fine-tune
  a 7B model on the debate-to-outcome dataset. Requires GPU resources.

**No direct dependency.** Prompt versioning is a SQLite-backed system, not a library.

---

### Epic 7: Self-Improvement Phase 3 — Strategy Mining

**Pattern source: FinMem (three-tier memory architecture)**
- URL: https://github.com/pipiku915/FinMem-LLM-StockTrading
- Stars: ~856 | Abandoned Apr 2023 | License: MIT
- Cherry-pick: **Three-tier memory concept** — the architecture, not the code:
  1. **Short-term (working)**: Recent debates for same ticker/sector. Already queryable
     from `ai_theses` table. Render as context in prompts.
  2. **Long-term (patterns)**: Persistent learned patterns in new `agent_memory` SQLite
     table. Scoped by agent + ticker/sector/regime. Examples: "When IV Rank >80 in
     Technology, bearish puts outperform by 12% (n=67)"
  3. **Reflective (meta-learning)**: Weekly batch job that analyzes outcomes, groups by
     dimensions (sector × IV bucket × DTE bucket × direction), identifies statistically
     significant patterns (min 20 samples, chi-squared test), generates `StrategyRule`
     candidates for human approval.
- Apply as: SQLite-based (not vector DB). Options Arena's structured data allows exact
  SQL queries, which is more reliable than embedding similarity for financial data.
  Memory injected into prompts as delimited text blocks (`<<<LEARNED_PATTERNS>>>`).
- When to add vector DB: If agents need semantic similarity search across past debates
  (Phase 4+). Consider ChromaDB + sentence-transformers at that point.
- Ignore: FinMem's vector embedding retrieval, their abandoned implementation.

**Pattern source: optopsy (strategy performance evaluation)**
- URL: https://github.com/goldspanlabs/optopsy
- Stars: ~1,300 | Last active: Mar 2026 | License: AGPL-3.0
- Cherry-pick: Their 38-strategy taxonomy and performance metrics (Sharpe, Sortino, VaR,
  CVaR, Calmar). Inform what strategy patterns to mine from outcome data.
- Apply as: Reference for the `StrategyRule` pattern definitions and evaluation metrics.
  When strategy mining discovers "iron condors on low-IV tech stocks have 72% win rate,"
  optopsy's metric suite informs how to evaluate that claim statistically.
- Do not add as dependency (AGPL license, different data format).

---

### Epic 8: Agency Frontend

**No direct repo to cherry-pick.** Vue 3 + PrimeVue + Pinia stack is already established.

**Reference only: Stocksera**
- URL: https://github.com/guanquann/Stocksera
- Stars: ~758 | Stale since Mar 2023
- Reference: Their full-stack web app layout (options chain visualization + social
  sentiment + Congress trading data) shows how to organize a multi-panel dashboard.
  The chat-style interface for their analysis queries is worth studying.
- Do not use code (Django, stale, different stack).

---

## Direct Dependencies to Add

| Library | Version | Epic | Purpose | Risk |
|---------|---------|------|---------|------|
| `arch` | `>=7.0` | 1 (Volatility desk tool) | GARCH/EGARCH volatility forecasting | Low — scipy/numpy already present. MIT license. |

Everything else is **pattern-only** — study the architecture, adopt the concept,
implement in Options Arena's typed model system with PydanticAI.

---

## Future Integration Candidates (Not for Initial Epics)

| Library | When | Purpose |
|---------|------|---------|
| `ib_async` | Autonomous execution epic | Real-time IBKR data + order placement. asyncio-native. |
| `polygon-api-client` | Data quality epic | Professional chains with native Greeks, historical to 2014. Paid. |
| `schwab-py` | Broker integration epic | Real-time Greeks from ThinkorSwim infra. Requires Schwab account. |
| `chromadb` | Memory V2 | Vector similarity search when SQL-based memory proves insufficient. |
| `sentence-transformers` | Memory V2 | Encode debate context for semantic similarity retrieval. |
| `lumiwealth-tradier` | Data provider epic | `greeks=True` returns provider-computed Greeks from Tradier. |

---

## Repos Evaluated but NOT Recommended

| Repo | Stars | Why Skip |
|------|-------|----------|
| QuantLib-SWIG | 385 | Massive API complexity, 27MB wheel. Current scipy BSM+BAW is sufficient. |
| py_vollib | 389 | European-only IV solver. Current brentq works for American options. |
| PFHedge | 338 | Adds PyTorch dependency (~2GB) for marginal benefit over analytical Greeks. |
| TensorTrade | 6,100 | No options support. RL-focused crypto/equity framework. |
| optionlab | 482 | European BSM only, strategy evaluation not strategy mining. |
| OptionStratLib | 173 | Rust, no Python bindings. |
| RustQuant | 1,700 | Rust, no Python bindings. Interesting AD for Greeks but impractical. |
| backtrader | 20,700 | Abandoned. No options primitives. |
| vectorbt | 6,900 | No options primitives. Equity signals only. |
| zipline-reloaded | 1,700 | No options support. |
| riskfolio-lib | 3,800 | Pure equity portfolio optimization. No options/Greeks. |
| mibian | 288 | Abandoned since 2016, GPL license. |

---

## Key Architectural Decisions

### 1. PydanticAI stays — do not adopt LangGraph
TradingAgents uses LangGraph for orchestration. Options Arena should NOT switch.
PydanticAI's `@agent.tool` + typed deps + structured output already provide the same
capabilities with better type safety and simpler testing (TestModel).

### 2. SQLite memory — do not add vector DB in Phase 1
FinMem uses vector embeddings for memory retrieval. Options Arena's data is structured
(typed Pydantic models with discrete fields like sector, IV rank bucket, DTE bucket).
SQL WHERE clauses on these fields are more reliable than cosine similarity for pattern
retrieval. Add vector DB only when unstructured semantic search is needed.

### 3. Prompt injection for learning — do not use RL
FinRL's DRL approach is wrong for LLM agents. The feedback loop is:
outcome data → statistical analysis → pattern extraction → prompt text injection.
Not: outcome data → reward signal → gradient update → model weights.
The LLM is not being trained — its prompts are being enriched with historical context.

### 4. Service DI through deps — do not break architecture boundaries
Agents will access services at runtime through `DeskDeps` dataclass injection, not
through import-time coupling. This preserves testability and the boundary table from
CLAUDE.md. The `agents/` module still never imports from `services/` at the module level.

### 5. Tool call budgeting — prevent runaway costs
Cap tool calls per agent per query (default 3, Research desk gets 5-8). Tools that
fail or timeout return error strings, not exceptions. This follows the never-raises
convention and prevents a single agent from consuming excessive API calls.

---

## Competitive Landscape Context

### What Options Arena uniquely provides (no open source competitor)
1. Options-specific AI agency (all competitors target equities)
2. Local American-style pricing (BAW) with computed Greeks
3. Multi-agent debate on specific option contracts
4. Outcome tracking with P&L at multiple holding periods
5. Self-improvement loop from outcome → weight tuning → prompt evolution

### Closest architectural analogs to monitor
- **TradingAgents** (32k stars): If they add options support, they become a direct
  competitor. Currently stock-only. Monitor their roadmap.
- **optopsy** (1.3k stars): If they add AI/LLM integration, they bridge the gap from
  backtesting to recommendation. Currently pure backtesting. Active development.

### Gaps in the ecosystem Options Arena fills
- No open source real-time options screener with IV rank + Greeks filtering
- No open source portfolio-level options Greek aggregation tool
- No open source AI-powered options contract recommendation system
- No open source options outcome tracking with agent accuracy analytics
