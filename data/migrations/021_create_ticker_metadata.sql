-- Migration 021: Create ticker_metadata table for cached GICS classification.
--
-- Stores sector, industry group, market cap tier, and company name per ticker.
-- Used by the metadata index to avoid repeated lookups during scan pipeline.

CREATE TABLE IF NOT EXISTS ticker_metadata (
    ticker TEXT PRIMARY KEY,
    sector TEXT,
    industry_group TEXT,
    market_cap_tier TEXT,
    company_name TEXT,
    raw_sector TEXT NOT NULL DEFAULT 'Unknown',
    raw_industry TEXT NOT NULL DEFAULT 'Unknown',
    last_updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticker_metadata_sector ON ticker_metadata(sector);
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_industry_group ON ticker_metadata(industry_group);
