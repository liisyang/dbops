-- =============================================================================
-- Phase 3.4 v2 — UNIQUE → PARTIAL UNIQUE INDEX for asset_fact_snapshot
-- =============================================================================
-- Background: v1 migration added a full UNIQUE(source_run_id, source_item_key)
-- constraint, which:
--   (a) Does NOT cover NULL values (PG default NULLS DISTINCT) — I5 TOCTOU gap
--   (b) Auto-creates a composite backing btree — C3 cost analysis
--   (c) Keeps the old single-column idx_fact_snapshot_source_run as redundant
--
-- v2 fix: drop the full UNIQUE, replace with a partial unique index that
-- only constrains non-null rows. NULLs are out of scope (TOCTOU only
-- matters when both fields are populated by the callback path).
-- =============================================================================

BEGIN;

-- 1. Pre-flight: confirm asset_fact_snapshot exists
DO $$
BEGIN
    IF to_regclass('dbops.asset_fact_snapshot') IS NULL THEN
        RAISE EXCEPTION 'dbops.asset_fact_snapshot does not exist';
    END IF;
END$$;

-- 2. Drop the full UNIQUE constraint (this also drops its backing btree)
ALTER TABLE dbops.asset_fact_snapshot
    DROP CONSTRAINT IF EXISTS uq_asset_fact_snapshot_source;

-- 3. Drop the constraint-named index if it lingered (belt + suspenders)
DROP INDEX IF EXISTS dbops.uq_asset_fact_snapshot_source;

-- 4. Create the partial unique index (TOCTOU protection only when both
-- columns are populated — NULLs excluded, matching the callback contract)
CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_fact_snapshot_source
    ON dbops.asset_fact_snapshot (source_run_id, source_item_key)
    WHERE source_run_id IS NOT NULL
      AND source_item_key IS NOT NULL;

-- 5. Verify the new index covers the expected query pattern
-- (a) Equality on both columns: yes
-- (b) Equality on source_run_id alone: partial index cannot satisfy this
--     because the WHERE clause restricts to (NOT NULL, NOT NULL). If any
--     query does WHERE source_run_id = ?, it MUST fall back to the
--     single-column idx_fact_snapshot_source_run. We do NOT drop that
--     index in this migration — verify its usage first, then drop in a
--     follow-up.
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'dbops'
  AND tablename = 'asset_fact_snapshot'
  AND indexname IN (
      'uq_asset_fact_snapshot_source',
      'idx_fact_snapshot_source_run'
  );

-- 6. (Optional, follow-up) Drop the redundant single-column index once
-- we have confirmed via pg_stat_user_indexes that no query uses it:
--   SELECT idx_scan FROM pg_stat_user_indexes
--   WHERE indexname = 'idx_fact_snapshot_source_run';
-- If idx_scan = 0 over a representative window, drop:
--   DROP INDEX IF EXISTS dbops.idx_fact_snapshot_source_run;
-- This is intentionally NOT in the migration — do it in a separate
-- PR after observation.

COMMIT;
