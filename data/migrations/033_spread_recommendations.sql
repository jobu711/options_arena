-- Migration 033: Spread strategy recommendations
-- Stores multi-leg spread analyses produced by select_strategy() in Phase 3.
-- spread_recommendations holds P&L profile; spread_legs holds individual contracts.

CREATE TABLE IF NOT EXISTS spread_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    spread_type TEXT NOT NULL,
    net_premium TEXT NOT NULL,
    max_profit TEXT NOT NULL,
    max_loss TEXT NOT NULL,
    risk_reward_ratio REAL,
    pop_estimate REAL,
    strategy_rationale TEXT,
    iv_regime TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS spread_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spread_recommendation_id INTEGER NOT NULL REFERENCES spread_recommendations(id),
    leg_index INTEGER NOT NULL,
    contract_ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,
    strike TEXT NOT NULL,
    expiration TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    bid TEXT,
    ask TEXT,
    mid TEXT,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL
);

CREATE INDEX IF NOT EXISTS idx_spread_recommendations_scan_run ON spread_recommendations(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_spread_recommendations_ticker ON spread_recommendations(ticker);
CREATE INDEX IF NOT EXISTS idx_spread_legs_recommendation ON spread_legs(spread_recommendation_id);
