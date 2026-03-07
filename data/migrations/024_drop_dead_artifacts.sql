-- Migration 024: Drop dead DB artifacts
-- intelligence_snapshots: ghost table, zero Python references
-- thematic_tags_json: dead column, zero production references
-- watchlists/watchlist_tickers: orphaned after watchlist feature removal

DROP TABLE IF EXISTS intelligence_snapshots;
ALTER TABLE ticker_scores DROP COLUMN thematic_tags_json;
DROP TABLE IF EXISTS watchlists;
DROP TABLE IF EXISTS watchlist_tickers;
