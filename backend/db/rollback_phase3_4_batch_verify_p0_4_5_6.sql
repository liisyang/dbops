-- =============================================================================
-- Rollback for dbops_phase3_4_batch_verify_p0_4_5_6_fixups.sql
-- =============================================================================
-- Run this to undo the C6 (cancelled_at) + I3 (UNIQUE) migrations if the
-- working tree causes issues in the test DB.
--
-- This is the inverse of the migration file. Use a transaction so a partial
-- failure leaves the DB in a consistent state.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Drop the UNIQUE constraint first (it has a covering index we want to keep)
-- -----------------------------------------------------------------------------
ALTER TABLE dbops.asset_fact_snapshot
    DROP CONSTRAINT IF EXISTS uq_asset_fact_snapshot_source;


-- -----------------------------------------------------------------------------
-- Drop the cancelled_at index + column
-- -----------------------------------------------------------------------------
DROP INDEX IF EXISTS dbops.idx_collector_dispatch_run_cancelled_at;

ALTER TABLE dbops.collector_dispatch_run
    DROP COLUMN IF EXISTS cancelled_at;

COMMIT;


-- =============================================================================
-- Verification after rollback:
-- =============================================================================
--   SELECT column_name FROM information_schema.columns
--   WHERE table_schema='dbops' AND table_name='collector_dispatch_run'
--     AND column_name='cancelled_at';
--   -- expect 0 rows
--
--   SELECT conname FROM pg_constraint
--   WHERE conname = 'uq_asset_fact_snapshot_source';
--   -- expect 0 rows
-- =============================================================================
