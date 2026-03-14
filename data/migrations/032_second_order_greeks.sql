-- Migration 032: Add second-order Greek columns to recommended_contracts.
-- These persist vanna, charm, and vomma from OptionGreeks (computed by pricing/dispatch).
-- Idempotent: check column existence before adding (SQLite lacks ADD COLUMN IF NOT EXISTS).
ALTER TABLE recommended_contracts ADD COLUMN vanna REAL;
ALTER TABLE recommended_contracts ADD COLUMN charm REAL;
ALTER TABLE recommended_contracts ADD COLUMN vomma REAL;
