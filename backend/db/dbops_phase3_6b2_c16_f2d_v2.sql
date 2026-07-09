-- =============================================================================
-- Phase 3.6B2 C16-F2d v2 — AI System View Policy: per-instance → per-db_type
-- 2026-07-09
--
-- 背景：
-- - v1 按 instance_id UNIQUE NOT NULL，每个实例独立维护 policy 行
-- - 实际 Oracle/MSSQL/PG 系统视图在同一 DB 类型的所有实例间完全相同
-- - v2 改为 db_type_code 级别默认 + instance_id 可覆盖（nullable）
--
-- 变更：
-- 1. instance_id → nullable（DROP NOT NULL）
-- 2. uq_ai_system_view_policy_instance UNIQUE → partial unique index
--    （WHERE instance_id IS NOT NULL）
-- 3. 新增 partial unique index on db_type_code WHERE instance_id IS NULL
--    （每个 db_type 只能有一条默认行）
-- 4. 数据迁移：从现有 instance policies 生成 db_type 默认行
--
-- 幂等：所有 ALTER / DROP 使用 IF EXISTS / IF NOT EXISTS
-- =============================================================================

-- 1. 取消 instance_id NOT NULL
ALTER TABLE dbops.ai_system_view_policy
    ALTER COLUMN instance_id DROP NOT NULL;

-- 2. 删除旧的 UNIQUE 约束（v1：每个 instance 唯一）
ALTER TABLE dbops.ai_system_view_policy
    DROP CONSTRAINT IF EXISTS uq_ai_system_view_policy_instance;

-- 3. 创建 partial unique index：每个 instance 最多一行
DROP INDEX IF EXISTS dbops.uq_ai_system_view_policy_instance;
CREATE UNIQUE INDEX uq_ai_system_view_policy_instance
    ON dbops.ai_system_view_policy(instance_id) WHERE instance_id IS NOT NULL;

-- 4. 创建 partial unique index：每个 db_type 最多一条默认行
DROP INDEX IF EXISTS dbops.uq_ai_system_view_policy_db_type_default;
CREATE UNIQUE INDEX uq_ai_system_view_policy_db_type_default
    ON dbops.ai_system_view_policy(db_type_code) WHERE instance_id IS NULL;

-- 5. 数据迁移：从现有 instance policies 生成 db_type 默认行
INSERT INTO dbops.ai_system_view_policy (
    instance_id,       -- NULL = db_type 默认行
    db_type_code,
    policy_version,
    allowlist,
    denylist,
    column_hints,
    enabled,
    updated_at,
    created_at
)
SELECT
    NULL                          AS instance_id,
    p.db_type_code,
    p.policy_version,
    p.allowlist,
    p.denylist,
    p.column_hints,
    TRUE                          AS enabled,
    NOW()                         AS updated_at,
    NOW()                         AS created_at
FROM (
    SELECT DISTINCT ON (db_type_code)
        db_type_code,
        policy_version,
        allowlist,
        denylist,
        column_hints
    FROM dbops.ai_system_view_policy
    WHERE enabled = TRUE
    ORDER BY db_type_code, id ASC
) p
WHERE NOT EXISTS (
    SELECT 1 FROM dbops.ai_system_view_policy d
    WHERE d.db_type_code = p.db_type_code
      AND d.instance_id IS NULL
);
