-- =============================================================================
-- Rollback v5.2: Drop inspection_type columns
-- =============================================================================

BEGIN;

ALTER TABLE dbops.inspection_task_item
    DROP COLUMN IF EXISTS inspection_type;

ALTER TABLE dbops.inspection_item
    DROP COLUMN IF EXISTS inspection_type;

COMMIT;
