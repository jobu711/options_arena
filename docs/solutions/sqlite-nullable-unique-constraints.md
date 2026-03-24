# SQLite Nullable UNIQUE Constraints Are Silently Unenforced

## Problem

SQLite treats every `NULL` as distinct from every other `NULL`. A table-level
`UNIQUE(recommendation_id, source)` constraint does nothing when `recommendation_id`
is `NULL` — SQLite considers `(NULL, 'desk_trend')` and `(NULL, 'desk_trend')` as
distinct rows. Duplicate predictions accumulate without detection.

This is standard SQL behavior (ISO SQL says NULL != NULL), but surprises developers
used to PostgreSQL's `NULLS NOT DISTINCT` option.

## Solution

Replace table-level UNIQUE constraints on nullable columns with **partial unique indexes**:

```sql
-- Table-level UNIQUE does nothing when FK is NULL:
UNIQUE(recommendation_id, source)  -- BROKEN for nullable recommendation_id

-- Partial unique index enforces uniqueness only on non-NULL rows:
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_rec_source_unique
    ON predictions(recommendation_id, source)
    WHERE recommendation_id IS NOT NULL;
```

Keep the table-level UNIQUE as documentation, but rely on the partial index for enforcement.

## When This Applies

Any table with:
- A nullable foreign key column
- A UNIQUE constraint involving that nullable column
- Multiple rows expected to have NULL in the FK column

## Discovery

Found by db-auditor during epic/recommendation-learning-foundation release prep.
The `predictions` table has dual nullable FKs (`recommendation_id`, `scan_run_id`)
with UNIQUE constraints on both — both needed partial unique indexes.
