-- Migration 011: Recommended contracts from scan pipeline
-- Persists Phase 3 contract recommendations with entry prices and Greeks

CREATE TABLE IF NOT EXISTS recommended_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,
    strike TEXT NOT NULL,
    expiration TEXT NOT NULL,
    bid TEXT NOT NULL,
    ask TEXT NOT NULL,
    last TEXT,
    volume INTEGER NOT NULL,
    open_interest INTEGER NOT NULL,
    market_iv REAL NOT NULL,
    exercise_style TEXT NOT NULL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    rho REAL,
    pricing_model TEXT,
    greeks_source TEXT,
    entry_stock_price TEXT NOT NULL,
    entry_mid TEXT NOT NULL,
    direction TEXT NOT NULL,
    composite_score REAL NOT NULL,
    risk_free_rate REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(scan_run_id, ticker, option_type, strike, expiration)
);

CREATE INDEX IF NOT EXISTS idx_rc_scan_run ON recommended_contracts(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_rc_ticker ON recommended_contracts(ticker);
CREATE INDEX IF NOT EXISTS idx_rc_expiration ON recommended_contracts(expiration);
