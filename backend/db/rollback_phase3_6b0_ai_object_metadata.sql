-- ============================================================================
-- DBOPS Phase 3.6B0 F3 (C16-F3): AI Copilot - Object Metadata Snapshot 回滚
-- ❗Dangerous: 此脚本会删除所有 Object Metadata Snapshot 数据
--
-- 执行前请先确认数据量：
--   SELECT COUNT(*) FROM dbops.ai_object_metadata_snapshot;
--   SELECT MAX(created_at) FROM dbops.ai_object_metadata_snapshot;
--
-- 部署失败时不自动执行破坏性回滚 — 需先人工确认数据量。
-- ============================================================================

BEGIN;

-- CASCADE 会自动级联删除所有约束 / 索引 / 触发器
DROP TABLE IF EXISTS dbops.ai_object_metadata_snapshot CASCADE;

COMMIT;

-- 验证（应返回 0 行）
SELECT 'ai_object_metadata_snapshot' AS table_name, COUNT(*) AS table_exists
FROM information_schema.tables
WHERE table_schema = 'dbops' AND table_name = 'ai_object_metadata_snapshot';
