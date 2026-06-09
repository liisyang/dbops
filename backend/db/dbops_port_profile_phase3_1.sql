BEGIN;

SET search_path TO dbops, public;

CREATE TABLE IF NOT EXISTS dbops.port_profile (
    id BIGSERIAL PRIMARY KEY,
    profile_code VARCHAR(100) NOT NULL UNIQUE,
    target_scope VARCHAR(50) NOT NULL,
    endpoint_type VARCHAR(100) NOT NULL,
    db_type_code VARCHAR(50),
    os_family VARCHAR(50),
    protocol VARCHAR(10) NOT NULL DEFAULT 'tcp',
    default_port INTEGER NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT true,
    is_candidate BOOLEAN NOT NULL DEFAULT true,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    priority INTEGER NOT NULL DEFAULT 100,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_port_profile_target_scope
        CHECK (target_scope IN ('server', 'db_instance')),
    CONSTRAINT chk_port_profile_protocol
        CHECK (protocol IN ('tcp', 'udp')),
    CONSTRAINT chk_port_profile_default_port
        CHECK (default_port >= 1 AND default_port <= 65535)
);

CREATE INDEX IF NOT EXISTS idx_port_profile_scope
    ON dbops.port_profile(target_scope);
CREATE INDEX IF NOT EXISTS idx_port_profile_db_type
    ON dbops.port_profile(db_type_code);
CREATE INDEX IF NOT EXISTS idx_port_profile_os_family
    ON dbops.port_profile(os_family);
CREATE INDEX IF NOT EXISTS idx_port_profile_enabled
    ON dbops.port_profile(is_enabled);
CREATE INDEX IF NOT EXISTS idx_port_profile_endpoint_type
    ON dbops.port_profile(endpoint_type);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'dbops'
          AND p.proname = 'set_updated_at'
    ) THEN
        DROP TRIGGER IF EXISTS trg_port_profile_updated_at ON dbops.port_profile;
        CREATE TRIGGER trg_port_profile_updated_at
        BEFORE UPDATE ON dbops.port_profile
        FOR EACH ROW
        EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

INSERT INTO dbops.port_profile (
    profile_code,
    target_scope,
    endpoint_type,
    db_type_code,
    os_family,
    protocol,
    default_port,
    is_required,
    is_candidate,
    is_enabled,
    priority,
    remark
)
VALUES
    ('LINUX_SSH_22', 'server', 'LINUX_SSH', NULL, 'linux', 'tcp', 22, true, true, true, 10, 'Linux SSH default automation port'),
    ('WINDOWS_RDP_3389', 'server', 'WINDOWS_RDP', NULL, 'windows', 'tcp', 3389, true, true, true, 10, 'Windows RDP default management port'),
    ('ORACLE_LISTENER_1521', 'db_instance', 'ORACLE_LISTENER', 'ORACLE', NULL, 'tcp', 1521, true, true, true, 10, 'Oracle default listener port'),
    ('ORACLE_LISTENER_1526', 'db_instance', 'ORACLE_LISTENER', 'ORACLE', NULL, 'tcp', 1526, false, true, true, 20, 'Oracle candidate listener port'),
    ('ORACLE_CUSTOM_1903', 'db_instance', 'ORACLE_CUSTOM_SERVICE', 'ORACLE', NULL, 'tcp', 1903, false, true, true, 30, 'Oracle candidate custom service port'),
    ('SQLSERVER_TDS_1433', 'db_instance', 'SQLSERVER_TDS', 'SQLSERVER', NULL, 'tcp', 1433, true, true, true, 10, 'SQL Server default TDS port'),
    ('SQLSERVER_TDS_3000', 'db_instance', 'SQLSERVER_TDS', 'SQLSERVER', NULL, 'tcp', 3000, false, true, true, 20, 'SQL Server candidate custom TDS port')
ON CONFLICT (profile_code) DO UPDATE
SET
    target_scope = EXCLUDED.target_scope,
    endpoint_type = EXCLUDED.endpoint_type,
    db_type_code = EXCLUDED.db_type_code,
    os_family = EXCLUDED.os_family,
    protocol = EXCLUDED.protocol,
    default_port = EXCLUDED.default_port,
    is_required = EXCLUDED.is_required,
    is_candidate = EXCLUDED.is_candidate,
    is_enabled = EXCLUDED.is_enabled,
    priority = EXCLUDED.priority,
    remark = EXCLUDED.remark,
    updated_at = now();

ALTER TABLE IF EXISTS dbops.collector_run_item
    ADD COLUMN IF NOT EXISTS endpoint_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS port_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE IF EXISTS dbops.collector_run_result
    ADD COLUMN IF NOT EXISTS endpoint_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS protocol VARCHAR(20),
    ADD COLUMN IF NOT EXISTS port_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN;

ALTER TABLE IF EXISTS dbops.asset_endpoint
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS last_item_key VARCHAR(255),
    ADD COLUMN IF NOT EXISTS reachable BOOLEAN,
    ADD COLUMN IF NOT EXISTS port_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE IF EXISTS dbops.asset_change_proposal
    ADD COLUMN IF NOT EXISTS proposal_type VARCHAR(64),
    ADD COLUMN IF NOT EXISTS field_path VARCHAR(255),
    ADD COLUMN IF NOT EXISTS current_value JSONB,
    ADD COLUMN IF NOT EXISTS suggested_value JSONB,
    ADD COLUMN IF NOT EXISTS confidence VARCHAR(20),
    ADD COLUMN IF NOT EXISTS source_run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_item_key VARCHAR(255),
    ADD COLUMN IF NOT EXISTS rejected_by VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_asset_change_proposal_target_field
    ON dbops.asset_change_proposal(entity_type, entity_id, field_path, status);

COMMIT;
