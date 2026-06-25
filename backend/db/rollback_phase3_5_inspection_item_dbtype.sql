-- =============================================================================
-- Phase 3.5: inspection_item.db_type_code rollback
-- =============================================================================
-- 配套 dbops_phase3_5_inspection_item_dbtype.sql 的回滚 SQL。
-- =============================================================================

DROP INDEX IF EXISTS dbops.idx_inspection_item_db_type_code;
ALTER TABLE dbops.inspection_item DROP COLUMN IF EXISTS db_type_code;