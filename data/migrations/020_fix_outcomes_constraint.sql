-- Migration 020: Recreate contract_outcomes with correct UNIQUE constraint.
-- SQLite does not support ALTER TABLE DROP/ADD CONSTRAINT, so we use
-- the standard table-recreation pattern:
--   1. Create new table with correct schema
--   2. Copy data (INSERT OR IGNORE deduplicates)
--   3. Drop old table
--   4. Rename new table

CREATE TABLE IF NOT EXISTS contract_outcomes_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommended_contract_id INTEGER NOT NULL REFERENCES recommended_contracts(id),
    exit_stock_price TEXT,
    exit_contract_mid TEXT,
    exit_contract_bid TEXT,
    exit_contract_ask TEXT,
    exit_date TEXT,
    stock_return_pct REAL,
    contract_return_pct REAL,
    is_winner INTEGER,
    holding_days INTEGER,
    dte_at_exit INTEGER,
    collection_method TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(recommended_contract_id, holding_days)
);

INSERT OR IGNORE INTO contract_outcomes_new
    SELECT * FROM contract_outcomes;

DROP TABLE IF EXISTS contract_outcomes;

ALTER TABLE contract_outcomes_new RENAME TO contract_outcomes;

CREATE INDEX IF NOT EXISTS idx_co_rec_id ON contract_outcomes(recommended_contract_id);
