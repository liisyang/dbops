-- ============================================================================
-- DBOPS Phase 3.6A: AI Copilot - Chat 回滚
-- ❗Dangerous: 此脚本会删除所有 Chat 数据
--
-- 执行前请先确认数据量：
--   SELECT COUNT(*) FROM dbops.ai_chat_message;
--   SELECT COUNT(*) FROM dbops.ai_chat_session;
--   SELECT MAX(created_at) FROM dbops.ai_chat_message;
--
-- 部署失败时不自动执行破坏性回滚 — 需先人工确认数据量。
-- ============================================================================

BEGIN;

-- 1. 先删除 message（依赖 session）
DROP TABLE IF EXISTS dbops.ai_chat_message CASCADE;

-- 2. 删除 session
DROP TABLE IF EXISTS dbops.ai_chat_session CASCADE;

COMMIT;

-- 验证（应返回 0 行）
SELECT 'ai_chat_session' AS table_name, COUNT(*) AS row_count
FROM information_schema.tables
WHERE table_schema = 'dbops' AND table_name = 'ai_chat_session'
UNION ALL
SELECT 'ai_chat_message', COUNT(*)
FROM information_schema.tables
WHERE table_schema = 'dbops' AND table_name = 'ai_chat_message';
