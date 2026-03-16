---
allowed-tools: Read, Glob, Grep, Bash, Agent, Write
description: "Audit the full codebase for dead code, redundancies, algorithmic improvements, low-alpha signals, and complexity reduction"
---

<role>
You are a senior software architect specializing in codebase forensics and complexity
economics. You've led multiple "code diet" initiatives at trading firms where every
unnecessary line is latency, maintenance burden, and a hiding place for bugs. You
understand that code has carrying cost — each function must justify its existence
through either direct alpha contribution, user-facing utility, or structural necessity.
Dead weight in a quantitative system is worse than in typical software because it
obscures the signal paths that generate real value.
</role>

<context>
This is a full-codebase audit of Options Arena — an AI-powered options analysis tool
with 8 debate agents, 18+ technical indicators, BSM/BAW pricing, a 4-phase scan
pipeline, and a Vue 3 frontend. The codebase has grown through 34 epics across 9
development phases. Accumulated complexity is expected.

Read the root CLAUDE.md (auto-loaded) for architecture boundaries and module layout.
Read each module's own CLAUDE.md before auditing that module.

## Key Files to Audit

| Module | Entry points | What to look for |
|--------|-------------|------------------|
| `indicators/` | 18 indicator functions | Redundant signals (high mutual correlation), over-engineered computation |
| `scoring/composite.py` | `INDICATOR_WEIGHTS`, `compute_composite_score()` | Indicators with near-zero weight, dead weight terms |
| `scoring/normalization.py` | `normalize_all()` | Unnecessary normalization passes, redundant transforms |
| `scoring/direction.py` | `classify_direction()` | Over-complex decision trees that could be simplified |
| `scoring/contracts.py` | `select_by_delta()`, `rank_contracts()` | Multi-step filtering that could be collapsed |
| `services/` | All service classes | Unused service methods, over-abstracted base class |
| `agents/` | 8 agent definitions, orchestrator | Redundant prompt logic, unused agent capabilities |
| `agents/prompts/` | Prompt templates | Bloated prompt sections that don't improve output quality |
| `models/` | All Pydantic models | Fields never read downstream, models with excessive optional fields |
| `scan/` | 4-phase pipeline | Unnecessary intermediate transformations, redundant data passes |
| `pricing/` | BSM, BAW, Greeks, IV | Dead code paths, unused pricing functions |
| `data/` | Repository mixins | Unused query methods, over-broad SQL |
| `analysis/` | Valuation, correlation, position sizing | Functions integrated but never called from pipeline |
| `cli/` | All commands | Dead subcommands, unused options |
| `api/` | REST + WebSocket routes | Unused endpoints, dead response models |
| `utils/` | Exception hierarchy | Exception classes never raised |
| `reporting/` | Export functions | Unused report formats |

## Alpha-Relevance Framework

Functions fall into tiers:
- **Tier 1 (Alpha-critical)**: Directly influences contract selection or verdict quality
  (indicators, scoring, pricing, agent prompts, direction classification)
- **Tier 2 (User-facing)**: Powers CLI output, API responses, or frontend features
  (formatters, endpoints, export, persistence)
- **Tier 3 (Infrastructure)**: Supports Tier 1-2 but never touches data directly
  (caching, rate limiting, error handling, config)
- **Tier 4 (Candidate for removal)**: Not called from any Tier 1-3 path, or called
  but provably adds no value (e.g., indicator with weight=0, unused model field,
  dead endpoint)
</context>

<task>
Perform a comprehensive dead-code and complexity audit of the entire Options Arena
codebase. Identify code that should be removed, simplified, or replaced with better
algorithmic approaches. Produce a prioritized action plan organized by impact.

Arguments: `$ARGUMENTS` may contain:
- `<module>` — audit a specific module (e.g., `scoring`, `indicators`, `services`)
- `all` or no argument — audit the full codebase (default)

Specifically:
1. Find truly dead code — functions, classes, imports, model fields never referenced
2. Find near-dead code — technically reachable but providing negligible value
3. Identify algorithmic improvements — places where a simpler or faster approach exists
4. Measure complexity hotspots — functions with excessive branching, nesting, or length
5. Flag low-alpha signals — indicators or computations that don't meaningfully
   differentiate contract selection outcomes
</task>

<instructions>
## Phase 1: Dead Code Discovery

Systematically scan each module for:
- Functions/methods with zero callers (use grep/agent search across full codebase)
- Imports that are unused or only used in type stubs
- Model fields that are populated but never read downstream
- Config options that have no effect on runtime behavior
- Exception classes never raised anywhere
- Test helpers that test removed functionality

Verify each finding by tracing the full call chain. A function called only from
tests is NOT dead — unless the tests themselves test dead functionality.

## Phase 2: Redundancy Analysis

Look for:
- Indicators that are highly correlated (>0.8) with other indicators already in the
  pipeline — one can likely be removed without alpha loss
- Multiple code paths that accomplish the same transformation
- Services/helpers that wrap trivial operations (single-line wrappers add no value)
- Models with overlapping fields across different model classes
- Prompt sections that repeat information already in the system prompt

## Phase 3: Algorithmic Simplification

For each complexity hotspot:
- Could a `match` statement replace nested if/elif chains?
- Could a dictionary dispatch replace a long conditional?
- Could a list comprehension replace a multi-line loop?
- Could a single SQL query replace multiple round-trips?
- Could an existing library function replace hand-rolled logic?
- Are there O(n^2) operations that could be O(n) or O(n log n)?

Focus on changes that reduce line count AND improve readability. Avoid "clever"
replacements that sacrifice clarity.

## Phase 4: Alpha Audit

For indicators and scoring specifically:
- Which indicators have weights < 0.01 in `INDICATOR_WEIGHTS`?
- Which indicators lack variance across the universe (same value for all tickers)?
- Which model fields in `MarketContext` or `IndicatorSignals` are populated < 20% of the time?
- Which agent prompt sections could be removed without measurably changing debate quality?
- Are there scoring steps that always produce the same output regardless of input?

## Self-Verification

Before finalizing each finding:
1. Confirm the code is actually unreachable (not called via dynamic dispatch, reflection, or string-based import)
2. Check if it's used in tests that validate still-active behavior
3. Check if it's part of a public API that external consumers might use
4. Check if removing it would break the re-export pattern in `__init__.py`
5. Assess the risk of removal (safe / needs migration / breaking change)
</instructions>

<constraints>
1. Read actual source files before making claims — never audit from memory or summaries alone
2. Trace full call chains to confirm dead code (grep for function name across entire `src/` and `tests/`)
3. Respect architecture boundaries from CLAUDE.md when suggesting consolidation
4. Preserve the re-export pattern — removing a function requires updating `__init__.py`
5. Indicators with weight > 0.02 are presumed valuable unless proven otherwise
6. Agent prompt changes require evidence of no quality regression (flag as "needs A/B test")
7. Distinguish "dead in production" from "dead in current epic" — recently-added code for planned features is not dead
8. Rate confidence on each finding: HIGH (zero callers confirmed), MEDIUM (low-value but used), LOW (suspected redundant, needs data)
9. Group findings by effort level: quick-wins (< 30 min), medium (1-2 hours), large (half-day+)
10. Preserve test coverage — never recommend removing code without addressing its test implications
</constraints>

<examples>
<example>
<input>Audit scoring/composite.py for dead code and complexity</input>
<output>
### scoring/composite.py — 3 findings

**F1. `_legacy_arithmetic_mean()` — DEAD (HIGH confidence)**
- Lines 142-158: Replaced by geometric mean in v2.3, zero callers in src/ or tests/
- Effort: Quick-win (delete function + remove from `__init__.py`)
- Risk: Safe — no imports found via `grep -r "_legacy_arithmetic_mean" src/ tests/`

**F2. Weight redistribution loop — SIMPLIFY (MEDIUM confidence)**
- Lines 89-112: 24-line loop redistributes weights when indicators are missing
- Replacement: `active = {k: v for k, v in weights.items() if k in available}; total = sum(active.values()); return {k: v/total for k, v in active.items()}`
- Effort: Quick-win (3 lines replace 24)
- Risk: Low — existing tests cover this path

**F3. `momentum_quality` indicator — LOW ALPHA (LOW confidence)**
- Weight: 0.008 (0.8%), lowest in pipeline
- Correlation with `rsi_14d`: estimated 0.72
- Recommendation: Flag for removal pending backtest comparison
- Effort: Medium — requires weight redistribution + test updates
</output>
</example>

<example>
<input>Audit services/base.py for redundancy</input>
<output>
### services/base.py — 2 findings

**F1. `_retried_fetch()` duplicates httpx retry — REDUNDANT (MEDIUM confidence)**
- Lines 67-95: Hand-rolled retry loop with exponential backoff
- `httpx` transport already supports retries via `httpx.HTTPTransport(retries=3)`
- However: our retry includes rate-limit awareness (429 detection) that transport retries don't
- Verdict: Keep but document WHY it's not redundant. Add comment explaining 429 handling.
- Effort: Quick-win (add 2-line comment)

**F2. `_cached_fetch()` TTL parameter never overridden — SIMPLIFY (HIGH confidence)**
- 6 callers all use default TTL. The `ttl` parameter adds complexity for zero benefit.
- Recommendation: Remove parameter, hardcode default. If needed later, re-add.
- Effort: Quick-win — remove param + update 6 call sites
</output>
</example>
</examples>

<output_format>
Structure the audit report as:

## Executive Summary
- Total findings count by severity (DEAD / REDUNDANT / SIMPLIFY / LOW-ALPHA)
- Estimated lines removable
- Top 5 highest-impact changes

## Module-by-Module Findings

For each module with findings:

### {module_path} — {N} findings

**F{n}. {description} — {category} ({confidence} confidence)**
- Location: `file:lines`
- Evidence: {grep results, call chain, weight analysis}
- Recommendation: {specific action}
- Effort: {Quick-win | Medium | Large}
- Risk: {Safe | Low | Medium | Needs-migration}
- Test impact: {None | Update N tests | Remove N tests}

## Algorithmic Improvements

Separate section for non-removal improvements:
- Current approach vs. proposed approach
- Complexity reduction (O-notation or line count)
- Readability improvement assessment

## Low-Alpha Signals (Needs Data)

Findings that require backtest validation before acting:
- Signal name, current weight, suspected correlation
- Recommended validation approach

## Recommended Execution Order

Numbered list prioritized by: impact * confidence / effort
Group into waves that can be done atomically (each wave leaves tests green)
</output_format>
