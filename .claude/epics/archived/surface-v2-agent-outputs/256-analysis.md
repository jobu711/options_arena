# Analysis: #256 — Export V2 Section Renderers

## Single stream — 4 new markdown section functions + protocol branching

## Key Files
| File | What to change |
|------|---------------|
| `src/options_arena/reporting/debate_export.py` | 4 new render functions + modify export_debate_markdown() |
| `tests/test_reporting/test_export_v2.py` | NEW — 8 tests |

## Key Pattern
- Follow existing _render_vol_section() pattern
- Branch on result.debate_protocol == "v2"
- V2 heading: "Trend Analysis" (not "Bull Case")
- V2 omits "Bear Case" section
- V1 export unchanged (regression tests)
