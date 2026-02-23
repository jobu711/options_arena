-- 001_initial.sql — Options Arena initial schema
--
-- NOTE: schema_version is NOT here — created by Database.connect() before
-- migrations run.  This file only contains business tables.
--
-- All TEXT datetime columns store ISO 8601 UTC format:
--   "2026-02-23T17:55:14+00:00"

-- scan_runs: metadata for completed scan runs
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,              -- ISO 8601 UTC
    completed_at TEXT,                     -- ISO 8601 UTC, NULL if incomplete
    preset TEXT NOT NULL,                  -- ScanPreset enum value ("full", "sp500", "etfs")
    tickers_scanned INTEGER NOT NULL,
    tickers_scored INTEGER NOT NULL,
    recommendations INTEGER NOT NULL
);

-- ticker_scores: scored tickers linked to a scan run
CREATE TABLE IF NOT EXISTS ticker_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    composite_score REAL NOT NULL,
    direction TEXT NOT NULL,               -- SignalDirection enum value ("bullish", "bearish", "neutral")
    signals_json TEXT NOT NULL,            -- IndicatorSignals.model_dump_json()
    UNIQUE(scan_run_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_ticker_scores_scan_id ON ticker_scores(scan_run_id);

-- service_cache: key-value cache with TTL (used by ServiceCache)
-- NOTE: ServiceCache already creates this table itself in cache.py.
-- This migration ensures it exists for fresh databases that skip cache init.
CREATE TABLE IF NOT EXISTS service_cache (
    key TEXT PRIMARY KEY,
    value BLOB,
    expires_at REAL
);

-- v2 placeholders (tables created now, unused in MVP)

-- ai_theses: AI debate results (v2)
CREATE TABLE IF NOT EXISTS ai_theses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    bull_json TEXT,
    bear_json TEXT,
    risk_json TEXT,
    verdict_json TEXT,
    created_at TEXT NOT NULL               -- ISO 8601 UTC
);

-- watchlists: user-defined watchlists (v2)
CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL               -- ISO 8601 UTC
);

-- watchlist_tickers: tickers in a watchlist (v2)
CREATE TABLE IF NOT EXISTS watchlist_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id),
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,                -- ISO 8601 UTC
    UNIQUE(watchlist_id, ticker)
);
