# Analysis: #770 — Attribution CLI Command and API Endpoint

## Streams

### Stream A: CLI command in agency.py
**Files:** `src/options_arena/cli/agency.py` (MODIFY)
**Work:**
1. Add `@learn_app.command("attribution")` with --window-days and --source params
2. Add `_run_attribution()` async helper
3. Rich table for source accuracy + condition breakdown

### Stream B: API endpoint in analytics.py
**Files:** `src/options_arena/api/routes/analytics.py` (MODIFY)
**Work:**
1. Add `GET /attribution` endpoint with rate limiting
2. Accept window_days (7-365) and optional source filter
3. Return AttributionReport JSON

### Stream C: Unit tests
**Files:** `tests/unit/cli/test_learn_attribution.py` (NEW), `tests/unit/api/test_attribution_endpoint.py` (NEW)

## Key Patterns
- CLI: sync Typer command + asyncio.run() wrapper (see existing learn status command)
- API: @limiter.limit("60/minute"), Request param, Depends(get_repo)
- Both call compute_attribution() from prediction_ledger.py
- Both use repo.get_predictions(window_days, source) for data retrieval

## Dependencies
- #766: compute_attribution() must exist ✅ (completed)
