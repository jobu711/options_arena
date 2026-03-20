# CLAUDE.md — Learning Module (`learning/`)

## Purpose

Self-improvement infrastructure for Options Arena. Phase 1: weight tuning for both
agent vote weights and indicator composite weights based on historical outcome data.

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Middle-stack** | Accesses `models/`, `data/`, `scoring/` — never `services/`, `agents/` instances, or `cli/` |
| **Never-raises** | All orchestration functions catch exceptions, log, and return empty/fallback results |
| **No I/O in algorithms** | Pure computation functions take data in, return results out. Orchestration wrappers handle DB |
| **Typed boundaries** | Returns Pydantic models or typed aliases, never raw dicts |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | `services/` (no data fetching) |
| `data/` (Repository for persistence) | `agents/` instances (no agent imports) |
| `scoring/composite` (INDICATOR_WEIGHTS) | `cli/`, `api/`, `reporting/` |
| stdlib: `math`, `logging`, `statistics` | `pricing/`, `indicators/` |

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports public API |
| `weight_tuner.py` | Vote weight tuning (relocated) + indicator weight tuning |
| `CLAUDE.md` | This file — module conventions |
