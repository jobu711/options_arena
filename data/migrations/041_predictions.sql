-- Migration 041: predictions table for recommendation-learning prediction ledger
-- Records intermediate decisions (scan direction, per-desk calls, synthesis) for
-- attribution scoring against outcomes. Dual FK to recommendation_results and scan_runs.

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER REFERENCES recommendation_results(id),
    scan_run_id INTEGER REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    predicted_direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    adx REAL,
    iv_rank REAL,
    atr_pct REAL,
    rsi REAL,
    was_correct INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(recommendation_id, source),
    UNIQUE(scan_run_id, ticker, source)
);

CREATE INDEX IF NOT EXISTS idx_predictions_source
    ON predictions(source);
CREATE INDEX IF NOT EXISTS idx_predictions_was_correct
    ON predictions(was_correct) WHERE was_correct IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_predictions_rec_id
    ON predictions(recommendation_id) WHERE recommendation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_predictions_scan_id
    ON predictions(scan_run_id) WHERE scan_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_predictions_ticker
    ON predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at
    ON predictions(created_at);

-- Partial unique indexes for nullable FK columns (SQLite treats NULL as distinct
-- in regular UNIQUE constraints, so the table-level UNIQUE on nullable FKs is
-- insufficient).
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_rec_source_unique
    ON predictions(recommendation_id, source) WHERE recommendation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_scan_ticker_source_unique
    ON predictions(scan_run_id, ticker, source) WHERE scan_run_id IS NOT NULL;
