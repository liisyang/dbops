-- ============================================================================
-- DBOPS Phase 3.3A — Credential Management + Fact Collection + Drift Detection
-- ============================================================================
-- Run against the target database AFTER reviewing:
--   psql -h <host> -U <user> -d dbops -f backend/db/dbops_phase3_3a.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. credential_profile — stores AWX credential reference ONLY (no passwords)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dbops.credential_profile (
    id BIGSERIAL PRIMARY KEY,
    profile_code VARCHAR(100) NOT NULL,
    profile_name VARCHAR(200) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,      -- ssh_key, ssh_password, db_password, winrm_password, api_token
    awx_credential_id INTEGER NOT NULL,
    awx_credential_name VARCHAR(200),
    db_type_code VARCHAR(50),                  -- oracle, sqlserver, postgresql, mysql
    os_family VARCHAR(50),                     -- linux, windows
    default_database VARCHAR(100),             -- master, postgres, etc.
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    remark TEXT,
    extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_credential_profile_code UNIQUE (profile_code),
    CONSTRAINT ck_credential_profile_type CHECK (
        credential_type IN ('ssh_key', 'ssh_password', 'db_password', 'winrm_password', 'api_token')
    )
);

CREATE INDEX IF NOT EXISTS idx_credential_profile_awx ON dbops.credential_profile(awx_credential_id);
CREATE INDEX IF NOT EXISTS idx_credential_profile_db_type ON dbops.credential_profile(db_type_code) WHERE db_type_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_credential_profile_enabled ON dbops.credential_profile(is_enabled);

-- ----------------------------------------------------------------------------
-- 2. credential_binding — binds profiles to targets with priority chain
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dbops.credential_binding (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES dbops.credential_profile(id) ON DELETE CASCADE,
    binding_role VARCHAR(50) NOT NULL,         -- db_readonly, db_monitor, os_readonly, os_sudo
    binding_target_type VARCHAR(50) NOT NULL,  -- server, db_instance, cluster, business_system, network_zone, global
    binding_target_id BIGINT,                  -- FK to target table (nullable for network_zone/global)
    network_zone VARCHAR(100),                 -- used when binding_target_type = network_zone
    priority INTEGER NOT NULL DEFAULT 100,     -- lower = higher priority
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    remark TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_credential_binding UNIQUE NULLS NOT DISTINCT (profile_id, binding_role, binding_target_type, binding_target_id, network_zone)
);

CREATE INDEX IF NOT EXISTS idx_credential_binding_target ON dbops.credential_binding(binding_target_type, binding_target_id) WHERE binding_target_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_credential_binding_role ON dbops.credential_binding(binding_role);
CREATE INDEX IF NOT EXISTS idx_credential_binding_profile ON dbops.credential_binding(profile_id);
CREATE INDEX IF NOT EXISTS idx_credential_binding_nz ON dbops.credential_binding(network_zone) WHERE network_zone IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. asset_fact_snapshot — one row per collection event
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dbops.asset_fact_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    collector_run_id BIGINT NOT NULL REFERENCES dbops.collector_run(id),
    item_key VARCHAR(255) NOT NULL,
    check_code VARCHAR(100) NOT NULL,
    target_type VARCHAR(50) NOT NULL,          -- server, db_instance
    target_id BIGINT NOT NULL,
    target_host VARCHAR(255) NOT NULL,
    target_port INTEGER,
    db_type_code VARCHAR(50),
    credential_profile_id BIGINT REFERENCES dbops.credential_profile(id),
    snapshot_status VARCHAR(32) NOT NULL DEFAULT 'ok',
    error_code VARCHAR(100),                   -- CREDENTIAL_MISSING, CONNECTION_FAILED, PERMISSION_DENIED, etc.
    raw_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_asset_fact_snapshot_id UNIQUE (snapshot_id),
    CONSTRAINT uq_asset_fact_snapshot_item UNIQUE (collector_run_id, item_key),
    CONSTRAINT ck_asset_fact_snapshot_target_type CHECK (target_type IN ('server', 'db_instance')),
    CONSTRAINT ck_asset_fact_snapshot_status CHECK (snapshot_status IN ('ok', 'partial', 'error', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_fact_snapshot_target ON dbops.asset_fact_snapshot(target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_run ON dbops.asset_fact_snapshot(run_id);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_check_code ON dbops.asset_fact_snapshot(check_code);

-- ----------------------------------------------------------------------------
-- 4. asset_fact_value — individual fact key-values, FK to snapshot
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dbops.asset_fact_value (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES dbops.asset_fact_snapshot(id) ON DELETE CASCADE,
    fact_key VARCHAR(200) NOT NULL,
    fact_value JSONB,
    fact_category VARCHAR(100),                -- basic, version, role, config
    source_query TEXT,                         -- for audit trail (what was queried)
    is_null BOOLEAN NOT NULL DEFAULT FALSE,
    collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_value_snapshot ON dbops.asset_fact_value(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_fact_value_key ON dbops.asset_fact_value(fact_key);
CREATE INDEX IF NOT EXISTS idx_fact_value_category ON dbops.asset_fact_value(fact_category);

-- ----------------------------------------------------------------------------
-- 5. asset_drift_record — independent drift audit trail
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dbops.asset_drift_record (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES dbops.asset_fact_snapshot(id),
    proposal_id BIGINT REFERENCES dbops.asset_change_proposal(id),
    target_type VARCHAR(50) NOT NULL,
    target_id BIGINT NOT NULL,
    field_path VARCHAR(255),
    expected_value JSONB,
    actual_value JSONB,
    drift_type VARCHAR(50) NOT NULL,           -- value_mismatch, missing, extra, type_change
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT ck_asset_drift_record_type CHECK (drift_type IN ('value_mismatch', 'missing', 'extra', 'type_change')),
    CONSTRAINT ck_asset_drift_record_severity CHECK (severity IN ('info', 'warning', 'critical'))
);

CREATE INDEX IF NOT EXISTS idx_drift_record_target ON dbops.asset_drift_record(target_type, target_id, resolved);
CREATE INDEX IF NOT EXISTS idx_drift_record_snapshot ON dbops.asset_drift_record(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_drift_record_proposal ON dbops.asset_drift_record(proposal_id) WHERE proposal_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drift_record_unresolved ON dbops.asset_drift_record(severity, created_at DESC) WHERE resolved = FALSE;

-- ----------------------------------------------------------------------------
-- ALTER: collector_dispatch_run — add credential columns
-- ----------------------------------------------------------------------------
ALTER TABLE dbops.collector_dispatch_run
    ADD COLUMN IF NOT EXISTS credential_strategy VARCHAR(50),
    ADD COLUMN IF NOT EXISTS credential_profile_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS credential_group_hash VARCHAR(100);

COMMENT ON COLUMN dbops.collector_dispatch_run.credential_strategy IS 'Credential resolution strategy (e.g. best_match, per_item)';
COMMENT ON COLUMN dbops.collector_dispatch_run.credential_profile_ids IS 'JSON array of credential_profile.id values used in this dispatch';
COMMENT ON COLUMN dbops.collector_dispatch_run.credential_group_hash IS 'SHA256 hex digest of sorted credential references for dispatch grouping';

-- ----------------------------------------------------------------------------
-- ALTER: collector_check_definition — allow new task_type values
-- ----------------------------------------------------------------------------
ALTER TABLE dbops.collector_check_definition
    DROP CONSTRAINT IF EXISTS chk_collector_check_definition_task_type;

ALTER TABLE dbops.collector_check_definition
    ADD CONSTRAINT chk_collector_check_definition_task_type
    CHECK (task_type IN ('PORT_CHECK', 'DB_PORT_DISCOVERY', 'OS_DISCOVERY', 'DB_SQL_COLLECT', 'OS_FACT_COLLECT'));

-- ----------------------------------------------------------------------------
-- SEED: new check_code definitions
-- ----------------------------------------------------------------------------
INSERT INTO dbops.collector_check_definition (check_code, check_name, target_scope, task_type, awx_role, default_timeout_seconds, enabled, config, description)
VALUES
    ('OS_BASIC_FACT_COLLECTION', 'OS基础信息采集', 'server', 'OS_FACT_COLLECT', 'os_fact_collect', 30, TRUE, '{}'::jsonb, '采集服务器主机名、OS版本、CPU、内存、磁盘、网络等基础信息'),
    ('DB_BASIC_FACT_COLLECTION', 'DB基础信息采集', 'db_instance', 'DB_SQL_COLLECT', 'db_fact_collect', 30, TRUE, '{}'::jsonb, '采集数据库实例名、版本、运行模式、启动时间等基础信息'),
    ('DB_VERSION_FACT_COLLECTION', 'DB版本信息采集', 'db_instance', 'DB_SQL_COLLECT', 'db_fact_collect', 30, TRUE, '{}'::jsonb, '采集数据库详细版本号、补丁级别、已安装组件'),
    ('DB_ROLE_FACT_COLLECTION', 'DB角色信息采集', 'db_instance', 'DB_SQL_COLLECT', 'db_fact_collect', 30, TRUE, '{}'::jsonb, '采集数据库高可用角色（Primary/Standby/Single）')
ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    awx_role = EXCLUDED.awx_role,
    default_timeout_seconds = EXCLUDED.default_timeout_seconds,
    description = EXCLUDED.description;

COMMIT;
