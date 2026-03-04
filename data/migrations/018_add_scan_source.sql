-- 018: Add source column to scan_runs for provenance tracking.
-- Distinguishes manual scans from watchlist-originated scans.
ALTER TABLE scan_runs ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';
