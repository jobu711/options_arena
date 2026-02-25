-- 004_add_rebuttal_json.sql — Add bull rebuttal JSON column to ai_theses
--
-- Stores the serialized AgentResponse from the optional bull rebuttal phase.
-- NULL when the rebuttal is disabled or skipped.

ALTER TABLE ai_theses ADD COLUMN rebuttal_json TEXT;
