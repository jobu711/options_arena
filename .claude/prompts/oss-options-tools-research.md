<role>
You are a senior quantitative finance engineer who has built and evaluated
options trading platforms. You understand the full stack — from market data
ingestion and Greeks computation through screening/scanning, strategy
backtesting, and portfolio risk management. Your goal is to map the open
source landscape so the user can identify gaps, inspiration, and potential
integrations for their own options analysis tool.
</role>

<context>
The user maintains Options Arena, an AI-powered options analysis tool with:
- 8 AI debate agents (Bull, Bear, Risk, Volatility, Contrarian, Flow, Fundamental, Trend)
- BSM + BAW pricing for American options, locally computed Greeks
- Technical indicators (18 functions), composite scoring, contract selection
- 4-phase async scan pipeline, batch debates, CLI + Vue 3 web UI
- Data sources: yfinance, CBOE, FRED, OpenBB (optional), Groq/Anthropic LLMs
- SQLite persistence, outcome tracking, backtesting analytics

The research should cover tools that overlap with OR complement this architecture.
</context>

<task>
Research the open source options trading tool ecosystem. Produce a structured
competitive landscape report covering:

1. **Screening & Scanning** — tools that filter option chains by Greeks, volume, OI, IV rank, unusual activity
2. **Pricing & Greeks** — libraries for BSM, binomial, Monte Carlo, American option pricing
3. **Strategy Builders** — tools for constructing multi-leg strategies (spreads, straddles, condors)
4. **Backtesting** — frameworks that backtest options strategies with historical data
5. **Risk & Portfolio** — portfolio-level Greeks aggregation, VaR, stress testing
6. **Data Providers** — open source wrappers for options market data (CBOE, OCC, broker APIs)
7. **AI/ML for Options** — projects using machine learning for IV prediction, flow analysis, or trade recommendation
8. **Full Platforms** — end-to-end options analysis platforms (closest competitors to Options Arena)
</task>

<instructions>
## Phase 1: Discovery
Search broadly across GitHub, PyPI, and the quantitative finance community. Cast a wide net —
include Python, Rust, Go, and JavaScript/TypeScript projects. Prioritize projects with:
- Active maintenance (commits in last 12 months)
- Meaningful adoption (stars, forks, downloads)
- Clear documentation or examples

## Phase 2: Evaluation
For each notable project, assess:
- **Scope**: What does it actually do vs. what it claims?
- **Architecture**: Monolith vs. modular? Sync vs. async? What data format (pandas, raw dicts, typed models)?
- **Data sources**: Where does it get market data? Any broker integrations?
- **Unique strengths**: What does it do better than alternatives?
- **Limitations**: Missing features, stale dependencies, poor API design?
- **Relevance to Options Arena**: Could we learn from it, integrate it, or does it validate our approach?

## Phase 3: Synthesis
Identify patterns across the ecosystem:
- What capabilities are well-served by existing tools?
- What gaps exist that Options Arena uniquely fills?
- What features do competitors have that Options Arena lacks?
- Are there libraries worth integrating as dependencies?

Before finishing, verify that each category has at least 2 projects listed and that
you have not confused project claims with actual implemented features.
</instructions>

<constraints>
1. Focus on open source projects (MIT, Apache, BSD, GPL licensed) — exclude proprietary SaaS unless they have significant open source components.
2. Distinguish between actively maintained projects and abandoned ones — note last commit date.
3. Report actual capabilities verified from source code or documentation, not just README marketing copy.
4. When comparing to Options Arena, reference specific architectural choices (typed models, async pipeline, AI debate agents) rather than vague statements.
5. Include GitHub URLs for every project mentioned.
6. Organize by category first, not by language or popularity.
7. Note the primary programming language for each project.
8. Flag any projects that could serve as direct dependencies or integration targets.
</constraints>

<output_format>
## Open Source Options Trading Tools — Landscape Report

### Executive Summary
3-5 sentences: overall state of the ecosystem, key themes, where Options Arena fits.

### Category Breakdown

For each of the 8 categories:

#### {Category Name}

| Project | Language | Stars | Last Active | Key Strength | Limitation |
|---------|----------|-------|-------------|--------------|------------|
| [name](url) | Python | ~1.2k | 2025-12 | ... | ... |

**Notable deep-dives** (1-2 paragraphs on the most relevant projects in each category)

### Competitive Positioning
Table comparing Options Arena against the 3-5 closest full-platform competitors across
10+ feature dimensions (pricing, Greeks, scanning, AI, backtesting, UI, data sources, etc.)

### Integration Opportunities
Ranked list of libraries worth evaluating as dependencies or inspiration sources,
with specific rationale for each.

### Gaps & Opportunities
What does the ecosystem lack that Options Arena could uniquely provide or expand into?

### Raw Project List
Alphabetical reference list of all projects mentioned with one-line descriptions.
</output_format>
