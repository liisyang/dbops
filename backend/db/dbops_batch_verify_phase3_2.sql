-- ============================================================================
-- DBOPS Phase 3.2: 批量资产校验中心 + 分网段 AWX 分发调度
-- DDL Migration（可重复执行）
-- ============================================================================

-- ============================================================================
-- 1. collector_batch_run — 批量任务主表
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.collector_batch_run (
    id BIGSERIAL PRIMARY KEY,
    batch_code VARCHAR(100) NOT NULL,
    run_type VARCHAR(50) NOT NULL,
    target_scope VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    total_asset_count INTEGER NOT NULL DEFAULT 0,
    total_item_count INTEGER NOT NULL DEFAULT 0,
    success_item_count INTEGER NOT NULL DEFAULT 0,
    failed_item_count INTEGER NOT NULL DEFAULT 0,
    pending_item_count INTEGER NOT NULL DEFAULT 0,
    running_item_count INTEGER NOT NULL DEFAULT 0,
    skipped_item_count INTEGER NOT NULL DEFAULT 0,
    dispatch_count INTEGER NOT NULL DEFAULT 0,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_by VARCHAR(100),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- UNIQUE constraint on batch_code (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_collector_batch_run_code'
          AND conrelid = 'dbops.collector_batch_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_batch_run
        ADD CONSTRAINT uq_collector_batch_run_code UNIQUE (batch_code);
    END IF;
END $$;

-- CHECK constraint: target_scope
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_batch_run_scope'
          AND conrelid = 'dbops.collector_batch_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_batch_run
        ADD CONSTRAINT chk_collector_batch_run_scope
        CHECK (target_scope IN ('server', 'db_instance'));
    END IF;
END $$;

-- CHECK constraint: status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_batch_run_status'
          AND conrelid = 'dbops.collector_batch_run'::regclass
    ) THEN
        ALTER TABLE dbops.collector_batch_run
        ADD CONSTRAINT chk_collector_batch_run_status
        CHECK (status IN ('pending','dispatching','running','success','partial_success','failed','cancelled'));
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_collector_batch_run_status
    ON dbops.collector_batch_run(status);

CREATE INDEX IF NOT EXISTS idx_collector_batch_run_type
    ON dbops.collector_batch_run(run_type);

CREATE INDEX IF NOT EXISTS idx_collector_batch_run_created_at
    ON dbops.collector_batch_run(created_at DESC);

-- ============================================================================
-- 2. collector_dispatch_run — AWX 分发表
-- ============================================================================

CREATE TABLE IF NOT EXISTS dbops.collector_dispatch_run (
    id BIGSERIAL PRIMARY KEY,
    dispatch_code VARCHAR(100),
    batch_run_id BIGINT NOT NULL,
    collector_run_id BIGINT,
    network_zone VARCHAR(100),
    awx_instance_group VARCHAR(100),
    awx_job_template VARCHAR(200) NOT NULL DEFAULT 'JT_DBOPS_COLLECTOR_GENERIC',
    awx_job_id BIGINT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    item_count INTEGER NOT NULL DEFAULT 0,
    success_item_count INTEGER NOT NULL DEFAULT 0,
    failed_item_count INTEGER NOT NULL DEFAULT 0,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    launched_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- FK to batch_run (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_collector_dispatch_run_batch_run'
    ) THEN
        ALTER TABLE dbops.collector_dispatch_run
        ADD CONSTRAINT fk_collector_dispatch_run_batch_run
        FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE CASCADE;
    END IF;
END $$;

-- CHECK constraint: status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_collector_dispatch_run_status'
    ) THEN
        ALTER TABLE dbops.collector_dispatch_run
        ADD CONSTRAINT chk_collector_dispatch_run_status
        CHECK (status IN ('pending','launching','launched','running','success','partial_success','failed','cancelled'));
    END IF;
END $$;

-- dispatch_code unique index (partial — only when dispatch_code is not null)
CREATE UNIQUE INDEX IF NOT EXISTS uq_collector_dispatch_run_code
    ON dbops.collector_dispatch_run(dispatch_code)
    WHERE dispatch_code IS NOT NULL;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_collector_dispatch_batch
    ON dbops.collector_dispatch_run(batch_run_id);

CREATE INDEX IF NOT EXISTS idx_collector_dispatch_status
    ON dbops.collector_dispatch_run(status);

CREATE INDEX IF NOT EXISTS idx_collector_dispatch_awx_job
    ON dbops.collector_dispatch_run(awx_job_id);

CREATE INDEX IF NOT EXISTS idx_collector_dispatch_group
    ON dbops.collector_dispatch_run(network_zone, awx_instance_group);

-- ============================================================================
-- 3. ALTER collector_run — 新增批量调度字段 + FK
-- ============================================================================

ALTER TABLE dbops.collector_run
ADD COLUMN IF NOT EXISTS batch_run_id BIGINT,
ADD COLUMN IF NOT EXISTS dispatch_run_id BIGINT,
ADD COLUMN IF NOT EXISTS network_zone VARCHAR(100),
ADD COLUMN IF NOT EXISTS awx_instance_group VARCHAR(100);

-- FK: collector_run → collector_batch_run
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_collector_run_batch_run'
    ) THEN
        ALTER TABLE dbops.collector_run
        ADD CONSTRAINT fk_collector_run_batch_run
        FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: collector_run → collector_dispatch_run
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_collector_run_dispatch_run'
    ) THEN
        ALTER TABLE dbops.collector_run
        ADD CONSTRAINT fk_collector_run_dispatch_run
        FOREIGN KEY (dispatch_run_id) REFERENCES dbops.collector_dispatch_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- FK: collector_dispatch_run → collector_run (反向)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_collector_dispatch_run_collector_run'
    ) THEN
        ALTER TABLE dbops.collector_dispatch_run
        ADD CONSTRAINT fk_collector_dispatch_run_collector_run
        FOREIGN KEY (collector_run_id) REFERENCES dbops.collector_run(id) ON DELETE SET NULL;
    END IF;
END $$;

-- CollectorRun indexes
CREATE INDEX IF NOT EXISTS idx_collector_run_batch
    ON dbops.collector_run(batch_run_id);

CREATE INDEX IF NOT EXISTS idx_collector_run_dispatch
    ON dbops.collector_run(dispatch_run_id);

CREATE INDEX IF NOT EXISTS idx_collector_run_awx_group
    ON dbops.collector_run(network_zone, awx_instance_group);

-- ============================================================================
-- 4. Triggers (set_updated_at)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_collector_batch_run_updated_at'
    ) THEN
        CREATE TRIGGER trg_collector_batch_run_updated_at
        BEFORE UPDATE ON dbops.collector_batch_run
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_collector_dispatch_run_updated_at'
    ) THEN
        CREATE TRIGGER trg_collector_dispatch_run_updated_at
        BEFORE UPDATE ON dbops.collector_dispatch_run
        FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();
    END IF;
END $$;
