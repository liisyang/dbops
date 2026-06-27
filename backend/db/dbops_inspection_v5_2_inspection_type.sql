-- =============================================================================
-- v5.2: Add inspection_type column for business-level categorization
-- =============================================================================
-- 新增 inspection_type 字段作为巡检项的业务分组标签。
-- 独立于 category（检查类别：info/state/capacity/performance）和
-- db_type_code（DB 引擎类型：Oracle/SQLServer/MySQL/PostgreSQL）。
--
-- 典型值：Oracle基础巡检、SQL Server基础巡检 等。
-- 可为空：已有巡检项未分类时显示为「未分类」。
-- 任务创建时自动快照到 inspection_task_item。
--
-- 执行环境: 测试库 dbops (10.134.185.85:5432)
-- 配套回滚: rollback_inspection_v5_2_inspection_type.sql
-- =============================================================================

BEGIN;

-- inspection_item (主表)
ALTER TABLE dbops.inspection_item
    ADD COLUMN IF NOT EXISTS inspection_type VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_inspection_item_inspection_type
    ON dbops.inspection_item(inspection_type)
    WHERE inspection_type IS NOT NULL;

COMMENT ON COLUMN dbops.inspection_item.inspection_type IS
    '巡检类型 — 业务分组标签，例如 Oracle基础巡检 / SQL Server基础巡检。可选。';

-- inspection_task_item (快照表，创建任务时从 inspection_item 复制)
ALTER TABLE dbops.inspection_task_item
    ADD COLUMN IF NOT EXISTS inspection_type VARCHAR(100);

COMMENT ON COLUMN dbops.inspection_task_item.inspection_type IS
    '巡检类型快照 — 任务创建时从 inspection_item 复制。可选。';

COMMIT;
