-- ============================================================================
-- DBOPS Phase 3.6B1: AI Copilot - SQL Execute
-- DDL Migration（可重复执行；幂等）
--
-- 变更点：
--   1. ai_chat_message.message_type CHECK 扩展：新增 'sql_preview_link'
--      （Chat 流内"SQL Preview"卡片，由 C14 ExecuteService 调用 SqlPreview
--       通过「接受并写回」按钮产生，C15 起 Chat 一键预览会用）
--   2. ai_chat_message 新增部分唯一索引：同一 audit 至多落一条 sql_result 消息
--      （callback 重发场景下去重；ORM 层 metadata_json 已用 JSONB，索引用表达式）
--
-- 依赖（pre-existing）:
--   - dbops.ai_chat_message — 聊天消息表（C2 已建）
--   - dbops.ai_sql_audit — SQL 审计表（C12 已建，含完整 execute 字段）
--
-- 不在 C14 范围（明确避免 scope creep）:
--   ❌ Chat 流 sql_preview_link 卡片 → C15
--   ❌ Inspection AI Analysis → C16
--   ❌ SSE / Stream → C18
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_chat_message.message_type CHECK 扩展 — 新增 'sql_preview_link'
-- ============================================================================
DO $$
BEGIN
    -- 如果 CHECK 约束存在且不含 'sql_preview_link'，先 DROP 再 ADD
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_message_type'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        -- 用 pg_get_constraintdef 检查是否已包含新枚举值
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            WHERE conname = 'chk_ai_chat_message_type'
              AND conrelid = 'dbops.ai_chat_message'::regclass
              AND pg_get_constraintdef(c.oid) LIKE '%sql_preview_link%'
        ) THEN
            ALTER TABLE dbops.ai_chat_message
                DROP CONSTRAINT chk_ai_chat_message_type;
            ALTER TABLE dbops.ai_chat_message
                ADD CONSTRAINT chk_ai_chat_message_type
                CHECK (message_type IN ('chat', 'sql_preview', 'sql_preview_link', 'sql_result', 'error'));
        END IF;
    ELSE
        -- 约束不存在，直接创建（兼容首次部署）
        ALTER TABLE dbops.ai_chat_message
            ADD CONSTRAINT chk_ai_chat_message_type
            CHECK (message_type IN ('chat', 'sql_preview', 'sql_preview_link', 'sql_result', 'error'));
    END IF;
END $$;

-- ============================================================================
-- 2. 部分唯一索引：同一 audit 至多一条 sql_result 消息（幂等去重）
-- ============================================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_message_sql_result_audit
    ON dbops.ai_chat_message ((metadata->>'audit_id'))
    WHERE message_type = 'sql_result' AND metadata ? 'audit_id';

COMMIT;

-- 验证
SELECT 'chk_ai_chat_message_type' AS constraint_name,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conname = 'chk_ai_chat_message_type'
  AND conrelid = 'dbops.ai_chat_message'::regclass;

SELECT 'uq_ai_chat_message_sql_result_audit' AS index_name,
       indexdef AS definition
FROM pg_indexes
WHERE indexname = 'uq_ai_chat_message_sql_result_audit';