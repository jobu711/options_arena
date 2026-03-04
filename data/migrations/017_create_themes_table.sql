-- Create themes table for ETF-based thematic screening snapshots.
CREATE TABLE IF NOT EXISTS themes (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    etf_source_json TEXT NOT NULL DEFAULT '[]',
    tickers_json TEXT NOT NULL DEFAULT '[]',
    ticker_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
