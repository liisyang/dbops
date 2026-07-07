-- ============================================================================
-- DBOPS Phase 3.6B2: C16-F2a Chat 绑定实例字段
-- DDL Migration（可重复执行；幂等）
--
-- 表: dbops.ai_chat_session
--   新增字段:
--     1. chat_mode         VARCHAR(30) NOT NULL DEFAULT 'general'
--                          Chat 模式：general（普通多轮对话）/ instance_sql（实例绑定 SQL Copilot）
--     2. bound_instance_id BIGINT NULL
--                          当 chat_mode='instance_sql' 时必填；指向 dbops.db_instance.id
--                          创建后不可变（P0-1 不可变绑定规则）
--
-- 关键约束（plan §21.2 P0-1 修正）:
--   - chat_mode 枚举: 'general' / 'instance_sql'
--   - 双约束: (general AND NULL) OR (instance_sql AND NOT NULL)
--   - partial unique: 同 user 同一 instance 只复用一个 instance_sql session
--     → UNIQUE(user_id, bound_instance_id) WHERE chat_mode='instance_sql' AND bound_instance_id IS NOT NULL
--   - FK: bound_instance_id -> db_instance.id (CASCADE — 删除实例清空 session)
--
-- 设计动机（plan §21.2）:
--   这是 SQL Preview 入口鉴权依赖字段，必须作为实体列而非 JSONB 内字段
--   metadata_json 仍可用于存 bound_instance_name / source_page / context_version 等辅助信息
--
-- 执行前确认:
--   - SELECT COUNT(*) FROM dbops.ai_chat_session; -- 当前 20 行
--   - 字段可重复执行（ADD COLUMN IF NOT EXISTS）
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. 新增字段
-- ============================================================================
ALTER TABLE dbops.ai_chat_session
    ADD COLUMN IF NOT EXISTS chat_mode VARCHAR(30) NOT NULL DEFAULT 'general';

ALTER TABLE dbops.ai_chat_session
    ADD COLUMN IF NOT EXISTS bound_instance_id BIGINT NULL;

-- ============================================================================
-- 2. CHECK 约束 — chat_mode 枚举
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_session_mode'
          AND conrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_session
        ADD CONSTRAINT chk_ai_chat_session_mode
        CHECK (chat_mode IN ('general', 'instance_sql'));
    END IF;
END $$;

-- ============================================================================
-- 3. CHECK 约束 — mode 与 bound_instance_id 一致性
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_session_bound_instance'
          AND conrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_session
        ADD CONSTRAINT chk_ai_chat_session_bound_instance
        CHECK (
            (chat_mode = 'general' AND bound_instance_id IS NULL)
            OR
            (chat_mode = 'instance_sql' AND bound_instance_id IS NOT NULL)
        );
    END IF;
END $$;

-- ============================================================================
-- 4. FK: bound_instance_id -> db_instance.id (CASCADE)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_chat_session_bound_instance'
          AND conrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_session
        ADD CONSTRAINT fk_ai_chat_session_bound_instance
        FOREIGN KEY (bound_instance_id) REFERENCES dbops.db_instance(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 5. 部分唯一索引 — 同 user 同一 instance 只复用一个 instance_sql session
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_ai_chat_session_user_instance_sql'
    ) THEN
        CREATE UNIQUE INDEX uq_ai_chat_session_user_instance_sql
            ON dbops.ai_chat_session (user_id, bound_instance_id)
            WHERE chat_mode = 'instance_sql' AND bound_instance_id IS NOT NULL;
    END IF;
END $$;

-- ============================================================================
-- 6. 辅助索引 — 按 mode + instance 查询
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_ai_chat_session_bound_instance
    ON dbops.ai_chat_session(bound_instance_id)
    WHERE bound_instance_id IS NOT NULL;

COMMIT;

-- 验证（仅 schema 元数据查询，不查业务表行数据）
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'dbops'
  AND table_name = 'ai_chat_session'
  AND column_name IN ('chat_mode', 'bound_instance_id')
ORDER BY column_name;

SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'dbops.ai_chat_session'::regclass
  AND conname IN (
    'chk_ai_chat_session_mode',
    'chk_ai_chat_session_bound_instance',
    'fk_ai_chat_session_bound_instance'
  )
ORDER BY conname;

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'dbops'
  AND tablename = 'ai_chat_session'
  AND indexname IN (
    'uq_ai_chat_session_user_instance_sql',
    'idx_ai_chat_session_bound_instance'
  )
ORDER BY indexname;