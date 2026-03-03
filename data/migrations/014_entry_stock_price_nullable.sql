-- Make entry_stock_price nullable on recommended_contracts.
-- SQLite lacks ALTER COLUMN, so recreate the table with the constraint removed.
-- Existing data (entry_stock_price = '0') is converted to NULL.

CREATE TABLE IF NOT EXISTS recommended_contracts_new (
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
    delta REAL, gamma REAL, theta REAL, vega REAL, rho REAL,
    pricing_model TEXT,
    greeks_source TEXT,
    entry_stock_price TEXT,
    entry_mid TEXT NOT NULL,
    direction TEXT NOT NULL,
    composite_score REAL NOT NULL,
    risk_free_rate REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(scan_run_id, ticker, option_type, strike, expiration)
);

INSERT INTO recommended_contracts_new
    SELECT id, scan_run_id, ticker, option_type, strike, expiration,
           bid, ask, last, volume, open_interest, market_iv, exercise_style,
           delta, gamma, theta, vega, rho, pricing_model, greeks_source,
           CASE WHEN entry_stock_price = '0' THEN NULL ELSE entry_stock_price END,
           entry_mid, direction, composite_score, risk_free_rate, created_at
    FROM recommended_contracts;

DROP TABLE recommended_contracts;

ALTER TABLE recommended_contracts_new RENAME TO recommended_contracts;

CREATE INDEX IF NOT EXISTS idx_rc_scan_run ON recommended_contracts(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_rc_ticker ON recommended_contracts(ticker);
CREATE INDEX IF NOT EXISTS idx_rc_expiration ON recommended_contracts(expiration);
