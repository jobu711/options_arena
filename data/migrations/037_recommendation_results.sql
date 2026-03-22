-- Migration 037: recommendation_results table + recommendation_protocol column
-- Supports the unified agent system recommendation pipeline

CREATE TABLE IF NOT EXISTS recommendation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    scan_run_id INTEGER,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    recommended_contract TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    entry_criteria TEXT NOT NULL,
    exit_criteria TEXT NOT NULL,
    stop_loss TEXT,
    take_profit TEXT,
    position_size_pct REAL NOT NULL,
    risk_reward_ratio REAL NOT NULL,
    recommended_strategy TEXT,
    summary TEXT NOT NULL,
    key_factors_json TEXT NOT NULL,
    risk_assessment TEXT NOT NULL,
    agent_agreement_score REAL,
    dissenting_desks_json TEXT NOT NULL DEFAULT '[]',
    assessments_json TEXT NOT NULL,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    citation_density REAL NOT NULL DEFAULT 0.0,
    position_rationale TEXT NOT NULL DEFAULT '',
    strategy_rationale TEXT NOT NULL DEFAULT '',
    max_loss_estimate TEXT NOT NULL DEFAULT '',
    model_used TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_results_ticker
    ON recommendation_results(ticker);
CREATE INDEX IF NOT EXISTS idx_recommendation_results_created_at
    ON recommendation_results(created_at DESC);

ALTER TABLE agent_predictions ADD COLUMN recommendation_protocol TEXT NOT NULL DEFAULT 'debate_v1';
