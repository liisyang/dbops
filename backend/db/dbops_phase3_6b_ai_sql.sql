-- ============================================================================
-- DBOPS Phase 3.6B: AI Copilot - SQL Audit
-- DDL Migration（可重复执行；幂等）
--
-- 表:
--   1. ai_sql_audit - SQL Preview/Execute 审计（plan §2.3 line 192-197）
--
-- 关键约束（plan §2.3 + §2.4 + §19 P0-6 条件 UPDATE）:
--   - 双轨 SQL: generated_sql（Dify 原始） vs approved_sql（AST 重写后）
--   - 双 SHA-256: generated_sql_hash + approved_sql_hash
--   - Preview/Execution 状态机分离:
--       preview_safety_status:   passed / rejected
--       execution_status:        not_requested / pending / running / success
--                                / failed / timeout / cancelled
--   - Schema 强绑定（plan §4.5 P0-3）:
--       schema_snapshot_id (FK) + schema_policy_hash
--       Execute 时再次校验 snapshot.is_current + schema_policy_hash 一致
--   - 条件 UPDATE 控制 execution_status 转换（plan §19 P0-6）：
--       数据库 CHECK 仅约束枚举值，状态转换由应用层条件 UPDATE 实现
--
-- 依赖（pre-existing）:
--   - dbops.db_instance(id)        — 实例主表
--   - dbops.users(id)              — 用户主表（user_id FK SET NULL）
--   - dbops.ai_chat_session(id)    — 聊天会话（session_id FK SET NULL）
--   - dbops.ai_chat_message(id)    — 聊天消息（message_id / result_message_id FK SET NULL）
--   - dbops.ai_sql_schema_snapshot(id) — Schema 快照（C6 表）
--   - dbops.collector_run(id)      — AWX 采集运行（collector_run_id FK SET NULL）
--   - dbops.collector_run_item(id) — AWX 采集 item（collector_run_item_id FK SET NULL）
--
-- 不在 C12 范围（明确避免 scope creep）:
--   ❌ AiSqlCallbackService + /ai/sql/execute + Execute 业务逻辑 → C17-C19
--   ❌ 子查询 alias 列解析 → C11 已记录 §14 收尾工单
--   ❌ Dify SQL workflow Key 在 .env 缺失时启动校验 → C29
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_sql_audit — SQL Preview/Execute 审计
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.ai_sql_audit (
    id BIGSERIAL PRIMARY KEY,
    -- 关联：会话 + 消息（可空：直接调用 preview 时不带 chat 上下文）
    session_id BIGINT,
    message_id BIGINT,
    result_message_id BIGINT,
    user_id UUID,

    -- 目标实例（必填；instance 删除时级联清理 audit）
    instance_id BIGINT NOT NULL,
    db_type_code VARCHAR(50) NOT NULL,

    -- 用户原始问题
    user_question TEXT NOT NULL,

    -- Dify 生成（原始） — 审计追溯
    generated_sql TEXT,
    generated_sql_hash VARCHAR(64),

    -- AST 重写后（权威） — Execute 时唯一使用
    approved_sql TEXT,
    approved_sql_hash VARCHAR(64),

    -- Preview 安全状态
    preview_safety_status VARCHAR(20) NOT NULL DEFAULT 'rejected',
    preview_safety_reason TEXT,

    -- Execute 安全状态（Execute 阶段再次校验 approved_sql_hash 一致）
    execution_safety_status VARCHAR(20),
    execution_safety_reason TEXT,

    -- 策略版本（safety_policy_version 与 schema_policy_version 不同：
    --   safety_policy_version 是 SQL 安全规则版本
    --   schema_policy_hash 是 Schema Policy 内容 hash）
    safety_policy_version VARCHAR(50),

    -- Schema 强绑定（plan §4.5 P0-3）
    schema_snapshot_id BIGINT,
    schema_policy_hash VARCHAR(64),

    -- Dify 调用追踪
    dify_workflow_run_id VARCHAR(100),
    sql_workflow_version VARCHAR(50),

    -- 时间戳
    previewed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- 执行状态机（plan §19 P0-6）
    execution_status VARCHAR(20) NOT NULL DEFAULT 'not_requested',

    -- AWX Collector 关联（Execute 阶段填充；SET NULL 保留 audit 审计）
    collector_run_id BIGINT,
    collector_run_item_id BIGINT,

    -- 执行结果统计
    row_count INTEGER,
    duration_ms INTEGER,

    -- 错误信息
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FK: session_id -> ai_chat_session.id (SET NULL 保留 audit)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_session'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_session
        FOREIGN KEY (session_id) REFERENCES dbops.ai_chat_session(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: message_id -> ai_chat_message.id (SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_message'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_message
        FOREIGN KEY (message_id) REFERENCES dbops.ai_chat_message(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: result_message_id -> ai_chat_message.id (SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_result_message'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_result_message
        FOREIGN KEY (result_message_id) REFERENCES dbops.ai_chat_message(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: user_id -> users.id (SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_user'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_user
        FOREIGN KEY (user_id) REFERENCES dbops.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: instance_id -> db_instance.id (CASCADE：删除实例清空 audit)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_instance'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_instance
        FOREIGN KEY (instance_id) REFERENCES dbops.db_instance(id) ON DELETE CASCADE;
    END IF;
END $$;

-- FK: schema_snapshot_id -> ai_sql_schema_snapshot.id (SET NULL — Snapshot 删除时 audit 保留)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_schema_snapshot'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_schema_snapshot
        FOREIGN KEY (schema_snapshot_id) REFERENCES dbops.ai_sql_schema_snapshot(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: collector_run_id -> collector_run.id (SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_collector_run'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_collector_run
        FOREIGN KEY (collector_run_id) REFERENCES dbops.collector_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: collector_run_item_id -> collector_run_item.id (SET NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_audit_collector_run_item'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT fk_ai_sql_audit_collector_run_item
        FOREIGN KEY (collector_run_item_id) REFERENCES dbops.collector_run_item(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CHECK: db_type_code 白名单（与 C6 snapshot 对齐）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_db_type'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_db_type
        CHECK (db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL', 'MYSQL'));
    END IF;
END $$;

-- CHECK: preview_safety_status 二态
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_preview_safety'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_preview_safety
        CHECK (preview_safety_status IN ('passed', 'rejected'));
    END IF;
END $$;

-- CHECK: execution_safety_status 二态（NULL 表示尚未 Execute 校验）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_execution_safety'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_execution_safety
        CHECK (execution_safety_status IS NULL OR execution_safety_status IN ('passed', 'rejected'));
    END IF;
END $$;

-- CHECK: execution_status 七态机（plan §2.3 line 227-230）
-- 状态转换由应用层条件 UPDATE 控制，CHECK 仅约束枚举值
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_execution_status'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_execution_status
        CHECK (execution_status IN (
            'not_requested', 'pending', 'running', 'success',
            'failed', 'timeout', 'cancelled'
        ));
    END IF;
END $$;

-- CHECK: hash 长度（64 hex chars = SHA-256；NULL 表示尚未生成）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_hash_len'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_hash_len
        CHECK (
            (generated_sql_hash IS NULL OR length(generated_sql_hash) = 64)
            AND (approved_sql_hash IS NULL OR length(approved_sql_hash) = 64)
            AND (schema_policy_hash IS NULL OR length(schema_policy_hash) = 64)
        );
    END IF;
END $$;

-- CHECK: payload 完整性（C12 Preview 阶段 + C17 Execute 阶段共用）
--   preview_safety_status = 'passed':
--     approved_sql/approved_sql_hash/previewed_at/schema_snapshot_id/schema_policy_hash 必填
--     user_question 必填
--   preview_safety_status = 'rejected':
--     preview_safety_reason 必填（用于错误展示）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_audit_payload'
          AND conrelid = 'dbops.ai_sql_audit'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_audit
        ADD CONSTRAINT chk_ai_sql_audit_payload
        CHECK (
            (
                preview_safety_status = 'passed'
                AND user_question IS NOT NULL
                AND approved_sql IS NOT NULL
                AND approved_sql_hash IS NOT NULL
                AND previewed_at IS NOT NULL
                AND schema_snapshot_id IS NOT NULL
                AND schema_policy_hash IS NOT NULL
                AND preview_safety_reason IS NULL
            )
            OR
            (
                preview_safety_status = 'rejected'
                AND preview_safety_reason IS NOT NULL
            )
        );
    END IF;
END $$;

-- Indexes
-- instance_id + created_at DESC：实例维度历史查询
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_instance_created
    ON dbops.ai_sql_audit(instance_id, created_at DESC);

-- user_id + created_at DESC：用户维度历史查询
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_user_created
    ON dbops.ai_sql_audit(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- session_id + created_at ASC：会话内 audit 列表
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_session_created
    ON dbops.ai_sql_audit(session_id, created_at)
    WHERE session_id IS NOT NULL;

-- execution_status 部分索引：执行回调条件 UPDATE 加速
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_execution_status
    ON dbops.ai_sql_audit(execution_status)
    WHERE execution_status IN ('pending', 'running');

-- collector_run_id 部分索引：回调关联加速
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_collector_run
    ON dbops.ai_sql_audit(collector_run_id)
    WHERE collector_run_id IS NOT NULL;

-- schema_snapshot_id 部分索引：Execute 时按 snapshot 反查 audit
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_schema_snapshot
    ON dbops.ai_sql_audit(schema_snapshot_id)
    WHERE schema_snapshot_id IS NOT NULL;

COMMIT;

-- 验证
SELECT 'ai_sql_audit' AS table_name, COUNT(*) AS row_count FROM dbops.ai_sql_audit;