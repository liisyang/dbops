BEGIN;

SET search_path TO dbops, public;

ALTER TABLE IF EXISTS dbops.collector_run
    ADD COLUMN IF NOT EXISTS target_scope VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    ADD COLUMN IF NOT EXISTS server_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS item_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS dbops.collector_run
    ALTER COLUMN db_instance_id DROP NOT NULL;

ALTER TABLE IF EXISTS dbops.collector_run
    ALTER COLUMN target_host DROP NOT NULL;

ALTER TABLE IF EXISTS dbops.collector_run
    ALTER COLUMN target_port DROP NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_collector_run_status'
          AND conrelid = 'dbops.collector_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run DROP CONSTRAINT chk_collector_run_status;
    END IF;

    ALTER TABLE dbops.collector_run
        ADD CONSTRAINT chk_collector_run_status
        CHECK (status IN ('pending', 'launched', 'running', 'success', 'partial_success', 'failed', 'callback_failed', 'timeout', 'canceled'));

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_collector_run_target_scope'
          AND conrelid = 'dbops.collector_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run
            ADD CONSTRAINT chk_collector_run_target_scope
            CHECK (target_scope IN ('db_instance', 'server', 'mixed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_collector_run_item_count'
          AND conrelid = 'dbops.collector_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run
            ADD CONSTRAINT chk_collector_run_item_count
            CHECK (item_count >= 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_collector_run_server_time
    ON dbops.collector_run(server_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_target_scope
    ON dbops.collector_run(target_scope);

CREATE TABLE IF NOT EXISTS dbops.collector_check_definition (
    id BIGSERIAL PRIMARY KEY,
    check_code VARCHAR(100) NOT NULL UNIQUE,
    check_name VARCHAR(200) NOT NULL,
    target_scope VARCHAR(32) NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    db_type_code VARCHAR(50) NULL,
    os_type_code VARCHAR(50) NULL,
    awx_role VARCHAR(100) NULL,
    default_timeout_seconds INTEGER NOT NULL DEFAULT 5,
    enabled BOOLEAN NOT NULL DEFAULT true,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_collector_check_definition_target_scope
        CHECK (target_scope IN ('server', 'db_instance')),
    CONSTRAINT chk_collector_check_definition_task_type
        CHECK (task_type IN ('PORT_CHECK', 'DB_PORT_DISCOVERY', 'OS_DISCOVERY', 'DB_SQL_COLLECT'))
);

CREATE TABLE IF NOT EXISTS dbops.collector_run_item (
    id BIGSERIAL PRIMARY KEY,
    collector_run_id BIGINT NOT NULL REFERENCES dbops.collector_run(id) ON DELETE CASCADE,
    run_id VARCHAR(64) NOT NULL,
    item_key VARCHAR(255) NOT NULL,
    check_code VARCHAR(100) NOT NULL,
    target_scope VARCHAR(32) NOT NULL,
    server_id BIGINT NULL REFERENCES dbops.server(id),
    db_instance_id BIGINT NULL REFERENCES dbops.db_instance(id),
    target_host VARCHAR(255) NOT NULL,
    target_port INTEGER NOT NULL,
    protocol VARCHAR(20) NOT NULL DEFAULT 'tcp',
    timeout_seconds INTEGER NOT NULL DEFAULT 5,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    result_status VARCHAR(32) NULL,
    result_message TEXT NULL,
    raw_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_collector_run_item_key UNIQUE (collector_run_id, item_key),
    CONSTRAINT chk_collector_run_item_target_scope
        CHECK (target_scope IN ('server', 'db_instance')),
    CONSTRAINT chk_collector_run_item_status
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped', 'timeout')),
    CONSTRAINT chk_collector_run_item_result_status
        CHECK (result_status IS NULL OR result_status IN ('verified', 'missing', 'drifted', 'collected', 'failed')),
    CONSTRAINT chk_collector_run_item_target_port
        CHECK (target_port BETWEEN 1 AND 65535)
);

CREATE INDEX IF NOT EXISTS idx_collector_run_item_run
    ON dbops.collector_run_item(collector_run_id);

CREATE INDEX IF NOT EXISTS idx_collector_run_item_scope_instance
    ON dbops.collector_run_item(db_instance_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_item_scope_server
    ON dbops.collector_run_item(server_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_item_status
    ON dbops.collector_run_item(status);

CREATE TABLE IF NOT EXISTS dbops.asset_endpoint (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(32) NOT NULL,
    entity_id BIGINT NOT NULL,
    endpoint_type VARCHAR(32) NOT NULL DEFAULT 'port',
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    protocol VARCHAR(20) NOT NULL DEFAULT 'tcp',
    source VARCHAR(32) NOT NULL DEFAULT 'cmdb',
    expected BOOLEAN NOT NULL DEFAULT true,
    status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    last_seen_at TIMESTAMP NULL,
    last_verify_at TIMESTAMP NULL,
    last_run_id VARCHAR(64) NULL,
    last_message TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_asset_endpoint_identity UNIQUE (entity_type, entity_id, endpoint_type, host, port, source),
    CONSTRAINT chk_asset_endpoint_entity_type CHECK (entity_type IN ('server', 'db_instance')),
    CONSTRAINT chk_asset_endpoint_protocol CHECK (protocol IN ('tcp', 'udp')),
    CONSTRAINT chk_asset_endpoint_source CHECK (source IN ('cmdb', 'discovered', 'manual')),
    CONSTRAINT chk_asset_endpoint_status CHECK (status IN ('unknown', 'online', 'offline', 'drifted')),
    CONSTRAINT chk_asset_endpoint_port CHECK (port BETWEEN 1 AND 65535)
);

CREATE INDEX IF NOT EXISTS idx_asset_endpoint_entity_time
    ON dbops.asset_endpoint(entity_type, entity_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_asset_endpoint_status
    ON dbops.asset_endpoint(status);

CREATE TABLE IF NOT EXISTS dbops.asset_change_proposal (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(32) NOT NULL,
    entity_id BIGINT NOT NULL,
    change_type VARCHAR(64) NOT NULL,
    old_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_run_id VARCHAR(64) NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    requested_by VARCHAR(100) NULL,
    approved_by VARCHAR(100) NULL,
    approved_at TIMESTAMP NULL,
    applied_at TIMESTAMP NULL,
    rejected_reason TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_asset_change_proposal_entity_type CHECK (entity_type IN ('server', 'db_instance')),
    CONSTRAINT chk_asset_change_proposal_status CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'canceled'))
);

ALTER TABLE IF EXISTS dbops.collector_run_result
    ADD COLUMN IF NOT EXISTS item_key VARCHAR(255) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS check_code VARCHAR(100) NOT NULL DEFAULT 'PORT_REACHABILITY',
    ADD COLUMN IF NOT EXISTS target_scope VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    ADD COLUMN IF NOT EXISTS server_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS collector_run_item_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS result_message TEXT NULL,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT now();

ALTER TABLE IF EXISTS dbops.collector_run_result
    ALTER COLUMN db_instance_id DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_collector_run_result_item'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result
            ADD CONSTRAINT fk_collector_run_result_item
            FOREIGN KEY (collector_run_item_id) REFERENCES dbops.collector_run_item(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_collector_run_result_run_check'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result DROP CONSTRAINT uq_collector_run_result_run_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_collector_run_result_item'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result
            ADD CONSTRAINT uq_collector_run_result_item UNIQUE (collector_run_id, item_key);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_collector_run_result_item_id'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result
            ADD CONSTRAINT uq_collector_run_result_item_id UNIQUE (collector_run_item_id);
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_collector_run_result_status'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result DROP CONSTRAINT chk_collector_run_result_status;
    END IF;

    ALTER TABLE dbops.collector_run_result
        ADD CONSTRAINT chk_collector_run_result_status
        CHECK (status IN ('verified', 'missing', 'drifted', 'collected', 'failed'));

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_collector_run_result_target_scope'
          AND conrelid = 'dbops.collector_run_result'::regclass
    ) THEN
        ALTER TABLE dbops.collector_run_result
            ADD CONSTRAINT chk_collector_run_result_target_scope
            CHECK (target_scope IN ('server', 'db_instance'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_collector_run_result_server_time
    ON dbops.collector_run_result(server_id, created_at DESC);

COMMIT;
