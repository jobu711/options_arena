-- Migration 026: Remove vestigial v2 naming
-- The v1 debate protocol has been eliminated; v2 is the only path.
-- Rename risk_v2_json → risk_assessment_json (can't use risk_json — already exists as v1 column).
-- Normalize debate_protocol values.

ALTER TABLE ai_theses RENAME COLUMN risk_v2_json TO risk_assessment_json;

UPDATE ai_theses SET debate_protocol = 'current' WHERE debate_protocol IN ('v1', 'v2');
