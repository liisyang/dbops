-- =============================================================================
-- Phase 3.5: inspection_item.db_type_code column gap fix
-- =============================================================================
-- 修复 Commit 3 (1d5ec9b) 引入的 ORM/DB 不一致：
-- InspectionItem ORM 模型声明了 db_type_code (dbops_assets.py)，
-- InspectionService 也用 item.db_type_code (inspection_service.py:80)，
-- 但 Phase 3.4 DDL 没有 ADD COLUMN，Phase 3.5 DDL
-- (dbops_phase3_5_backup_status.sql) 也只补了 backup_status_snapshot，
-- 没有 inspection_item。结果：任何 ORM 读 inspection_item.db_type_code
-- 的 query 都报 UndefinedColumn 异常。
--
-- 修复：ADD COLUMN IF NOT EXISTS db_type_code VARCHAR(32) （允许 NULL，
-- 因为历史 12 行都不是 DB_READONLY_SQL_EXEC 类型，不强制 NOT NULL）。
--
-- 执行环境: 测试库 dbops (10.134.185.85:5432)
-- 配套回滚: rollback_phase3_5_inspection_item_dbtype.sql
-- =============================================================================

ALTER TABLE dbops.inspection_item
    ADD COLUMN IF NOT EXISTS db_type_code VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_inspection_item_db_type_code
    ON dbops.inspection_item(db_type_code)
    WHERE db_type_code IS NOT NULL;

COMMENT ON COLUMN dbops.inspection_item.db_type_code IS
    'Phase 3.5: SQL safety service 选 lead-keyword allow-list 的依据。'
    'DB_READONLY_SQL_EXEC 类型必填；其他 check_code 可空。';