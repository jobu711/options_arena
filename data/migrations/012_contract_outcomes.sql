CREATE TABLE IF NOT EXISTS contract_outcomes (
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
CREATE INDEX IF NOT EXISTS idx_co_rec_id ON contract_outcomes(recommended_contract_id);
