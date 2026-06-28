-- ============================================================================
-- DBOPS Phase 3.6B: AI Copilot - SQL Audit 回滚
-- ❗Dangerous: 此脚本会删除所有 ai_sql_audit 数据
--
-- 执行前请先确认数据量：
--   SELECT COUNT(*) FROM dbops.ai_sql_audit;
--   SELECT COUNT(*) FROM dbops.ai_sql_audit WHERE preview_safety_status = 'passed';
--   SELECT MAX(created_at) FROM dbops.ai_sql_audit;
--
-- 部署失败时不自动执行破坏性回滚 — 需先人工确认数据量。
-- ============================================================================

BEGIN;

-- CASCADE 会自动级联删除所有约束 / 索引 / 触发器
DROP TABLE IF EXISTS dbops.ai_sql_audit CASCADE;

COMMIT;

-- 验证（应返回 0 行）
SELECT 'ai_sql_audit' AS table_name, COUNT(*) AS table_exists
FROM information_schema.tables
WHERE table_schema = 'dbops' AND table_name = 'ai_sql_audit';