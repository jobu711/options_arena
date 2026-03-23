---
title: "Agency intent routing always defaulted to VOLATILITY desk"
date: 2026-03-22
module: options_arena.agents._routing
problem_type: integration_issue
severity: high
symptoms:
  - "All agency queries route to VOLATILITY desk regardless of content"
  - "'trending bullish' routes to VOLATILITY instead of TREND"
  - "'key risks' routes to VOLATILITY instead of RISK"
  - "'explain what IV rank means' routes to VOLATILITY instead of RESEARCH"
tags:
  - routing
  - intent-classification
  - agency
  - desk-agents
  - keyword-matching
root_cause: "Default fallback was VOLATILITY, keyword matching used exact word boundaries rejecting plurals/stems, and keyword maps had gaps"
---

## Problem

During live smoke test, all 4 agency `ask` queries routed to the VOLATILITY desk:
- "What is the current IV situation for AAPL?" → VOLATILITY (correct)
- "Is MSFT trending bullish or bearish?" → VOLATILITY (wrong, should be TREND)
- "What are the key risks for TSLA options?" → VOLATILITY (wrong, should be RISK)
- "Explain what IV rank means" → VOLATILITY (acceptable but RESEARCH preferred)

## Root Cause

Three compounding issues in `classify_intent()` in `_routing.py`:

1. **Default fallback was VOLATILITY** (line 266-268): When no keywords matched, the
   function defaulted to `DeskType.VOLATILITY` instead of a general-purpose desk.

2. **Exact word-boundary regex** (line 261): `re.search(rf"\b{kw}\b", query)` required
   exact word matches. "trending" didn't match "trend", "risks" didn't match "risk"
   because the trailing `\b` rejected partial stems.

3. **Incomplete keyword maps**: TREND desk lacked "bullish"/"bearish", RISK desk lacked
   "protect"/"downside", RESEARCH desk lacked "explain"/"what is"/"how does".

4. **"vol" keyword collision**: The single-word "vol" in VOLATILITY matched "volume" via
   stem matching, stealing FLOW desk queries about volume activity.

## Solution

Four changes to `_routing.py`:

1. Changed default fallback from `DeskType.VOLATILITY` to `DeskType.RESEARCH` (general-purpose).

2. Changed regex from `\b{kw}\b` (exact boundary) to `\b{kw}` (word-start only) for
   single-word keywords, enabling stem matching ("trending" matches "trend").

3. Multi-word phrases use substring match (`kw in query_lower`) instead of regex,
   fixing "put call ratio", "what is", etc.

4. Expanded keyword maps:
   - TREND: +bullish, bearish, uptrend, downtrend, breakout, support, resistance
   - RISK: +protect, downside, stop loss
   - FLOW: +sweep, block trade
   - FUNDAMENTAL: +eps, balance sheet, profit, growth
   - RESEARCH: +explain, what is, what are, how does, how do
   - VOLATILITY: removed "vol" (collision), added "iv rank", "iv percentile"

## Prevention Rule

When adding keyword-based routing:
- Always test with plural/stem variants of keywords (not just exact forms)
- Default fallback should be the most general-purpose handler, not a domain-specific one
- Short keywords (3 chars or less) need word-boundary on BOTH sides to prevent substring collisions
- Add test cases for each desk with the most natural user phrasing, not just technical terms

## Related

- `src/options_arena/agents/_routing.py` — `classify_intent()`, `_DESK_KEYWORDS`
- `tests/unit/agents/test_routing.py` — `TestClassifyIntentDefaults`
