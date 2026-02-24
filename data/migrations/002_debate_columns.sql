-- 002_debate_columns.sql — Add debate metadata columns to ai_theses
--
-- Extends the v2 placeholder table with columns needed by the debate system.

ALTER TABLE ai_theses ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN model_name TEXT DEFAULT '';
ALTER TABLE ai_theses ADD COLUMN duration_ms INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN is_fallback INTEGER DEFAULT 0;
