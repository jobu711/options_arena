-- Add filter_spec_json column to scan_runs for scan reproducibility.
-- Stores ScanFilterSpec.model_dump_json() so that any scan can be replayed
-- with the exact same filter settings.
ALTER TABLE scan_runs ADD COLUMN filter_spec_json TEXT;
