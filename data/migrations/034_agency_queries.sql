-- Migration 034: Agency query persistence
-- Stores agency routing queries, intents, and synthesized responses for audit trail.

CREATE TABLE IF NOT EXISTS agency_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL UNIQUE,
    query_text TEXT NOT NULL,
    desk TEXT,
    tickers_json TEXT,
    intent_json TEXT,
    response_json TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agency_queries_query_id
    ON agency_queries(query_id);

CREATE INDEX IF NOT EXISTS idx_agency_queries_created_at
    ON agency_queries(created_at);
