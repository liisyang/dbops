-- =============================================================================
-- Phase 3.5 rollback: drop backup_status_snapshot + v_backup_status_latest
-- =============================================================================
-- 配套回滚脚本: 配合 dbops_phase3_5_backup_status.sql 使用

DROP VIEW IF EXISTS dbops.v_backup_status_latest;
DROP TABLE IF EXISTS dbops.backup_status_snapshot;
