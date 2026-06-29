-- ============================================================================
-- DBOPS Phase 3.6B1: AI Copilot - SQL Execute 回滚
-- ⚠ Dangerous: 此脚本会移除 C14 新增的 message_type 枚举值和 sql_result 幂等索引
--
-- 依赖：执行前确认当前 ai_chat_message 没有 message_type='sql_preview_link' 的行
--   SELECT COUNT(*) FROM dbops.ai_chat_message WHERE message_type = 'sql_preview_link';
-- 若有 > 0 行需先清理或迁移，否则 ALTER 会失败：
--   UPDATE dbops.ai_chat_message SET message_type = 'chat' WHERE message_type = 'sql_preview_link';
-- ============================================================================

BEGIN;

-- 1. 移除 sql_result 幂等索引
DROP INDEX IF EXISTS dbops.uq_ai_chat_message_sql_result_audit;

-- 2. 还原 message_type CHECK（移除 sql_preview_link）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_message_type'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
            DROP CONSTRAINT chk_ai_chat_message_type;
        ALTER TABLE dbops.ai_chat_message
            ADD CONSTRAINT chk_ai_chat_message_type
            CHECK (message_type IN ('chat', 'sql_preview', 'sql_result', 'error'));
    END IF;
END $$;

COMMIT;

-- 验证
SELECT 'chk_ai_chat_message_type' AS constraint_name,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conname = 'chk_ai_chat_message_type'
  AND conrelid = 'dbops.ai_chat_message'::regclass;

SELECT 'uq_ai_chat_message_sql_result_audit' AS index_name,
       COUNT(*) AS index_exists
FROM pg_indexes
WHERE indexname = 'uq_ai_chat_message_sql_result_audit';