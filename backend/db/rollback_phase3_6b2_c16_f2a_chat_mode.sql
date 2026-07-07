-- ============================================================================
-- DBOPS Phase 3.6B2: C16-F2a Chat 绑定实例字段 — Rollback
-- 回滚 C16-F2a 新增的 chat_mode / bound_instance_id 字段及关联约束
--
-- ⚠️ 危险：执行前必须确认：
--   1. 应用层已停止调用 /api/v1/ai/chat/sessions 的 mode/instance_sql 路径
--   2. 已迁移所有 chat_mode='instance_sql' 的 session（如需保留数据，先手工 UPDATE）
--   3. 已 DROP 依赖 bound_instance_id 的索引/视图（如有）
-- ============================================================================

BEGIN;

-- 1. 删除约束（顺序：FK → CHECK）
ALTER TABLE dbops.ai_chat_session
    DROP CONSTRAINT IF EXISTS fk_ai_chat_session_bound_instance;

ALTER TABLE dbops.ai_chat_session
    DROP CONSTRAINT IF EXISTS chk_ai_chat_session_bound_instance;

ALTER TABLE dbops.ai_chat_session
    DROP CONSTRAINT IF EXISTS chk_ai_chat_session_mode;

-- 2. 删除索引
DROP INDEX IF EXISTS dbops.idx_ai_chat_session_bound_instance;
DROP INDEX IF EXISTS dbops.uq_ai_chat_session_user_instance_sql;

-- 3. 删除字段
ALTER TABLE dbops.ai_chat_session
    DROP COLUMN IF EXISTS bound_instance_id;

ALTER TABLE dbops.ai_chat_session
    DROP COLUMN IF EXISTS chat_mode;

COMMIT;

-- 验证（不应有任何 chat_mode / bound_instance_id 残留）
SELECT
    column_name
FROM information_schema.columns
WHERE table_schema = 'dbops'
  AND table_name = 'ai_chat_session'
  AND column_name IN ('chat_mode', 'bound_instance_id');

SELECT
    conname AS constraint_name
FROM pg_constraint
WHERE conrelid = 'dbops.ai_chat_session'::regclass
  AND conname IN (
    'chk_ai_chat_session_mode',
    'chk_ai_chat_session_bound_instance',
    'fk_ai_chat_session_bound_instance'
  );