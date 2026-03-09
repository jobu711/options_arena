CREATE TABLE IF NOT EXISTS auto_tune_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    manual_weight REAL NOT NULL,
    auto_weight REAL NOT NULL,
    brier_score REAL,
    sample_size INTEGER NOT NULL,
    window_days INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atw_created ON auto_tune_weights(created_at);
