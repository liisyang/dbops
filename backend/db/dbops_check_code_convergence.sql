-- =============================================================================
-- 资产校验功能优化 v2 — DB Seed 数据迁移 (Phase 2a)
-- Date: 2026-06-17
-- Description: 收敛 check_code 与 inspection_item 定义
--   - 禁用旧 check_code (DB_VERSION_FACT_COLLECTION / DB_ROLE_FACT_COLLECTION /
--     SSH_PORT_REACHABILITY / PORT_CANDIDATE_REACHABILITY)
--   - 新增 OS_PORT_REACHABILITY
--   - 修正 OS_BASIC_FACT_COLLECTION 的 task_type (DB_SQL_COLLECT → OS_DISCOVERY)
--   - 幂等补 DB_PORT_REACHABILITY 定义
--   - 收敛 inspection_item (CONNECTIVITY_DB_PORT / CONNECTIVITY_OS_PORT /
--     DB_FACT_DRIFT_DETECTED；禁用旧项)
--
-- ⚠️  执行前必须先备份:
--   CREATE TABLE dbops.collector_check_definition_bak_20260617 AS
--     SELECT * FROM dbops.collector_check_definition;
--   CREATE TABLE dbops.inspection_item_bak_20260617 AS
--     SELECT * FROM dbops.inspection_item;
-- =============================================================================

BEGIN;

-- 1. 禁用旧 check_code（保留行以便历史任务展示）
UPDATE dbops.collector_check_definition
SET enabled = false, updated_at = now()
WHERE check_code IN (
    'SSH_PORT_REACHABILITY',
    'PORT_CANDIDATE_REACHABILITY',
    'DB_VERSION_FACT_COLLECTION',
    'DB_ROLE_FACT_COLLECTION'
);

-- 2. 新增 OS_PORT_REACHABILITY（OS 采集通道连通性：Linux SSH 22 / Windows WinRM 5985）
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES (
    'OS_PORT_REACHABILITY', 'OS管理端口连通性检查', 'server', 'PORT_CHECK',
    5, true, '{}'::jsonb, '检查服务器OS采集通道端口是否可达（Linux SSH 22 / Windows WinRM 5985）', now(), now()
) ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    updated_at = now();

-- 3. 修正 OS_BASIC_FACT_COLLECTION 的 task_type（OS_BASIC 应是 OS_DISCOVERY）
UPDATE dbops.collector_check_definition
SET task_type = 'OS_DISCOVERY', updated_at = now()
WHERE check_code = 'OS_BASIC_FACT_COLLECTION' AND task_type = 'DB_SQL_COLLECT';

-- 4. 确保 DB_PORT_REACHABILITY 存在（幂等）
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES (
    'DB_PORT_REACHABILITY', 'DB端口连通性检查（含候选端口探测）', 'db_instance', 'PORT_CHECK',
    5, true, '{}'::jsonb, '检查数据库实例端口是否可达（含 PortProfile 候选端口探测）', now(), now()
) ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    default_timeout_seconds = EXCLUDED.default_timeout_seconds,
    enabled = true,
    config = EXCLUDED.config,
    description = EXCLUDED.description,
    updated_at = now();

-- 5. inspection_item — 禁用旧项
UPDATE dbops.inspection_item
SET enabled = false, updated_at = now()
WHERE item_code IN (
    'CONNECTIVITY_PORT_REACHABLE',   -- 由 CONNECTIVITY_DB_PORT 替代
    'DB_VERSION_COLLECTED',          -- 合并到 DB_BASIC_FACT_COLLECTION
    'DB_ROLE_COLLECTED',             -- 合并到 DB_BASIC_FACT_COLLECTION
    'DB_ROLE_CHANGED',               -- 由 DB_FACT_DRIFT_DETECTED 替代
    'INSTANCE_PORT_DRIFT'            -- 由 CONNECTIVITY_DB_PORT 替代
);

-- 6. inspection_item — 新增/更新收敛项（幂等）
INSERT INTO dbops.inspection_item (
    item_code, item_name, check_code, target_scope, severity, enabled,
    description, rule_config, created_at, updated_at
) VALUES
    ('CONNECTIVITY_DB_PORT', 'DB端口连通性', 'DB_PORT_REACHABILITY', 'db_instance', 'critical', true,
     '数据库实例端口 TCP 连通性检查', '{}'::jsonb, now(), now()),
    ('CONNECTIVITY_OS_PORT', 'OS端口连通性', 'OS_PORT_REACHABILITY', 'server', 'critical', true,
     '服务器OS采集通道端口连通性检查', '{}'::jsonb, now(), now()),
    ('DB_FACT_DRIFT_DETECTED', 'DB事实字段漂移', 'DB_BASIC_FACT_COLLECTION', 'db_instance', 'warning', true,
     'DB基础事实采集后发现实例名、服务名、角色等字段与CMDB不一致',
     '{"fields":["instance_name","service_name","node_role","port"]}'::jsonb, now(), now())
ON CONFLICT (item_code) DO UPDATE SET
    item_name = EXCLUDED.item_name,
    check_code = EXCLUDED.check_code,
    target_scope = EXCLUDED.target_scope,
    severity = EXCLUDED.severity,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    rule_config = EXCLUDED.rule_config,
    updated_at = now();

-- 7. CLUSTER_TYPE_MISMATCH（cluster_type 提示巡检项；本次仅作为 AssetVerifyReport 提示）
--    target_scope=db_instance（CHECK 约束），rule_config.derived_target_type=cluster
INSERT INTO dbops.inspection_item (
    item_code, item_name, check_code, target_scope, severity, enabled,
    description, rule_config, created_at, updated_at
) VALUES (
    'CLUSTER_TYPE_MISMATCH', '集群类型不匹配',
    'DB_BASIC_FACT_COLLECTION', 'db_instance', 'warning', true,
    '从实例角色采集推断的集群类型与CMDB记录不一致',
    '{"derived_target_type":"cluster","auto_proposal":false}'::jsonb,
    now(), now()
) ON CONFLICT (item_code) DO UPDATE SET
    item_name = EXCLUDED.item_name,
    check_code = EXCLUDED.check_code,
    target_scope = EXCLUDED.target_scope,
    severity = EXCLUDED.severity,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    rule_config = EXCLUDED.rule_config,
    updated_at = now();

-- 8. 补旧 check_code 的 disabled 定义（保证历史任务展示有名称）
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES
    ('SSH_PORT_REACHABILITY', '旧版SSH端口连通性检查', 'server', 'PORT_CHECK',
     5, false, '{}'::jsonb, '旧版检查项，已由 OS_PORT_REACHABILITY 替代', now(), now()),
    ('PORT_CANDIDATE_REACHABILITY', '旧版候选端口连通性检查', 'db_instance', 'PORT_CHECK',
     5, false, '{}'::jsonb, '旧版检查项，已合并到 DB_PORT_REACHABILITY', now(), now()),
    ('DB_VERSION_FACT_COLLECTION', '旧版DB版本事实采集', 'db_instance', 'DB_SQL_COLLECT',
     60, false, '{}'::jsonb, '旧版检查项，已合并到 DB_BASIC_FACT_COLLECTION', now(), now()),
    ('DB_ROLE_FACT_COLLECTION', '旧版DB角色事实采集', 'db_instance', 'DB_SQL_COLLECT',
     60, false, '{}'::jsonb, '旧版检查项，已合并到 DB_BASIC_FACT_COLLECTION', now(), now())
ON CONFLICT (check_code) DO UPDATE SET
    enabled = false,
    updated_at = now();

COMMIT;
