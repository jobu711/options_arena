# Solution: Database Column Name Mismatch in New Queries

## Problem

New SQL queries reference column names that don't exist in the schema, causing
`sqlite3.OperationalError` at runtime. The never-raises wrapper masks the error
by returning empty results, making the feature silently non-functional.

## Root Cause

When writing `get_outcome_signal_pairs()` in `data/_analytics.py`, the column
`co.pnl_pct` was used instead of the actual column name `co.contract_return_pct`
from migration 012. The error was not caught by unit tests because they used
mocked repositories that bypass real SQL execution.

## Detection

Caught by the 7-agent full audit during release prep — both the OA Python
reviewer and bug auditor independently flagged it. The OA reviewer cross-referenced
the SQL column names against the migration files.

## Fix

Replace all occurrences of `pnl_pct` with `contract_return_pct` in the SQL query
and the Python `r["pnl_pct"]` dict access.

## Prevention

1. **Always verify column names against migrations** before writing new SQL queries.
   Run `grep -r "column_name" data/migrations/` to confirm.
2. **Integration tests with real `:memory:` DB** catch schema mismatches that unit
   tests with mocked repos miss. Add at least one integration test per new query.
3. **The full-audit step in release-prep** is the safety net — always run it.

## Applies To

- Any new SQL query in `data/_analytics.py` or `data/_debate.py`
- Any time a new join references columns from tables defined in older migrations
