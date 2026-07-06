-- ============================================================================
-- DBOPS Phase 3.6B0 F3 (C16-F3): AI Copilot - Object Metadata Snapshot
-- DDL Migration（可重复执行；幂等）
--
-- 表:
--   1. ai_object_metadata_snapshot - 数据库对象 DDL 快照（instance + database + schema 维度）
--
-- 关键约束（与 plan §2.2 + §4 + F3 段落对齐）:
--   - status 五态机: pending / running / success / failed / unavailable
--   - 状态机完整性 CHECK: success 时必填字段齐; failed/unavailable 时 error_message 必须有
--   - 部分唯一索引: 同一 (instance_id, database_name, schema_name) 同时只有一个 is_current=true
--     → 两阶段发布：旧 snapshot 在新 snapshot 切到 is_current=true 时被改 is_current=false
--   - 过期清理: 成功 snapshot 默认 24h 过期（expires_at；callback service 端控制 TTL）
--
-- 依赖（pre-existing）:
--   - dbops.db_instance(id)        — 实例主表
--   - dbops.collector_run(id)      — AWX 采集运行记录
--
-- 与 C6 ai_sql_schema_snapshot 的差异（设计意图）:
--   - 概念独立：DDL 文本（object_ddl_text）vs 列元数据（allowed_*）
--   - partial unique 加 schema_name 维度（DDL 粒度更细）
--   - 不依赖 ai_sql_schema_snapshot 任何字段（独立 FK）
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_object_metadata_snapshot — 数据库对象 DDL 快照
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.ai_object_metadata_snapshot (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    db_type_code VARCHAR(50) NOT NULL,
    -- database_name 不允许 NULL：无明确 database 时存 '<default>'（与 C9 callback 一致）
    database_name VARCHAR(200) NOT NULL,
    schema_name VARCHAR(200) NOT NULL,

    -- 五态机：pending / running / success / failed / unavailable
    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- DDL 文本聚合（仅 success 时填充，1MB 截断兜底）
    object_ddl_text TEXT,
    object_ddl_sha256 VARCHAR(64),

    -- 对象计数（仅 success 时填充）
    table_count INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    index_count INTEGER NOT NULL DEFAULT 0,
    function_count INTEGER NOT NULL DEFAULT 0,
    total_object_count INTEGER NOT NULL DEFAULT 0,

    -- 两阶段发布标志：同时只允许一行 is_current=true
    is_current BOOLEAN NOT NULL DEFAULT false,

    -- 关联 AWX 采集运行（删除 collector_run 时置 NULL，保留 snapshot 审计）
    collector_run_id BIGINT,
    -- SHA-256 hex (64 chars) of canonical JSON (columns, rows)
    snapshot_hash VARCHAR(64),

    -- TTL：成功时必须设置（callback service 端按 AI_OBJECT_METADATA_TTL_HOURS 计算）
    expires_at TIMESTAMPTZ,
    -- 实际采集完成时间：成功时必须设置
    collected_at TIMESTAMPTZ,

    -- 错误：failed / unavailable 时 error_message 必须有
    error_code VARCHAR(100),
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FK: instance_id -> db_instance.id (CASCADE：删除实例清空 snapshot)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_object_metadata_snapshot_instance'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT fk_ai_object_metadata_snapshot_instance
        FOREIGN KEY (instance_id) REFERENCES dbops.db_instance(id) ON DELETE CASCADE;
    END IF;
END $$;

-- FK: collector_run_id -> collector_run.id (SET NULL 保留 snapshot 审计)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_object_metadata_snapshot_collector_run'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT fk_ai_object_metadata_snapshot_collector_run
        FOREIGN KEY (collector_run_id) REFERENCES dbops.collector_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CHECK: db_type_code 白名单
-- 首版仅 PostgreSQL 真正落地（plan §4.8 P1），其他 db_type 预留 capability
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_object_metadata_snapshot_db_type'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT chk_ai_object_metadata_snapshot_db_type
        CHECK (db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL', 'MYSQL'));
    END IF;
END $$;

-- CHECK: status 五态机
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_object_metadata_snapshot_status'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT chk_ai_object_metadata_snapshot_status
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'unavailable'));
    END IF;
END $$;

-- CHECK: 状态机完整性（与 C8 chk_ai_sql_schema_snapshot_payload 对齐）
-- success 时必填字段齐（object_ddl_text / object_ddl_sha256 / collected_at / expires_at）
-- failed/unavailable 时 error_message 必须有
-- pending/running 时 error_code / error_message 必须 NULL（尚未失败）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_object_metadata_snapshot_payload'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT chk_ai_object_metadata_snapshot_payload
        CHECK (
            (status = 'success'
             AND object_ddl_text IS NOT NULL
             AND object_ddl_sha256 IS NOT NULL
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

-- CHECK: hash 长度（64 hex chars = SHA-256）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_object_metadata_snapshot_hash_len'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT chk_ai_object_metadata_snapshot_hash_len
        CHECK (object_ddl_sha256 IS NULL OR length(object_ddl_sha256) = 64);
    END IF;
END $$;

-- CHECK: snapshot_hash 长度（与 C8 一致，64 hex chars = SHA-256）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ai_object_metadata_snapshot_snapshot_hash_len'
          AND conrelid = 'dbops.ai_object_metadata_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.ai_object_metadata_snapshot
        ADD CONSTRAINT chk_ai_object_metadata_snapshot_snapshot_hash_len
        CHECK (snapshot_hash IS NULL OR length(snapshot_hash) = 64);
    END IF;
END $$;

-- 关键：部分唯一索引（plan §2.2 line 153-155 + F3 维度加 schema_name）
-- 同一 (instance_id, database_name, schema_name) 同时只允许一个 is_current=true
-- 两阶段发布：新 snapshot 成功后才将旧的 is_current 切 false，再设新的 true
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_ai_object_metadata_snapshot_current'
    ) THEN
        CREATE UNIQUE INDEX uq_ai_object_metadata_snapshot_current
            ON dbops.ai_object_metadata_snapshot (instance_id, database_name, schema_name)
            WHERE is_current = true;
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_object_metadata_snapshot_instance_status
    ON dbops.ai_object_metadata_snapshot(instance_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_object_metadata_snapshot_collector_run
    ON dbops.ai_object_metadata_snapshot(collector_run_id)
    WHERE collector_run_id IS NOT NULL;
-- 过期清理索引：仅 success 状态的 expires_at 才有意义
CREATE INDEX IF NOT EXISTS idx_ai_object_metadata_snapshot_expires_at
    ON dbops.ai_object_metadata_snapshot(expires_at)
    WHERE status = 'success';
-- schema 维度查询索引：history / context 端点常用
CREATE INDEX IF NOT EXISTS idx_ai_object_metadata_snapshot_schema
    ON dbops.ai_object_metadata_snapshot(instance_id, schema_name);

COMMIT;

-- 验证
SELECT 'ai_object_metadata_snapshot' AS table_name, COUNT(*) AS row_count FROM dbops.ai_object_metadata_snapshot;
