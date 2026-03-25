---
name: intel-wave6-synthesis-enhancement
description: Enhance synthesis agent prompt with market regime, event risk, and cross-domain correlation sections
status: backlog
created: 2026-03-24T15:48:29Z
effort: S
---

# PRD: intel-wave6-synthesis-enhancement

## Executive Summary

Enhance the synthesis agent's system prompt to incorporate intelligence desk assessments into recommendation generation. Add guidance for market regime weighting, event risk invalidation, and cross-domain correlation patterns. This is a prompt-only change — no code modifications needed beyond `agents/prompts/synthesis.py`.

## Problem Statement

### What problem are we solving?

The synthesis agent now receives 7 desk assessments (including the new Intelligence desk), but its prompt has no guidance on how to integrate macro regime context into position sizing, confidence, or risk assessment. Without explicit prompt engineering, the synthesis agent may underweight or ignore the intelligence desk's input.

### Why is this important now?

Depends on Wave 5 (intelligence desk agent). Once the intelligence desk produces assessments, the synthesis agent needs to know how to use them. This is the final link that makes intelligence data flow through to the recommendation output.

## Requirements

### Functional Requirements

#### FR-1: Market Regime Integration Section

Add to `SYNTHESIS_SYSTEM_PROMPT` in `agents/prompts/synthesis.py`:

```
## Market Regime Integration

When an Intelligence desk assessment is present:
1. Weight the market regime classification heavily for position sizing
2. In risk-off regimes, reduce position_size_pct by at least 30%
3. Cross-validate: if Intelligence says risk-off but 4+ desks are bullish,
   note the divergence and reduce confidence
4. Event catalysts from Intelligence desk override pure technical signals
   when events are within 5 trading days
5. Supply chain stress (elevated GSCPI) + energy price spikes = inflation hedge bias
```

#### FR-2: Event Risk Invalidation Section

```
## Event Risk Invalidation

If Intelligence desk flags CRITICAL events:
- Cap confidence at 0.6 regardless of desk agreement
- Require explicit stop_loss (never None)
- Note the event risk in risk_assessment field
- Consider shorter DTE to avoid event exposure
```

#### FR-3: Cross-Domain Correlation Section

```
## Cross-Domain Correlation

When multiple desks agree AND intelligence confirms:
- Trend bullish + Fundamental bullish + Intelligence expansionary = high confidence
- Vol elevated + Risk cautious + Intelligence risk-off = reduce size, buy protection
- Flow unusual + Intelligence event catalysts = potential information-driven activity
```

### Non-Functional Requirements

- Prompt changes only — no code changes beyond the prompt file
- Backward compatible — when IntelligenceAssessment is absent from assessments list, these sections are inert (no errors, no behavioral change)
- Total prompt length stays within model context limits

## Success Criteria

- Synthesis agent with 7 assessments (including Intelligence) produces recommendations that reference macro regime
- Synthesis agent with 6 assessments (no Intelligence) behaves identically to before
- Manual review: recommendations in risk-off regimes show reduced confidence and position size
- No regressions in existing synthesis tests

## Out of Scope

- Desk agent prompt changes (each desk has its own prompt, unchanged)
- New tools for synthesis agent
- Output model changes (PositionRecommendation fields unchanged)

## Dependencies

- **Wave 5** (intel-wave5-desk-agent) — IntelligenceAssessment must be produced

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/agents/prompts/synthesis.py` | Modify — add 3 new sections to SYNTHESIS_SYSTEM_PROMPT |
