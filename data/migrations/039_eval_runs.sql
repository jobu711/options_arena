-- Migration 039: Eval runs and definitions for agent quality measurement.
-- Part of agent-infra-eval-harness epic (Issue #657).

CREATE TABLE IF NOT EXISTS eval_definitions (
    name TEXT PRIMARY KEY,
    eval_type TEXT NOT NULL,
    target_desk TEXT,
    description TEXT NOT NULL,
    grader_type TEXT NOT NULL,
    market_context_fixture TEXT NOT NULL,
    expected_direction TEXT,
    expected_confidence_min REAL,
    expected_confidence_max REAL,
    custom_assertions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    passed INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    successes INTEGER NOT NULL,
    model_used TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (eval_name) REFERENCES eval_definitions(name)
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_name ON eval_runs(eval_name);
CREATE INDEX IF NOT EXISTS idx_eval_runs_timestamp ON eval_runs(timestamp DESC);
