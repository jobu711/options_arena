-- Add sector and company_name columns to ticker_scores
-- Nullable for backward compatibility with existing scan data.
ALTER TABLE ticker_scores ADD COLUMN sector TEXT;
ALTER TABLE ticker_scores ADD COLUMN company_name TEXT;
