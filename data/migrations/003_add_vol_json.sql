-- 003_add_vol_json.sql — Add volatility thesis JSON column to ai_theses
--
-- Stores the serialized VolatilityThesis from the optional volatility agent.
-- NULL when the volatility agent is disabled or skipped.

ALTER TABLE ai_theses ADD COLUMN vol_json TEXT;
