-- Migration 010: Intelligence snapshots for historical storage
-- Stores serialized intelligence data for trend analysis

CREATE TABLE IF NOT EXISTS intelligence_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_intelligence_ticker_category
    ON intelligence_snapshots(ticker, category);

CREATE INDEX IF NOT EXISTS idx_intelligence_fetched_at
    ON intelligence_snapshots(fetched_at);
