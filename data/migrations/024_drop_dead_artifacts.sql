-- Migration 024: Drop dead DB artifacts
-- intelligence_snapshots: ghost table, zero Python references
-- watchlists/watchlist_tickers: orphaned after watchlist feature removal
-- NOTE: thematic_tags_json column drop removed — column may not exist in all
-- databases (migration 016 was amended after initial deployment). Dead column
-- is harmless in SQLite.

DROP TABLE IF EXISTS intelligence_snapshots;
DROP TABLE IF EXISTS watchlists;
DROP TABLE IF EXISTS watchlist_tickers;
