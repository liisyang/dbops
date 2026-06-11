-- ============================================================================
-- DBOPS Phase 3.3A: 凭证中心 + 资产事实采集 + 漂移检测
-- DDL Migration（可重复执行）
-- ============================================================================

-- ============================================================================
-- 1. credential_profile — 凭证引用（只存 AWX credential ID，不存密码）
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.credential_profile (
    id BIGSERIAL PRIMARY KEY,
    profile_code VARCHAR(100) NOT NULL,
    profile_name VARCHAR(200) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    awx_credential_id BIGINT,
    awx_credential_name VARCHAR(200),
    binding_role VARCHAR(50) NOT NULL,
    db_type_code VARCHAR(50),
    os_family VARCHAR(50),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- UNIQUE constraint on profile_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_credential_profile_code'
          AND conrelid = 'dbops.credential_profile'::regclass
    ) THEN
        ALTER TABLE dbops.credential_profile
        ADD CONSTRAINT uq_credential_profile_code UNIQUE (profile_code);
    END IF;
END $$;

-- CHECK constraint: credential_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_profile_type'
          AND conrelid = 'dbops.credential_profile'::regclass
    ) THEN
        ALTER TABLE dbops.credential_profile
        ADD CONSTRAINT chk_credential_profile_type
        CHECK (credential_type IN ('ssh_password', 'ssh_key', 'db_password', 'winrm_password', 'api_token'));
    END IF;
END $$;

-- CHECK constraint: binding_role
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_profile_role'
          AND conrelid = 'dbops.credential_profile'::regclass
    ) THEN
        ALTER TABLE dbops.credential_profile
        ADD CONSTRAINT chk_credential_profile_role
        CHECK (binding_role IN ('os_readonly', 'db_readonly', 'db_monitor', 'db_owner', 'db_admin'));
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_credential_profile_type
    ON dbops.credential_profile(credential_type);
CREATE INDEX IF NOT EXISTS idx_credential_profile_role
    ON dbops.credential_profile(binding_role);
CREATE INDEX IF NOT EXISTS idx_credential_profile_db_type
    ON dbops.credential_profile(db_type_code);
CREATE INDEX IF NOT EXISTS idx_credential_profile_awx_id
    ON dbops.credential_profile(awx_credential_id);
CREATE INDEX IF NOT EXISTS idx_credential_profile_enabled
    ON dbops.credential_profile(is_enabled);

-- Trigger: set_updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_credential_profile_updated_at'
    ) THEN
        CREATE TRIGGER trg_credential_profile_updated_at
        BEFORE UPDATE ON dbops.credential_profile
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 2. credential_binding — 凭证绑定（profile → asset 映射）
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.credential_binding (
    id BIGSERIAL PRIMARY KEY,
    binding_code VARCHAR(100) NOT NULL,
    credential_profile_id BIGINT NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id BIGINT,
    network_zone VARCHAR(100),
    priority INTEGER NOT NULL DEFAULT 100,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- UNIQUE constraint on binding_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_credential_binding_code'
          AND conrelid = 'dbops.credential_binding'::regclass
    ) THEN
        ALTER TABLE dbops.credential_binding
        ADD CONSTRAINT uq_credential_binding_code UNIQUE (binding_code);
    END IF;
END $$;

-- FK to credential_profile
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_credential_binding_profile'
    ) THEN
        ALTER TABLE dbops.credential_binding
        ADD CONSTRAINT fk_credential_binding_profile
        FOREIGN KEY (credential_profile_id) REFERENCES dbops.credential_profile(id) ON DELETE CASCADE;
    END IF;
END $$;

-- CHECK constraint: target_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_binding_target_type'
          AND conrelid = 'dbops.credential_binding'::regclass
    ) THEN
        ALTER TABLE dbops.credential_binding
        ADD CONSTRAINT chk_credential_binding_target_type
        CHECK (target_type IN ('server', 'db_instance', 'cluster', 'business_system', 'network_zone', 'global'));
    END IF;
END $$;

-- CHECK constraint: priority range
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_binding_priority'
          AND conrelid = 'dbops.credential_binding'::regclass
    ) THEN
        ALTER TABLE dbops.credential_binding
        ADD CONSTRAINT chk_credential_binding_priority
        CHECK (priority >= 1 AND priority <= 1000);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_credential_binding_profile
    ON dbops.credential_binding(credential_profile_id);
CREATE INDEX IF NOT EXISTS idx_credential_binding_target
    ON dbops.credential_binding(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_credential_binding_zone
    ON dbops.credential_binding(network_zone);
CREATE INDEX IF NOT EXISTS idx_credential_binding_enabled
    ON dbops.credential_binding(is_enabled);
CREATE INDEX IF NOT EXISTS idx_credential_binding_priority
    ON dbops.credential_binding(priority);

-- Trigger: set_updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_credential_binding_updated_at'
    ) THEN
        CREATE TRIGGER trg_credential_binding_updated_at
        BEFORE UPDATE ON dbops.credential_binding
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 3. asset_fact_snapshot — 事实采集快照（一次采集事件一行）
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.asset_fact_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id BIGINT NOT NULL,
    source_run_id VARCHAR(64),
    source_item_key VARCHAR(255),
    check_code VARCHAR(100),
    collected_at TIMESTAMP NOT NULL DEFAULT now(),
    fact_count INTEGER NOT NULL DEFAULT 0,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now()
);

-- UNIQUE constraint on snapshot_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_asset_fact_snapshot_id'
          AND conrelid = 'dbops.asset_fact_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.asset_fact_snapshot
        ADD CONSTRAINT uq_asset_fact_snapshot_id UNIQUE (snapshot_id);
    END IF;
END $$;

-- CHECK constraint: target_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_fact_snapshot_target_type'
          AND conrelid = 'dbops.asset_fact_snapshot'::regclass
    ) THEN
        ALTER TABLE dbops.asset_fact_snapshot
        ADD CONSTRAINT chk_asset_fact_snapshot_target_type
        CHECK (target_type IN ('server', 'db_instance'));
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_target_time
    ON dbops.asset_fact_snapshot(target_type, target_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_source_run
    ON dbops.asset_fact_snapshot(source_run_id);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_check_code
    ON dbops.asset_fact_snapshot(check_code);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_collected_at
    ON dbops.asset_fact_snapshot(collected_at DESC);

-- ============================================================================
-- 4. asset_fact_value — 单个事实键值（FK → snapshot）
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.asset_fact_value (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL,
    fact_key VARCHAR(255) NOT NULL,
    fact_value JSONB,
    fact_type VARCHAR(50) NOT NULL DEFAULT 'string',
    collected_at TIMESTAMP NOT NULL DEFAULT now(),
    created_at TIMESTAMP DEFAULT now()
);

-- FK to asset_fact_snapshot
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_asset_fact_value_snapshot'
    ) THEN
        ALTER TABLE dbops.asset_fact_value
        ADD CONSTRAINT fk_asset_fact_value_snapshot
        FOREIGN KEY (snapshot_id) REFERENCES dbops.asset_fact_snapshot(id) ON DELETE CASCADE;
    END IF;
END $$;

-- CHECK constraint: fact_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_fact_value_type'
          AND conrelid = 'dbops.asset_fact_value'::regclass
    ) THEN
        ALTER TABLE dbops.asset_fact_value
        ADD CONSTRAINT chk_asset_fact_value_type
        CHECK (fact_type IN ('string', 'integer', 'float', 'boolean', 'json'));
    END IF;
END $$;

-- Unique constraint: one value per key per snapshot
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_asset_fact_value_snapshot_key'
          AND conrelid = 'dbops.asset_fact_value'::regclass
    ) THEN
        ALTER TABLE dbops.asset_fact_value
        ADD CONSTRAINT uq_asset_fact_value_snapshot_key
        UNIQUE (snapshot_id, fact_key);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_fact_value_snapshot
    ON dbops.asset_fact_value(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_fact_value_key
    ON dbops.asset_fact_value(fact_key);

-- ============================================================================
-- 5. asset_drift_record — 漂移检测记录
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.asset_drift_record (
    id BIGSERIAL PRIMARY KEY,
    drift_code VARCHAR(100) NOT NULL,
    snapshot_id BIGINT NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id BIGINT NOT NULL,
    fact_key VARCHAR(255) NOT NULL,
    expected_value JSONB,
    actual_value JSONB,
    drift_type VARCHAR(50) NOT NULL DEFAULT 'mismatch',
    severity VARCHAR(50) NOT NULL DEFAULT 'warning',
    proposal_id BIGINT,
    is_resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- UNIQUE constraint on drift_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_asset_drift_record_code'
          AND conrelid = 'dbops.asset_drift_record'::regclass
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT uq_asset_drift_record_code UNIQUE (drift_code);
    END IF;
END $$;

-- FK to asset_fact_snapshot
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_asset_drift_record_snapshot'
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT fk_asset_drift_record_snapshot
        FOREIGN KEY (snapshot_id) REFERENCES dbops.asset_fact_snapshot(id) ON DELETE CASCADE;
    END IF;
END $$;

-- FK to asset_change_proposal
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_asset_drift_record_proposal'
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT fk_asset_drift_record_proposal
        FOREIGN KEY (proposal_id) REFERENCES dbops.asset_change_proposal(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CHECK constraint: target_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_drift_record_target_type'
          AND conrelid = 'dbops.asset_drift_record'::regclass
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT chk_asset_drift_record_target_type
        CHECK (target_type IN ('server', 'db_instance'));
    END IF;
END $$;

-- CHECK constraint: drift_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_drift_record_drift_type'
          AND conrelid = 'dbops.asset_drift_record'::regclass
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT chk_asset_drift_record_drift_type
        CHECK (drift_type IN ('mismatch', 'missing', 'extra'));
    END IF;
END $$;

-- CHECK constraint: severity
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_drift_record_severity'
          AND conrelid = 'dbops.asset_drift_record'::regclass
    ) THEN
        ALTER TABLE dbops.asset_drift_record
        ADD CONSTRAINT chk_asset_drift_record_severity
        CHECK (severity IN ('critical', 'warning', 'info'));
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_asset_drift_target_time
    ON dbops.asset_drift_record(target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_drift_snapshot
    ON dbops.asset_drift_record(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_asset_drift_proposal
    ON dbops.asset_drift_record(proposal_id);
CREATE INDEX IF NOT EXISTS idx_asset_drift_resolved
    ON dbops.asset_drift_record(is_resolved);
CREATE INDEX IF NOT EXISTS idx_asset_drift_severity
    ON dbops.asset_drift_record(severity);

-- Trigger: set_updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_asset_drift_record_updated_at'
    ) THEN
        CREATE TRIGGER trg_asset_drift_record_updated_at
        BEFORE UPDATE ON dbops.asset_drift_record
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 6. ALTER collector_dispatch_run — 新增凭证分发字段
-- ============================================================================

ALTER TABLE dbops.collector_dispatch_run
ADD COLUMN IF NOT EXISTS credential_strategy VARCHAR(50),
ADD COLUMN IF NOT EXISTS credential_profile_ids JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS credential_group_hash VARCHAR(100);

-- CHECK constraint: credential_strategy
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_dispatch_credential_strategy'
          AND conrelid = 'dbops.collector_dispatch_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_dispatch_run
        ADD CONSTRAINT chk_collector_dispatch_credential_strategy
        CHECK (credential_strategy IS NULL OR credential_strategy IN ('single', 'grouped', 'none'));
    END IF;
END $$;

-- Index for credential_group_hash
CREATE INDEX IF NOT EXISTS idx_collector_dispatch_credential_hash
    ON dbops.collector_dispatch_run(credential_group_hash)
    WHERE credential_group_hash IS NOT NULL;

-- ============================================================================
-- 7. Expand task_type constraint to accommodate DB_SQL_COLLECT
-- ============================================================================

-- Drop and recreate the check constraint with expanded values (idempotent)
-- The existing constraint only allows PORT_CHECK/DB_PORT_DISCOVERY/OS_DISCOVERY.
-- We add DB_SQL_COLLECT for fact collection check codes.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_check_definition_task_type'
          AND conrelid = 'dbops.collector_check_definition'::regclass
    ) THEN
        ALTER TABLE dbops.collector_check_definition
        DROP CONSTRAINT chk_collector_check_definition_task_type;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_check_definition_task_type'
          AND conrelid = 'dbops.collector_check_definition'::regclass
    ) THEN
        ALTER TABLE dbops.collector_check_definition
        ADD CONSTRAINT chk_collector_check_definition_task_type
        CHECK (task_type IN ('PORT_CHECK', 'DB_PORT_DISCOVERY', 'OS_DISCOVERY', 'DB_SQL_COLLECT'));
    END IF;
END $$;

-- ============================================================================
-- 8. Seed: collector_check_definition — 新增 4 个 fact collection check_codes
-- ============================================================================

INSERT INTO dbops.collector_check_definition (check_code, check_name, target_scope, task_type, db_type_code, awx_role, default_timeout_seconds, enabled, config, description)
VALUES
    ('OS_BASIC_FACT_COLLECTION', 'OS Basic Fact Collection', 'server', 'DB_SQL_COLLECT', NULL, 'os_fact_collect', 60, true, '{"collector": "os_basic"}', 'Collect OS basic facts via SSH (hostname, CPU, memory, OS version)'),
    ('DB_BASIC_FACT_COLLECTION', 'DB Basic Fact Collection', 'db_instance', 'DB_SQL_COLLECT', NULL, 'db_fact_collect', 60, true, '{"collector": "db_basic"}', 'Collect DB basic facts (instance name, version, role)'),
    ('DB_VERSION_FACT_COLLECTION', 'DB Version Fact Collection', 'db_instance', 'DB_SQL_COLLECT', NULL, 'db_fact_collect', 60, true, '{"collector": "db_version"}', 'Collect DB version details (version_full, patch level, edition)'),
    ('DB_ROLE_FACT_COLLECTION', 'DB Role Fact Collection', 'db_instance', 'DB_SQL_COLLECT', NULL, 'db_fact_collect', 60, true, '{"collector": "db_role"}', 'Collect DB role facts (HA role, replica status, cluster membership)')
ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    db_type_code = EXCLUDED.db_type_code,
    awx_role = EXCLUDED.awx_role,
    default_timeout_seconds = EXCLUDED.default_timeout_seconds,
    config = EXCLUDED.config,
    description = EXCLUDED.description,
    updated_at = now();

-- ============================================================================
-- 9. ALTER credential_profile — 补充 usage_scope / network_zone / environment / extra_attrs
-- ============================================================================

ALTER TABLE dbops.credential_profile
  ADD COLUMN IF NOT EXISTS usage_scope VARCHAR(50),
  ADD COLUMN IF NOT EXISTS network_zone VARCHAR(100),
  ADD COLUMN IF NOT EXISTS environment VARCHAR(50),
  ADD COLUMN IF NOT EXISTS extra_attrs JSONB DEFAULT '{}'::jsonb;

-- CHECK constraint: usage_scope
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_profile_usage_scope'
          AND conrelid = 'dbops.credential_profile'::regclass
    ) THEN
        ALTER TABLE dbops.credential_profile
        ADD CONSTRAINT chk_credential_profile_usage_scope
        CHECK (usage_scope IS NULL OR usage_scope IN ('server', 'db_instance'));
    END IF;
END $$;

-- CHECK constraint: environment
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_profile_environment'
          AND conrelid = 'dbops.credential_profile'::regclass
    ) THEN
        ALTER TABLE dbops.credential_profile
        ADD CONSTRAINT chk_credential_profile_environment
        CHECK (environment IS NULL OR environment IN ('prod', 'staging', 'dev', 'test'));
    END IF;
END $$;

-- Indexes for new columns
CREATE INDEX IF NOT EXISTS idx_credential_profile_usage_scope
    ON dbops.credential_profile(usage_scope);
CREATE INDEX IF NOT EXISTS idx_credential_profile_network_zone
    ON dbops.credential_profile(network_zone);
CREATE INDEX IF NOT EXISTS idx_credential_profile_environment
    ON dbops.credential_profile(environment);

-- ============================================================================
-- 10. ALTER credential_binding — 补充 binding_role / extra_attrs
-- ============================================================================

ALTER TABLE dbops.credential_binding
  ADD COLUMN IF NOT EXISTS binding_role VARCHAR(50),
  ADD COLUMN IF NOT EXISTS extra_attrs JSONB DEFAULT '{}'::jsonb;

-- CHECK constraint: binding_role on credential_binding
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_credential_binding_role'
          AND conrelid = 'dbops.credential_binding'::regclass
    ) THEN
        ALTER TABLE dbops.credential_binding
        ADD CONSTRAINT chk_credential_binding_role
        CHECK (binding_role IS NULL OR binding_role IN ('os_readonly', 'db_readonly', 'db_monitor', 'db_owner', 'db_admin'));
    END IF;
END $$;

-- Index for binding_role
CREATE INDEX IF NOT EXISTS idx_credential_binding_role
    ON dbops.credential_binding(binding_role);
