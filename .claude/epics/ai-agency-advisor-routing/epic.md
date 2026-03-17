---
name: ai-agency-advisor-routing
status: backlog
created: 2026-03-17T14:37:45Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 2
dependencies: [ai-agency-desk-foundation]
parallelizable_with: [ai-agency-all-desks]
github: [Will be updated when synced to GitHub]
---

# Epic 2: Advisor + Routing

## Overview

Add the Advisor agent for intent classification, multi-desk query routing, response synthesis, and query persistence. Build API endpoints, CLI commands, and WebSocket streaming for agency interaction.

## Architecture Decisions

- Rule-based V1 routing: `classify_intent(query: str) -> QueryIntent` in `_routing.py` — keyword matching + regex ticker extraction, no LLM call
- Multi-desk dispatch: `asyncio.gather(*desk_coroutines, return_exceptions=True)` for parallel desk execution
- Response synthesis: Advisor combines `DeskResponse` list into `AgencyResponse` with merged citations
- Query persistence: `agency_queries` table (migration 034) for audit trail
- Never-raises: `run_desk_query()` catches all errors → returns error `DeskResponse`

## Technical Approach

### Advisor & Routing
- `agents/advisor.py` — `classify_intent()` pure Python function. Keyword → desk mapping, `$TICKER` regex extraction, query type inference
- `agents/_routing.py` — `run_agency_query()` orchestrator: classify → dispatch → synthesize → persist
- `AgencyResponse` model: query_id, desk_responses, synthesis, citations, confidence

### Data Layer
- `data/_agency.py` — `AgencyMixin` with `save_agency_query()`, `get_agency_query()`, `list_agency_queries()`
- Migration 034: `agency_queries` table (query_id, query_text, desk, tickers_json, response_json, confidence, created_at)

### API & CLI
- `api/routes/agency.py`: `POST /api/agency/query`, `GET /api/agency/query/{id}`, `WS /api/agency/ws`
- `cli/agency.py`: `agency ask "question"`, `agency ask --desk volatility "question"`
- WebSocket bridge: reuse `WebSocketProgressBridge` pattern for streaming desk responses
- Operation mutex: agency queries share the existing `asyncio.Lock` (409 if scan/debate running)

### Frontend
- `AgencyChat.vue` — Chat interface with message history, desk attribution, citation display

## Task Breakdown Preview

- [ ] Advisor intent classification + routing orchestrator
- [ ] AgencyMixin + migration 034 (query persistence)
- [ ] API endpoints + WebSocket bridge + CLI commands
- [ ] AgencyChat.vue frontend component

## Dependencies

- Epic 1 (Desk Foundation) — `DeskDeps`, `FunctionToolset` builders, vol/risk desks must exist

## Success Criteria

- Natural language queries route to correct desk(s) via keyword classification
- Multi-desk queries execute in parallel and synthesize into single response
- Queries persisted in SQLite for audit trail
- API endpoints return proper AgencyResponse
- CLI `agency ask` works end-to-end
- ~25+ new tests

## Estimated Effort

3-4 issues, ~2 implementation sessions
