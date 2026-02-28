-- Add next_earnings column to ticker_scores for earnings date persistence.
ALTER TABLE ticker_scores ADD COLUMN next_earnings TEXT;
