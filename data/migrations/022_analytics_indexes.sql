-- Analytics query performance indexes
CREATE INDEX IF NOT EXISTS idx_co_exit_date ON contract_outcomes(exit_date);
CREATE INDEX IF NOT EXISTS idx_rc_created_at ON recommended_contracts(created_at);
CREATE INDEX IF NOT EXISTS idx_ts_scan_direction ON ticker_scores(scan_run_id, direction);
