-- Add dimensional scoring columns to ticker_scores.
-- Nullable for backward compatibility with existing scan data.
ALTER TABLE ticker_scores ADD COLUMN dimensional_scores_json TEXT;
ALTER TABLE ticker_scores ADD COLUMN direction_confidence REAL;
ALTER TABLE ticker_scores ADD COLUMN market_regime TEXT;
