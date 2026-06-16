-- =============================================================================
-- Rollback: Phase 3.4 v2 — PARTIAL UNIQUE INDEX → full UNIQUE CONSTRAINT
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS dbops.uq_asset_fact_snapshot_source;

-- Restore the full UNIQUE constraint (it was here before v2)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_asset_fact_snapshot_source'
          AND conrelid = 'dbops.asset_fact_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.asset_fact_snapshot
            ADD CONSTRAINT uq_asset_fact_snapshot_source
            UNIQUE (source_run_id, source_item_key);
    END IF;
END$$;

COMMIT;
