-- 009_market_context.sql — Add market_context_json column to ai_theses
--
-- Stores the full MarketContext snapshot (serialized via model_dump_json())
-- alongside the debate result. Enables export with real prices and full
-- market state even when loaded from the database.
-- Nullable for backward compatibility with existing debate records.
ALTER TABLE ai_theses ADD COLUMN market_context_json TEXT;
