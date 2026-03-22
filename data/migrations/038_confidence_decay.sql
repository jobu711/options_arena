-- Migration 038: Add confidence decay columns to strategy_rules
-- Supports confidence tracking, temporal decay, and validation counting.

ALTER TABLE strategy_rules ADD COLUMN confidence REAL DEFAULT 0.5;
ALTER TABLE strategy_rules ADD COLUMN last_validated TEXT;
ALTER TABLE strategy_rules ADD COLUMN validation_count INTEGER DEFAULT 0;
