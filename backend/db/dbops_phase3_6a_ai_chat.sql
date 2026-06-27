-- ============================================================================
-- DBOPS Phase 3.6A: AI Copilot - Chat 会话与消息
-- DDL Migration（可重复执行；幂等）
--
-- 表:
--   1. ai_chat_session  - 聊天会话（user 维度）
--   2. ai_chat_message  - 聊天消息（user / assistant / system）
--
-- 关键约束（plan §2.1 P0-5 修正）:
--   - client_request_id 只写在 user message（幂等键）
--   - 部分唯一索引: UNIQUE(session_id, client_request_id) WHERE role='user' AND client_request_id IS NOT NULL
--   - 并发 pending 约束: UNIQUE(session_id) WHERE role='assistant' AND status='pending'
--   - 租约机制: processing_started_at / processing_expires_at
--   - metadata 列存储 JSONB（SQLAlchemy 端映射为 metadata_json）
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_chat_session — 聊天会话
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.ai_chat_session (
    id BIGSERIAL PRIMARY KEY,
    session_code VARCHAR(100) NOT NULL,
    user_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    dify_conversation_id VARCHAR(200),
    model_provider VARCHAR(50) NOT NULL DEFAULT 'dify',
    message_count INTEGER NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- UNIQUE: session_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_ai_chat_session_code'
          AND conrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_session
        ADD CONSTRAINT uq_ai_chat_session_code UNIQUE (session_code);
    END IF;
END $$;

-- FK: user_id -> users.id (SET NULL on user delete 保留会话审计)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_chat_session_user'
          AND conrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_session
        ADD CONSTRAINT fk_ai_chat_session_user
        FOREIGN KEY (user_id) REFERENCES dbops.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_chat_session_user
    ON dbops.ai_chat_session(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_chat_session_last_message_at
    ON dbops.ai_chat_session(last_message_at DESC NULLS LAST);

-- Trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_chat_session_updated_at'
          AND tgrelid = 'dbops.ai_chat_session'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_chat_session_updated_at
        BEFORE UPDATE ON dbops.ai_chat_session
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 2. ai_chat_message — 聊天消息
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.ai_chat_message (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    user_id UUID,
    client_request_id UUID,
    role VARCHAR(20) NOT NULL,
    message_type VARCHAR(30) NOT NULL DEFAULT 'chat',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    content TEXT,
    parent_message_id BIGINT,
    -- 注意：列名 `metadata`（JSONB），SQLAlchemy 端映射为 metadata_json
    -- 原因：SQLAlchemy Declarative Base.metadata 是保留属性
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Dify 响应元数据
    dify_task_id VARCHAR(100),
    workflow_run_id VARCHAR(100),
    elapsed_ms INTEGER,
    total_tokens INTEGER,
    -- 错误与状态
    error_code VARCHAR(100),
    error_message TEXT,
    -- 租约机制（plan §2.1 P0-5）
    processing_started_at TIMESTAMPTZ,
    processing_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FK: session_id -> ai_chat_session.id (CASCADE：删除会话清空消息)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_chat_message_session'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT fk_ai_chat_message_session
        FOREIGN KEY (session_id) REFERENCES dbops.ai_chat_session(id) ON DELETE CASCADE;
    END IF;
END $$;

-- FK: user_id -> users.id (SET NULL 保留消息审计)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_chat_message_user'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT fk_ai_chat_message_user
        FOREIGN KEY (user_id) REFERENCES dbops.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: parent_message_id -> ai_chat_message.id (self-ref, SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_chat_message_parent'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT fk_ai_chat_message_parent
        FOREIGN KEY (parent_message_id) REFERENCES dbops.ai_chat_message(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CHECK: role
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_message_role'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT chk_ai_chat_message_role
        CHECK (role IN ('user', 'assistant', 'system'));
    END IF;
END $$;

-- CHECK: message_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_message_type'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT chk_ai_chat_message_type
        CHECK (message_type IN ('chat', 'sql_preview', 'sql_result', 'error'));
    END IF;
END $$;

-- CHECK: status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_chat_message_status'
          AND conrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        ALTER TABLE dbops.ai_chat_message
        ADD CONSTRAINT chk_ai_chat_message_status
        CHECK (status IN ('pending', 'completed', 'failed', 'stale'));
    END IF;
END $$;

-- 关键：部分唯一索引（plan §2.1 P0-5）
-- 用户消息幂等键：(session_id, client_request_id) 当 role=user
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_ai_chat_message_session_client_request'
    ) THEN
        CREATE UNIQUE INDEX uq_ai_chat_message_session_client_request
            ON dbops.ai_chat_message (session_id, client_request_id)
            WHERE role = 'user' AND client_request_id IS NOT NULL;
    END IF;
END $$;

-- 关键：并发 pending 约束（plan §2.1 P0-5）
-- 同一 session 同时只允许一个 assistant pending
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_ai_chat_message_assistant_pending'
    ) THEN
        CREATE UNIQUE INDEX uq_ai_chat_message_assistant_pending
            ON dbops.ai_chat_message (session_id)
            WHERE role = 'assistant' AND status = 'pending';
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_chat_message_session_created
    ON dbops.ai_chat_message(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_chat_message_status
    ON dbops.ai_chat_message(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_ai_chat_message_processing_expires
    ON dbops.ai_chat_message(processing_expires_at)
    WHERE status = 'pending' AND role = 'assistant';
CREATE INDEX IF NOT EXISTS idx_ai_chat_message_parent
    ON dbops.ai_chat_message(parent_message_id) WHERE parent_message_id IS NOT NULL;

-- Trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_chat_message_updated_at'
          AND tgrelid = 'dbops.ai_chat_message'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_chat_message_updated_at
        BEFORE UPDATE ON dbops.ai_chat_message
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

COMMIT;

-- 验证
SELECT 'ai_chat_session' AS table_name, COUNT(*) AS row_count FROM dbops.ai_chat_session
UNION ALL
SELECT 'ai_chat_message', COUNT(*) FROM dbops.ai_chat_message;
