-- =============================================================================
-- Phase 3.5: backup_status_snapshot + v_backup_status_latest
-- =============================================================================
-- 备份状态采集（DB_READONLY_SQL_EXEC / business_domain=backup_status）的落库表。
-- 不与 inspection_result 耦合 — 后续"备份中心"功能与"巡检中心"解耦。
--
-- 执行环境: 测试库 dbops (10.134.185.85:5432)
-- 配套回滚: rollback_phase3_5_backup_status.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS dbops.backup_status_snapshot (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NULL REFERENCES dbops.backup_policy(id),
    collector_run_id BIGINT NULL,
    collector_run_item_id BIGINT NULL,
    backup_type VARCHAR(50) NULL,
    source_type VARCHAR(50) NOT NULL DEFAULT 'db_sql',
    last_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    last_success_at TIMESTAMP NULL,
    last_failure_at TIMESTAMP NULL,
    recovery_point_at TIMESTAMP NULL,
    age_minutes INTEGER NULL,
    duration_seconds INTEGER NULL,
    backup_size_mb NUMERIC(18,2) NULL,
    message TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    collected_at TIMESTAMP NOT NULL DEFAULT now(),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_backup_status_last_status CHECK (
        last_status IN ('success','failed','warning','unknown')
    ),
    CONSTRAINT chk_backup_status_source_type CHECK (
        source_type IN ('db_sql','agent','manual','external')
    )
);

CREATE INDEX IF NOT EXISTS idx_backup_status_snapshot_instance_collected
    ON dbops.backup_status_snapshot (instance_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_backup_status_snapshot_last_status
    ON dbops.backup_status_snapshot (last_status);
CREATE INDEX IF NOT EXISTS idx_backup_status_snapshot_policy
    ON dbops.backup_status_snapshot (policy_id);

-- DISTINCT ON view: latest snapshot per (instance_id, backup_type)
CREATE OR REPLACE VIEW dbops.v_backup_status_latest AS
SELECT DISTINCT ON (instance_id, COALESCE(backup_type, ''))
    id,
    instance_id,
    policy_id,
    collector_run_id,
    collector_run_item_id,
    backup_type,
    source_type,
    last_status,
    last_success_at,
    last_failure_at,
    recovery_point_at,
    age_minutes,
    duration_seconds,
    backup_size_mb,
    message,
    evidence,
    collected_at,
    created_at
FROM dbops.backup_status_snapshot
ORDER BY instance_id, COALESCE(backup_type, ''), collected_at DESC;
