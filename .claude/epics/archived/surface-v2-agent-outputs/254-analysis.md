# Analysis: #254 — API Layer V2

## Single stream — extend DebateResultDetail, parse v2 JSON, pass to save_debate()

## Key Files
| File | What to change |
|------|---------------|
| `src/options_arena/api/schemas.py` | Add 5 fields to DebateResultDetail |
| `src/options_arena/api/routes/debate.py` | Parse v2 JSON in get_debate(), pass v2 to save_debate() in _run_debate_background() |
| `tests/test_api/test_debate_routes_v2.py` | NEW — 5 tests |

## Key Points
- DebateResultDetail fields use dict[str, object] | None (not model types — avoids circular imports)
- Parse with json.loads() since these cross the API serialization boundary
- get_debate(): flow_response=json.loads(row.flow_json) if row.flow_json else None
- _run_debate_background(): pass v2 fields from DebateResult to save_debate()
