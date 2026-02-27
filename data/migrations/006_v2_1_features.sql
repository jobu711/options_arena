-- 006_v2_1_features.sql — v2.1 Close the Loop features
--
-- 1. Add description column to watchlists
-- 2. Add updated_at column to watchlists
-- 3. Create recommended_contracts table for persisting scan contract recommendations

-- Add description column to watchlists (nullable, existing rows get NULL)
ALTER TABLE watchlists ADD COLUMN description TEXT;

-- Add updated_at column to watchlists (default to created_at for existing rows)
ALTER TABLE watchlists ADD COLUMN updated_at TEXT;

-- recommended_contracts: persisted contract recommendations from scan pipeline
CREATE TABLE IF NOT EXISTS recommended_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,              -- "call" or "put"
    strike TEXT NOT NULL,                   -- Decimal as TEXT for precision
    expiration TEXT NOT NULL,               -- ISO 8601 date
    bid TEXT,                               -- Decimal as TEXT
    ask TEXT,                               -- Decimal as TEXT
    volume INTEGER,
    open_interest INTEGER,
    implied_volatility REAL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    score REAL,                             -- contract recommendation score
    created_at TEXT NOT NULL                -- ISO 8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_recommended_contracts_scan_id ON recommended_contracts(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_recommended_contracts_ticker ON recommended_contracts(ticker);
