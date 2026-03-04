# Analysis: #250 — Repository Layer V2 Persistence

## Single stream — extends DebateRow, save_debate(), _row_to_debate_row()

## Key Files
| File | What to change |
|------|---------------|
| `src/options_arena/data/repository.py` | Extend DebateRow, save_debate(), _row_to_debate_row() |
| `tests/unit/data/test_repository_v2.py` | NEW — 5 round-trip tests |

## Pattern: Follow existing vol_json/rebuttal_json pattern
- DebateRow dataclass gets 5 new fields with defaults
- save_debate() gets 5 new optional params, serializes via model_dump_json()
- _row_to_debate_row() extracts 5 new columns from sqlite3.Row
- Migration 019 must be applied before tests run (test fixtures handle this)
