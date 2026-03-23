# CLAUDE.md -- Learning Module (`learning/`)

## Purpose

Self-improvement infrastructure: weight tuning for agent vote weights and indicator
composite weights based on historical outcome data. Strategy mining and playbook management.

## Architecture Rules

- **Middle-stack**: Accesses `models/`, `data/`, `scoring/` -- never `services/`, `agents/`, `cli/`, `api/`, `pricing/`
- **Never-raises**: All orchestration functions catch exceptions, log, return empty/fallback results
- **No I/O in algorithms**: Pure computation takes data in, returns results out. Orchestration wrappers handle DB
- **Typed boundaries**: Returns Pydantic models or typed aliases, never raw dicts
