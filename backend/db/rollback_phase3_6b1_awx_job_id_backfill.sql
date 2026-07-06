-- ============================================================================
-- DBOPS Phase 3.6B1 C16-F1 rollback — 移除 ai_sql_audit.awx_job_id
-- ============================================================================

BEGIN;

DROP INDEX IF EXISTS dbops.idx_ai_sql_audit_awx_job_id;

ALTER TABLE dbops.ai_sql_audit
    DROP COLUMN IF EXISTS awx_job_id;

COMMIT;

-- 验证
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'dbops'
  AND table_name = 'ai_sql_audit'
  AND column_name = 'awx_job_id';