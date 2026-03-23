-- Migration 040: Add desk_metrics_json column to recommendation_results
-- Stores per-desk DeskMetrics (tier, model, tokens, duration) for cost analytics

ALTER TABLE recommendation_results ADD COLUMN desk_metrics_json TEXT NOT NULL DEFAULT '[]';
