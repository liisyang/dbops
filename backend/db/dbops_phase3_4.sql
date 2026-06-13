-- ============================================================================
-- DBOPS Phase 3.4: 基础巡检中心（可重复执行）
-- ============================================================================

-- ============================================================================
-- 1) inspection_schedule（新增）
-- ============================================================================
CREATE TABLE IF NOT EXISTS dbops.inspection_schedule (
    id BIGSERIAL PRIMARY KEY,
    schedule_code VARCHAR(100) NOT NULL,
    schedule_name VARCHAR(200) NOT NULL,
    cron_expr VARCHAR(100) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Shanghai',
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    next_run_at TIMESTAMP,
    last_run_at TIMESTAMP,
    last_task_id BIGINT,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_inspection_schedule_code'
          AND conrelid = 'dbops.inspection_schedule'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_schedule
        ADD CONSTRAINT uq_inspection_schedule_code UNIQUE (schedule_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_inspection_schedule_enabled
    ON dbops.inspection_schedule(is_enabled);
CREATE INDEX IF NOT EXISTS idx_inspection_schedule_next_run
    ON dbops.inspection_schedule(next_run_at DESC);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'dbops'
          AND table_name = 'inspection_schedule'
          AND column_name = 'updated_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_inspection_schedule_updated_at'
    ) THEN
        CREATE TRIGGER trg_inspection_schedule_updated_at
        BEFORE UPDATE ON dbops.inspection_schedule
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 2) inspection_item（扩展）
-- ============================================================================
ALTER TABLE dbops.inspection_item
    ADD COLUMN IF NOT EXISTS check_code VARCHAR(100),
    ADD COLUMN IF NOT EXISTS target_scope VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'warning',
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS rule_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();

UPDATE dbops.inspection_item
SET check_code = coalesce(item_code, 'UNKNOWN')
WHERE check_code IS NULL OR trim(check_code) = '';

ALTER TABLE dbops.inspection_item
    ALTER COLUMN check_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_item_target_scope'
          AND conrelid = 'dbops.inspection_item'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_item
        ADD CONSTRAINT chk_inspection_item_target_scope
        CHECK (target_scope IN ('server', 'db_instance'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_item_severity'
          AND conrelid = 'dbops.inspection_item'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_item
        ADD CONSTRAINT chk_inspection_item_severity
        CHECK (severity IN ('info', 'warning', 'critical'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_inspection_item_enabled
    ON dbops.inspection_item(enabled);
CREATE INDEX IF NOT EXISTS idx_inspection_item_check_code
    ON dbops.inspection_item(check_code);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'dbops'
          AND table_name = 'inspection_item'
          AND column_name = 'updated_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_inspection_item_updated_at'
    ) THEN
        CREATE TRIGGER trg_inspection_item_updated_at
        BEFORE UPDATE ON dbops.inspection_item
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 3) inspection_task（扩展）
-- ============================================================================
ALTER TABLE dbops.inspection_task
    ADD COLUMN IF NOT EXISTS schedule_id BIGINT,
    ADD COLUMN IF NOT EXISTS batch_run_id BIGINT,
    ADD COLUMN IF NOT EXISTS run_type VARCHAR(50) NOT NULL DEFAULT 'inspection',
    ADD COLUMN IF NOT EXISTS target_scope VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS check_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS item_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(100),
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_task_schedule'
    ) THEN
        ALTER TABLE dbops.inspection_task
        ADD CONSTRAINT fk_inspection_task_schedule
        FOREIGN KEY (schedule_id) REFERENCES dbops.inspection_schedule(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_task_batch_run'
    ) THEN
        ALTER TABLE dbops.inspection_task
        ADD CONSTRAINT fk_inspection_task_batch_run
        FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_task_target_scope'
          AND conrelid = 'dbops.inspection_task'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_task
        ADD CONSTRAINT chk_inspection_task_target_scope
        CHECK (target_scope IN ('server', 'db_instance'));
    END IF;
END $$;

-- Phase 3.4 adds 'partial_success' to the status enum.
-- The pre-existing constraint has a stricter definition without partial_success;
-- we must DROP and recreate to apply the new value set.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_task_status'
          AND conrelid = 'dbops.inspection_task'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_task DROP CONSTRAINT chk_inspection_task_status;
    END IF;
END $$;

ALTER TABLE dbops.inspection_task
    ADD CONSTRAINT chk_inspection_task_status
    CHECK (status IN ('pending', 'running', 'success', 'partial_success', 'failed', 'cancelled'));

CREATE INDEX IF NOT EXISTS idx_inspection_task_status
    ON dbops.inspection_task(status);
CREATE INDEX IF NOT EXISTS idx_inspection_task_batch_run
    ON dbops.inspection_task(batch_run_id);
CREATE INDEX IF NOT EXISTS idx_inspection_task_created_at
    ON dbops.inspection_task(created_at DESC);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'dbops'
          AND table_name = 'inspection_task'
          AND column_name = 'updated_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_inspection_task_updated_at'
    ) THEN
        CREATE TRIGGER trg_inspection_task_updated_at
        BEFORE UPDATE ON dbops.inspection_task
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 4) inspection_result（扩展）
-- ============================================================================
ALTER TABLE dbops.inspection_result
    ALTER COLUMN item_id DROP NOT NULL;

ALTER TABLE dbops.inspection_result
    ADD COLUMN IF NOT EXISTS batch_run_id BIGINT,
    ADD COLUMN IF NOT EXISTS collector_run_id BIGINT,
    ADD COLUMN IF NOT EXISTS collector_run_item_id BIGINT,
    ADD COLUMN IF NOT EXISTS target_type VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    ADD COLUMN IF NOT EXISTS target_id BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS result_code VARCHAR(100),
    ADD COLUMN IF NOT EXISTS result_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'warning',
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMP NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();

-- Make legacy status column nullable (superseded by result_status)
ALTER TABLE dbops.inspection_result ALTER COLUMN status DROP NOT NULL;

UPDATE dbops.inspection_result
SET result_code = coalesce(result_code, 'UNKNOWN')
WHERE result_code IS NULL OR trim(result_code) = '';

ALTER TABLE dbops.inspection_result
    ALTER COLUMN result_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_result_batch_run'
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT fk_inspection_result_batch_run
        FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_result_collector_run'
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT fk_inspection_result_collector_run
        FOREIGN KEY (collector_run_id) REFERENCES dbops.collector_run(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_result_collector_run_item'
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT fk_inspection_result_collector_run_item
        FOREIGN KEY (collector_run_item_id) REFERENCES dbops.collector_run_item(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Phase 3.4 narrows target_type to ('server', 'db_instance').
-- The pre-3.4 constraint (chk_inspection_result_target) allows a wider
-- value set including legacy 'business_system' / 'cluster'. Drop it so the
-- narrower Phase 3.4 constraint is the only one in effect.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_result_target'
          AND conrelid = 'dbops.inspection_result'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_result DROP CONSTRAINT chk_inspection_result_target;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_result_target_type'
          AND conrelid = 'dbops.inspection_result'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT chk_inspection_result_target_type
        CHECK (target_type IN ('server', 'db_instance'));
    END IF;
END $$;

-- Drop old constraint if it exists with outdated values (ok/warning/failed/unknown)
-- and recreate with Phase 3.4 values (normal/abnormal/warning/unknown)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_result_status'
          AND conrelid = 'dbops.inspection_result'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_result DROP CONSTRAINT chk_inspection_result_status;
    END IF;
END $$;

-- Guard the ADD so a re-run of this migration doesn't fail with
-- "constraint already exists" (the DROP above is idempotent).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_result_status'
          AND conrelid = 'dbops.inspection_result'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT chk_inspection_result_status
        CHECK (result_status IN ('normal', 'abnormal', 'warning', 'unknown'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_inspection_result_severity'
          AND conrelid = 'dbops.inspection_result'::regclass
    ) THEN
        ALTER TABLE dbops.inspection_result
        ADD CONSTRAINT chk_inspection_result_severity
        CHECK (severity IN ('info', 'warning', 'critical'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_inspection_result_task
    ON dbops.inspection_result(task_id);
CREATE INDEX IF NOT EXISTS idx_inspection_result_item
    ON dbops.inspection_result(item_id);
CREATE INDEX IF NOT EXISTS idx_inspection_result_target
    ON dbops.inspection_result(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_inspection_result_status
    ON dbops.inspection_result(result_status);
CREATE INDEX IF NOT EXISTS idx_inspection_result_detected_at
    ON dbops.inspection_result(detected_at DESC);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'dbops'
          AND table_name = 'inspection_result'
          AND column_name = 'updated_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_inspection_result_updated_at'
    ) THEN
        CREATE TRIGGER trg_inspection_result_updated_at
        BEFORE UPDATE ON dbops.inspection_result
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

-- 补充 inspection_schedule.last_task_id 外键（依赖 inspection_task 存在）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_inspection_schedule_last_task'
    ) THEN
        ALTER TABLE dbops.inspection_schedule
        ADD CONSTRAINT fk_inspection_schedule_last_task
        FOREIGN KEY (last_task_id) REFERENCES dbops.inspection_task(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ============================================================================
-- 5) 巡检项种子（首批 8 项）
-- ============================================================================
INSERT INTO dbops.inspection_item (
    item_code, item_name, check_code, target_scope, severity, enabled, description, rule_config
)
VALUES
    ('CONNECTIVITY_PORT_REACHABLE', '端口连通性可达', 'DB_PORT_REACHABILITY', 'db_instance', 'critical', true, '数据库服务端口连通性检查', '{"status_ok":["verified"]}'::jsonb),
    ('DB_VERSION_COLLECTED', '数据库版本已采集', 'DB_VERSION_FACT_COLLECTION', 'db_instance', 'warning', true, '数据库版本事实采集结果', '{"status_ok":["collected","verified"]}'::jsonb),
    ('DB_ROLE_COLLECTED', '数据库角色已采集', 'DB_ROLE_FACT_COLLECTION', 'db_instance', 'warning', true, '数据库角色事实采集结果', '{"status_ok":["collected","verified"]}'::jsonb),
    ('DB_ROLE_CHANGED', '数据库角色发生变化', 'DB_ROLE_FACT_COLLECTION', 'db_instance', 'critical', true, '角色变化巡检项', '{"match":{"fact_key":"db_role_changed","truthy":true}}'::jsonb),
    ('INSTANCE_PORT_DRIFT', '实例端口漂移', 'PORT_CANDIDATE_REACHABILITY', 'db_instance', 'critical', true, '实例端口与基线不一致', '{"status_abnormal":["drifted"]}'::jsonb),
    ('FACT_COLLECTION_FAILED', '事实采集失败', 'DB_BASIC_FACT_COLLECTION', 'db_instance', 'critical', true, '事实采集失败告警', '{"status_abnormal":["failed","missing"]}'::jsonb),
    ('CREDENTIAL_AUTH_FAILED', '凭证认证失败', 'DB_BASIC_FACT_COLLECTION', 'db_instance', 'critical', true, '凭证认证失败告警', '{"match":{"error_code":"AUTHENTICATION_FAILED"}}'::jsonb),
    ('SERVER_OS_COLLECTED', '服务器OS事实已采集', 'OS_BASIC_FACT_COLLECTION', 'server', 'warning', true, '服务器OS事实采集结果', '{"status_ok":["collected","verified"]}'::jsonb)
ON CONFLICT (item_code) DO UPDATE SET
    item_name = EXCLUDED.item_name,
    check_code = EXCLUDED.check_code,
    target_scope = EXCLUDED.target_scope,
    severity = EXCLUDED.severity,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    rule_config = EXCLUDED.rule_config,
    updated_at = now();
