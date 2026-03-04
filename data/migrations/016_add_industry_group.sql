-- Add industry_group column to ticker_scores for GICS sub-sector classification.
-- Nullable for backward compatibility with existing scan data.
ALTER TABLE ticker_scores ADD COLUMN industry_group TEXT;
ALTER TABLE ticker_scores ADD COLUMN thematic_tags_json TEXT;
