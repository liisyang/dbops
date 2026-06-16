-- =============================================================================
-- Phase 3.4 batch-verify 1000+ — P0-4/5/6 review-fixup migrations
-- =============================================================================
-- Background: working-tree diff for batch verify 1000+ was reviewed
-- (/ecc:review-pr on 2026-06-16). Findings C6 + I3 require schema changes:
--
--   1. collector_dispatch_run.cancelled_at (C6)
--      Separate cancel signal from finished_at so cancel does not clobber
--      a real finished_at set by the callback path, and so audits can
--      distinguish "user-cancelled" from "naturally-terminated".
--
--   2. asset_fact_snapshot UNIQUE(source_run_id, source_item_key) (I3)
--      Close the TOCTOU race in handle_callback's existing_snapshot pre-check
--      so two parallel callbacks for the same (run_id, item_key) cannot
--      both insert a snapshot.
--
--   3. (defensive) helper queries for the operator to verify migration
--      succeeded and to find any pre-existing duplicates before the UNIQUE
--      constraint is added.
--
-- Rollback: see /home/lisiyang/dbops/backend/db/rollback_phase3_4_batch_verify_p0_4_5_6.sql
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. cancelled_at column on collector_dispatch_run (C6)
-- -----------------------------------------------------------------------------
ALTER TABLE dbops.collector_dispatch_run
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP WITHOUT TIME ZONE;

COMMENT ON COLUMN dbops.collector_dispatch_run.cancelled_at
    IS 'Set by BatchCollectorService.cancel_batch_run when a dispatch is cancelled
        by the user. Distinct from finished_at which is set by the natural
        callback/timeout-recovery transition. NULL for non-cancelled rows.';

-- Index for finding recently-cancelled dispatches during audits / for
-- the new /collector/scheduler/status endpoint to surface cancel activity.
CREATE INDEX IF NOT EXISTS idx_collector_dispatch_run_cancelled_at
    ON dbops.collector_dispatch_run (cancelled_at)
    WHERE cancelled_at IS NOT NULL;


-- -----------------------------------------------------------------------------
-- 2. asset_fact_snapshot UNIQUE(source_run_id, source_item_key) (I3)
-- -----------------------------------------------------------------------------
-- Pre-check (run BEFORE this migration as a sanity scan):
--
--   SELECT source_run_id, source_item_key, COUNT(*) AS n
--   FROM dbops.asset_fact_snapshot
--   WHERE source_run_id IS NOT NULL AND source_item_key IS NOT NULL
--   GROUP BY source_run_id, source_item_key
--   HAVING COUNT(*) > 1;
--
-- If any rows are returned, the UNIQUE constraint will fail. Resolve by
-- keeping the earliest row (lowest id) per (source_run_id, source_item_key):
--
--   DELETE FROM dbops.asset_fact_snapshot a
--   USING dbops.asset_fact_snapshot b
--   WHERE a.source_run_id = b.source_run_id
--     AND a.source_item_key = b.source_item_key
--     AND a.id > b.id
--     AND a.source_run_id IS NOT NULL
--     AND a.source_item_key IS NOT NULL;
--
-- (The existing idx_asset_fact_snapshot_source index already covers
-- (source_run_id, source_item_key) so the constraint adds no extra cost.)

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


-- -----------------------------------------------------------------------------
-- 3. Verification helpers
-- -----------------------------------------------------------------------------
-- Run these after migration to confirm:
--   * cancelled_at column exists
--   * unique constraint is in place
--   * no duplicates remain (should return 0 rows)
--
-- SELECT column_name FROM information_schema.columns
-- WHERE table_schema='dbops' AND table_name='collector_dispatch_run'
--   AND column_name='cancelled_at';
--
-- SELECT conname FROM pg_constraint
-- WHERE conname = 'uq_asset_fact_snapshot_source';
--
-- SELECT source_run_id, source_item_key, COUNT(*) AS n
-- FROM dbops.asset_fact_snapshot
-- WHERE source_run_id IS NOT NULL AND source_item_key IS NOT NULL
-- GROUP BY source_run_id, source_item_key
-- HAVING COUNT(*) > 1;

COMMIT;
