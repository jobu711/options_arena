---
issue: 158
stream: Debate Protocol Wiring
agent: general-purpose
started: 2026-02-28T18:56:13Z
status: in_progress
---

# Stream B: Debate Protocol Wiring

## Scope
Wire run_debate_v2() into CLI debate command, API debate routes, and reporting export.
Render ExtendedTradeThesis fields (contrarian dissent, agreement score, dimensional
scores) in all output formats.

## Files
- src/options_arena/cli/commands.py
- src/options_arena/cli/rendering.py
- src/options_arena/api/routes/debate.py
- src/options_arena/api/routes/scan.py
- src/options_arena/api/schemas.py
- src/options_arena/reporting/debate_export.py

## Progress
- Starting implementation
