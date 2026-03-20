-- Add weight_type and accuracy_at_time columns to auto_tune_weights table.
-- Supports discriminating between vote weights (agent) and indicator weights.
-- DEFAULT 'vote' ensures existing rows are backward-compatible.
ALTER TABLE auto_tune_weights ADD COLUMN weight_type TEXT DEFAULT 'vote';
ALTER TABLE auto_tune_weights ADD COLUMN accuracy_at_time REAL;
CREATE INDEX IF NOT EXISTS idx_atw_weight_type ON auto_tune_weights(weight_type);
