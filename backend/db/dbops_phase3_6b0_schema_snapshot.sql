-- ============================================================================
-- DBOPS Phase 3.6B0: AI Copilot - SQL Schema Snapshot
-- DDL Migration（可重复执行；幂等）
--
-- 表:
--   1. ai_sql_schema_snapshot - 数据库结构快照（instance + database 维度）
--
-- 关键约束（plan §2.2 line 113-155）:
--   - status 五态机: pending / running / success / failed / unavailable
--   - 状态机完整性 CHECK: success 时必填字段齐; failed/unavailable 时 error_message 必须有
--   - 部分唯一索引: 同一 (instance_id, database_name) 同时只有一个 is_current=true
--     → 两阶段发布：旧 snapshot 在新 snapshot 切到 is_current=true 时被改 is_current=false
--   - 过期清理: 成功 snapshot 默认 24h 过期（expires_at；C10 service 端控制 TTL）
--
-- 依赖（pre-existing）:
--   - dbops.db_instance(id)        — 实例主表
--   - dbops.collector_run(id)      — AWX 采集运行记录
--
-- 不在 C6 范围（明确避免 scope creep）:
--   ❌ PostgreSQL 固定元数据 SQL 模板    → C7
--   ❌ Collector Builder + Role + Playbook → C8
--   ❌ Callback 落库服务                  → C9
--   ❌ API 端点 + AiSchemaContextService  → C10
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_sql_schema_snapshot — 数据库结构快照
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.ai_sql_schema_snapshot (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    db_type_code VARCHAR(50) NOT NULL,
    -- database_name 不允许 NULL：无明确 database 时存 '<default>'（plan line 146）
    database_name VARCHAR(200) NOT NULL,
    schema_name VARCHAR(200),
    -- 五态机：pending / running / success / failed / unavailable
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- 白名单：采集到的 schema / table / column 列表（C7+ 填充）
    allowed_schemas JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- {schema.table: [col1, col2]} 格式
    allowed_columns JSONB NOT NULL DEFAULT '{}'::jsonb,
    denied_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 两阶段发布标志：同时只允许一行 is_current=true
    is_current BOOLEAN NOT NULL DEFAULT false,
    -- 关联 AWX 采集运行（删除 collector_run 时置 NULL，保留 snapshot 审计）
    collector_run_id BIGINT,
    -- SHA-256 hex (64 chars)；pending/running 阶段为 NULL
    snapshot_hash VARCHAR(64),
    -- 统计：成功时填充
    total_tables INTEGER,
    total_columns INTEGER,
    -- TTL：成功时必须设置（C10 service 端按 AI_SCHEMA_SNAPSHOT_TTL_HOURS 计算）
    expires_at TIMESTAMPTZ,
    -- 错误：failed / unavailable 时 error_message 必须有
    error_code VARCHAR(100),
    error_message TEXT,
    -- 实际采集完成时间：成功时必须设置
    collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FK: instance_id -> db_instance.id (CASCADE：删除实例清空 snapshot)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_schema_snapshot_instance'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT fk_ai_sql_schema_snapshot_instance
        FOREIGN KEY (instance_id) REFERENCES dbops.db_instance(id) ON DELETE CASCADE;
    END IF;
END $$;

-- FK: collector_run_id -> collector_run.id (SET NULL 保留 snapshot 审计)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_sql_schema_snapshot_collector_run'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT fk_ai_sql_schema_snapshot_collector_run
        FOREIGN KEY (collector_run_id) REFERENCES dbops.collector_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CHECK: db_type_code 白名单
-- 首版仅 PostgreSQL 真正落地（plan §4.8），其他 db_type 预留 capability
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_schema_snapshot_db_type'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT chk_ai_sql_schema_snapshot_db_type
        CHECK (db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL', 'MYSQL'));
    END IF;
END $$;

-- CHECK: status 五态机
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_schema_snapshot_status'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT chk_ai_sql_schema_snapshot_status
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'unavailable'));
    END IF;
END $$;

-- CHECK: 状态机完整性（plan §2.2 line 124-143 P0-2 修正）
-- success 时必填字段齐（snapshot_hash / allowed_schemas / collected_at / expires_at）
-- failed/unavailable 时 error_message 必须有
-- pending/running 时 error_code / error_message 必须 NULL（尚未失败）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_schema_snapshot_payload'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT chk_ai_sql_schema_snapshot_payload
        CHECK (
            (status = 'success'
             AND snapshot_hash IS NOT NULL
             AND allowed_schemas IS NOT NULL
             AND collected_at IS NOT NULL
             AND expires_at IS NOT NULL)
            OR
            (status IN ('pending', 'running')
             AND error_message IS NULL
             AND error_code IS NULL)
            OR
            (status IN ('failed', 'unavailable')
             AND error_message IS NOT NULL)
        );
    END IF;
END $$;

-- CHECK: snapshot_hash 长度（64 hex chars = SHA-256）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_sql_schema_snapshot_hash_len'
          AND conrelid = 'dbops.ai_sql_schema_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_sql_schema_snapshot
        ADD CONSTRAINT chk_ai_sql_schema_snapshot_hash_len
        CHECK (snapshot_hash IS NULL OR length(snapshot_hash) = 64);
    END IF;
END $$;

-- 关键：部分唯一索引（plan §2.2 line 153-155）
-- 同一 (instance_id, database_name) 同时只允许一个 is_current=true
-- 两阶段发布：新 snapshot 成功后才将旧的 is_current 切 false，再设新的 true
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_ai_sql_schema_snapshot_current'
    ) THEN
        CREATE UNIQUE INDEX uq_ai_sql_schema_snapshot_current
            ON dbops.ai_sql_schema_snapshot (instance_id, database_name)
            WHERE is_current = true;
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_sql_schema_snapshot_instance_status
    ON dbops.ai_sql_schema_snapshot(instance_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_sql_schema_snapshot_collector_run
    ON dbops.ai_sql_schema_snapshot(collector_run_id)
    WHERE collector_run_id IS NOT NULL;
-- 过期清理索引：仅 success 状态的 expires_at 才有意义
CREATE INDEX IF NOT EXISTS idx_ai_sql_schema_snapshot_expires_at
    ON dbops.ai_sql_schema_snapshot(expires_at)
    WHERE status = 'success';

COMMIT;

-- 验证
SELECT 'ai_sql_schema_snapshot' AS table_name, COUNT(*) AS row_count FROM dbops.ai_sql_schema_snapshot;
