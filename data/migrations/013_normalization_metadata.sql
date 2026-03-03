CREATE TABLE IF NOT EXISTS normalization_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    indicator_name TEXT NOT NULL,
    ticker_count INTEGER NOT NULL,
    min_value REAL, max_value REAL,
    median_value REAL, mean_value REAL, std_dev REAL,
    p25 REAL, p75 REAL,
    created_at TEXT NOT NULL,
    UNIQUE(scan_run_id, indicator_name)
);
CREATE INDEX IF NOT EXISTS idx_nm_scan_run ON normalization_metadata(scan_run_id);
