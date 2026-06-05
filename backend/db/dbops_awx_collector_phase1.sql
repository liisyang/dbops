BEGIN;

SET search_path TO dbops, public;

ALTER TABLE dbops.db_instance
    ADD COLUMN IF NOT EXISTS trust_status VARCHAR(32) NOT NULL DEFAULT 'unverified',
    ADD COLUMN IF NOT EXISTS reachability_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS last_verify_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS verify_message TEXT NULL,
    ADD COLUMN IF NOT EXISTS last_verify_run_id VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS last_awx_job_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS verify_detail JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_db_instance_trust_status'
          AND conrelid = 'dbops.db_instance'::regclass
    ) THEN
        ALTER TABLE dbops.db_instance
            ADD CONSTRAINT chk_db_instance_trust_status
                CHECK (trust_status IN ('unverified', 'verified', 'missing', 'drifted'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_db_instance_reachability_status'
          AND conrelid = 'dbops.db_instance'::regclass
    ) THEN
        ALTER TABLE dbops.db_instance
            ADD CONSTRAINT chk_db_instance_reachability_status
                CHECK (reachability_status IN ('unknown', 'online', 'offline'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS dbops.collector_run (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    db_instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id),
    job_type VARCHAR(64) NOT NULL DEFAULT 'ASSET_VERIFY_PORT',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    awx_job_id BIGINT NULL,
    awx_job_url TEXT NULL,
    awx_job_template_id BIGINT NULL,
    awx_job_template_name VARCHAR(200) NULL,
    target_host VARCHAR(255) NOT NULL,
    target_port INTEGER NOT NULL,
    callback_url TEXT NULL,
    requested_by VARCHAR(100) NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    extra_vars JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_collector_run_status
        CHECK (status IN ('pending', 'launched', 'success', 'failed', 'callback_failed')),
    CONSTRAINT chk_collector_run_target_port
        CHECK (target_port BETWEEN 1 AND 65535)
);

CREATE TABLE IF NOT EXISTS dbops.collector_run_result (
    id BIGSERIAL PRIMARY KEY,
    collector_run_id BIGINT NOT NULL REFERENCES dbops.collector_run(id) ON DELETE CASCADE,
    run_id VARCHAR(64) NOT NULL,
    db_instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id),
    check_type VARCHAR(64) NOT NULL DEFAULT 'PORT_REACHABILITY',
    status VARCHAR(32) NOT NULL,
    port_reachable BOOLEAN NULL,
    target_host VARCHAR(255) NOT NULL,
    target_port INTEGER NOT NULL,
    error_message TEXT NULL,
    awx_job_id BIGINT NULL,
    checked_by VARCHAR(50) NULL,
    checked_at TIMESTAMP NULL,
    raw_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_collector_run_result_run_check UNIQUE (run_id, check_type),
    CONSTRAINT chk_collector_run_result_status
        CHECK (status IN ('verified', 'missing', 'drifted')),
    CONSTRAINT chk_collector_run_result_target_port
        CHECK (target_port BETWEEN 1 AND 65535)
);

CREATE INDEX IF NOT EXISTS idx_db_instance_trust_status
    ON dbops.db_instance(trust_status);

CREATE INDEX IF NOT EXISTS idx_db_instance_reachability_status
    ON dbops.db_instance(reachability_status);

CREATE INDEX IF NOT EXISTS idx_db_instance_last_verify_at
    ON dbops.db_instance(last_verify_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_instance_time
    ON dbops.collector_run(db_instance_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_awx_job
    ON dbops.collector_run(awx_job_id);

CREATE INDEX IF NOT EXISTS idx_collector_run_status
    ON dbops.collector_run(status);

CREATE INDEX IF NOT EXISTS idx_collector_run_result_instance_time
    ON dbops.collector_run_result(db_instance_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.triggers
        WHERE trigger_schema = 'dbops'
          AND trigger_name = 'trg_collector_run_updated_at'
    ) THEN
        CREATE TRIGGER trg_collector_run_updated_at
            BEFORE UPDATE ON dbops.collector_run
            FOR EACH ROW
            EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

COMMIT;
