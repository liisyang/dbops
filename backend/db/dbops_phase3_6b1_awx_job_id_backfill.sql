-- ============================================================================
-- DBOPS Phase 3.6B1: AI SQL Audit — awx_job_id 反向化（C16-F1）
-- DDL Migration（可重复执行；幂等）
--
-- 背景：
--   C14 提交（fb8addb）后，AiSqlExecuteService 在 AWX launch 成功后仅
--   写入了 collector_run.awx_job_id。前端 SqlPreview.vue audit 详情卡与
--   GET /ai/sql/audit/{id}/execution 响应（AiSqlExecutionStatusResponse）
--   都需要 ai_sql_audit.awx_job_id 才能渲染对应字段；当前 api/ai.py 用
--   `awx_job_id=None` 占位 + TODO 注释。
--
-- 变更点：
--   1. ai_sql_audit 新增 awx_job_id BIGINT NULL 列（Execute launch 后回填）
--   2. 同步加 idx_ai_sql_audit_awx_job_id 索引（便于按 awx_job_id 反查 audit）
--
-- 依赖（pre-existing）:
--   - dbops.ai_sql_audit — C12 已建
--   - dbops.collector_run.awx_job_id — Phase 1 已建
--
-- 不在 F1 范围（明确避免 scope creep）:
--   ❌ result_message_id 反向化（C16-F2）
--   ❌ callback 幂等增强（已由 AiSqlCallbackService 处理）
--   ❌ ai_chat_message 元数据扩展
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. ai_sql_audit.awx_job_id 列（C16-F1）
-- ============================================================================
ALTER TABLE dbops.ai_sql_audit
    ADD COLUMN IF NOT EXISTS awx_job_id BIGINT NULL;

COMMENT ON COLUMN dbops.ai_sql_audit.awx_job_id IS
    'AWX Job ID（Execute launch 成功后回填；用于前端详情展示与 join 反查）。幂等：'
    'execute_service 在 UPDATE WHERE awx_job_id IS NULL 后写入；callback 写库后保留。';

-- ============================================================================
-- 2. 索引：idx_ai_sql_audit_awx_job_id（便于反查 + 调试）
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_ai_sql_audit_awx_job_id
    ON dbops.ai_sql_audit (awx_job_id)
    WHERE awx_job_id IS NOT NULL;

COMMIT;

-- 验证
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'dbops'
  AND table_name = 'ai_sql_audit'
  AND column_name = 'awx_job_id';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'dbops'
  AND tablename = 'ai_sql_audit'
  AND indexname = 'idx_ai_sql_audit_awx_job_id';