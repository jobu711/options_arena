-- 002_debate_columns.sql — Add debate metadata columns to ai_theses
--
-- Extends the v2 placeholder table with columns needed by the debate system.
-- Also makes scan_run_id nullable (standalone debates have no scan context)
-- and adds an index on ticker for get_debates_for_ticker() queries.

-- Add metadata columns
ALTER TABLE ai_theses ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN model_name TEXT DEFAULT '';
ALTER TABLE ai_theses ADD COLUMN duration_ms INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN is_fallback INTEGER DEFAULT 0;

-- Recreate ai_theses with nullable scan_run_id (SQLite has no ALTER COLUMN)
CREATE TABLE IF NOT EXISTS ai_theses_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    bull_json TEXT,
    bear_json TEXT,
    risk_json TEXT,
    verdict_json TEXT,
    total_tokens INTEGER DEFAULT 0,
    model_name TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    is_fallback INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

INSERT INTO ai_theses_new SELECT * FROM ai_theses;
DROP TABLE ai_theses;
ALTER TABLE ai_theses_new RENAME TO ai_theses;

-- Index on ticker for get_debates_for_ticker() query performance
CREATE INDEX IF NOT EXISTS idx_ai_theses_ticker ON ai_theses(ticker);
