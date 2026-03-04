-- 019: Add v2 agent output columns to ai_theses.
-- Stores JSON-serialized outputs from 6-agent debate protocol (flow, fundamental,
-- risk v2, contrarian) plus a protocol version discriminator.
ALTER TABLE ai_theses ADD COLUMN flow_json TEXT;
ALTER TABLE ai_theses ADD COLUMN fundamental_json TEXT;
ALTER TABLE ai_theses ADD COLUMN risk_v2_json TEXT;
ALTER TABLE ai_theses ADD COLUMN contrarian_json TEXT;
ALTER TABLE ai_theses ADD COLUMN debate_protocol TEXT DEFAULT 'v1';
