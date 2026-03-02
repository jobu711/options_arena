# OpenBB Platform Integration — Options Arena

## Prompt

```markdown
<role>
You are a senior Python data engineer
and financial platform architect.
Expertise: data provider abstraction layers,
async pipeline migration, OpenBB Platform SDK,
and integrating multi-source financial data
into existing analysis systems
without disrupting production pipelines.
</role>

<context>
{{CLAUDE.md from project root}}
Use Context7 MCP to verify all data structures,
Pydantic models, service interfaces,
and current data fetching implementations.

### Current Data Architecture
**Sources**: yfinance (OHLCV, option chains),
FRED (risk-free rate), CBOE (ticker universe)
**Pipeline**: async, fault-isolated,
asyncio.gather(return_exceptions=True)
**Models**: typed Pydantic at every boundary
**Design**: never-raises services with fallbacks

### Current Data Flow
```
CBOE → 5-7K tickers (universe)
yfinance → 1yr OHLCV per ticker (async batch)
yfinance → option chains for top 50
FRED → risk-free rate (DGS10)
All → pandas DataFrames → indicators → scoring
```

### Current Limitations
- yfinance: unreliable, rate-limited,
  no SLA, schema changes without warning,
  no Greeks, limited options metadata
- FRED: single data point (risk-free rate)
- CBOE: universe list only
- No fundamental data
- No options flow / unusual activity
- No sentiment signals
- No analyst estimates or earnings surprises
- No multi-provider redundancy

### OpenBB Platform Overview
Open-source Python SDK: `pip install openbb`
Standardized API across 100+ data providers.
```python
from openbb import obb
obb.equity.price.historical("AAPL")
obb.equity.options.chains("AAPL")
obb.equity.fundamental.income("AAPL")
obb.derivatives.options.unusual("AAPL")
obb.economy.fred_series("DGS10")
obb.technical.rsi(data=df, length=14)
```
Key feature: configure provider once,
consume via Python, REST API, or MCP server.
Supports: FMP, Polygon, Yahoo, FRED, CBOE,
Intrinio, and many more.
</context>

<task>
Design the integration of OpenBB Platform
into Options Arena as the unified data layer.
This is a data infrastructure migration,
not a feature addition — every downstream system
(indicators, scoring, Greeks, debate agents)
is affected by how data enters the pipeline.

---

### 1. Migration Strategy Assessment
Before designing anything, answer:
- - Which OpenBB data providers are free
  vs require paid API keys?
- What is the minimum viable integration
  that improves data quality immediately?
- What is the full integration that unlocks
  all new analytical capabilities?
- What breaks if OpenBB is down?
  (must maintain never-raises contract)

Recommend: **incremental migration**
or alternate strategy.

---

### 2. Data Provider Abstraction Layer
Design a provider abstraction so the pipeline
never couples directly to yfinance OR OpenBB:

```
Pipeline ←→ DataProviderInterface ←→ Provider
                                      ├── OpenBBProvider (Fundamentals and Sentiment)
                                      ├── YFinanceProvider (primary)
                                      └── MockProvider (testing)
```

Define the interface:
- **get_historical(ticker, period)** → DataFrame
- **get_option_chains(ticker)** → typed model
- **get_risk_free_rate()** → float
- **get_ticker_universe(preset)** → list[str]
- **get_fundamentals(ticker)** → typed model
- **get_unusual_activity(ticker)** → typed model
- **get_earnings_data(ticker)** → typed model

For each method specify:
- Pydantic response model (extend existing)
- Async signature compatible with current pipeline
- Fallback chain (OpenBB → yfinance → cached → default)
- Timeout and retry policy
- How it maps to `obb.*` API calls

---

### 3. Provider Configuration & Auth
- Where do API keys live? (.env, config, etc.)
- Which free providers cover the baseline?
- Must use free data sources no subscription.
  
Produce a provider recommendation matrix:

| Data Type          |
| OHLCV              | 
| Option Chains      | 
| Greeks / IV        | 
| Fundamentals       | 
| Unusual Activity   | 
| Earnings Estimates | 
| Sentiment / News   | 
| Risk-Free Rate     | 

---

### 4. New Data Capabilities Unlocked
With OpenBB integrated, design how each
new data type feeds into existing systems:

**A. Fundamentals → Debate Agents**
- Income, balance sheet, cash flow, ratios
- How does this enrich MarketContext?
- Which agent(s) consume it?
- Define the Pydantic model extension

**B. Analyst Estimates → Scoring + Debate**
- Price targets, earnings estimates, revisions
- Does this feed into composite scoring
  or debate context only?
- How do you handle conflicting estimates?

**C. Unusual Options Activity → Flow Agent**
- Volume/OI spikes, large block trades
- New signal for scoring or new agent input?
- Define unusual activity scoring schema

**D. Sentiment / News → Debate Agents**
- News sentiment, social media, insider trading
- Risk of noise: how to filter signal from junk?
- Latency: real-time or daily aggregation?

**E. Earnings Data → Risk Assessment**
- Earnings dates, surprise history, expected move
- Integrate into contract selection logic
  (avoid selling premium into earnings?)
- Feed into Risk Agent context

**F. Enhanced Options Chains**
- Compare OpenBB options chain quality
  vs current yfinance chains
- Does OpenBB provide Greeks directly?
  If so: use theirs or keep BAW/BSM local calc?
- IV surface data availability by provider

For each capability provide:
- **OpenBB API call** — exact obb.* method
- **Provider required** — free or paid?
- **Pydantic model** — new or extended
- **Pipeline integration point** — which phase?
- **Consumer** — which agent(s) or scoring layer?
- **Priority** — P0 / P1 / P2

---

### 5. Async Pipeline Integration
Current pipeline is async with fault isolation.
OpenBB SDK: verify if it supports async natively.
If not, design the async wrapper:

- Thread pool executor for sync OpenBB calls?
- Or OpenBB's REST API mode with aiohttp?
- Batch request patterns: can OpenBB batch
  multiple tickers in one call?
- Rate limiting: per-provider rate limit handling
- How does this interact with existing
  asyncio.gather pattern?

Benchmark estimate:
- Current yfinance: ~X seconds for 5K tickers
- Expected OpenBB: ~X seconds for 5K tickers
- Is there a net speed improvement or regression?

---

### 6. MCP Server for Debate Agents
OpenBB has an MCP server feature.
Evaluate whether debate agents should:

**Option A**: Receive pre-fetched data
  in MarketContext (current pattern, enriched)
**Option B**: Query OpenBB MCP server
  directly during debate (agents pull data)
**Option C**: Hybrid — pre-fetch core data,
  let agents query for follow-up questions

For each option:
- Latency impact on debate round
- Groq/Llama 3.3 70B: can it use MCP tools?
- Reliability: what if MCP query fails mid-debate?
- Data consistency: all agents see same snapshot?
- Complexity vs analytical depth tradeoff

---

### 7. Testing & Rollback Strategy
- How do you verify OpenBB returns equivalent
  data to yfinance for existing pipeline?
  (comparison test suite)
- Can you run both providers in parallel
  during migration and diff the results?
- What is the rollback plan if OpenBB
  degrades a data source mid-production?
- How do you test with rate-limited
  paid providers without burning API credits?
- Mock provider for CI/CD

---

### 8. Implementation Phasing
---

## Constraints
- Never-raises contract must be preserved.
  OpenBB failures fall back to yfinance,
  yfinance failures fall back to cache/default.
- Pydantic models extend, never break.
  All new fields must be Optional with defaults
  until fully populated.
- asyncio.gather fault isolation preserved.
- Phase 1 must be a pure infrastructure swap
  with zero behavior changes visible to users.
- Free tier must cover the current feature set.
  Paid providers are additive only.
- No vendor lock-in: the abstraction layer
  must make OpenBB replaceable too.
</task>

<instructions>
Start by verifying via Context7 exactly
which yfinance calls exist in the codebase
and what data shapes they return.
Map every current yfinance call to its
OpenBB equivalent with provider specification.
This mapping IS the migration plan.
The abstraction layer is the most important
deliverable — get the interface right
and everything else follows.
Design the interface from the consumer side:
what does the indicator engine need?
What does the Greeks calculator need?
What do debate agents need?
Let those requirements define the interface,
not OpenBB's API shape.
For the provider fallback chain, specify
exactly what constitutes a "failure"
that triggers fallback (timeout? empty response?
partial data? wrong schema?) —
don't leave this ambiguous.
</instructions>
```
