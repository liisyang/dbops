-- ============================================================================
-- PostgreSQL Schema Metadata Collection（Phase 3.6B0 C7）
-- ============================================================================
-- 用途: DB_SCHEMA_METADATA_COLLECTION check（C8 Builder + Role 引用）
-- 返回: 每个业务 schema.table.column 一行（6 列）
--       table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
-- 只读: 仅查询 information_schema，不做任何 DDL/DML
-- 排除: pg_catalog / information_schema（系统 schema）
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - AI_SCHEMA_RESULT_MAX_ROWS=20000（超限按 schema 分批）
--   - AI_SCHEMA_RESULT_MAX_BYTES=10485760 (10MB)
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--   - truncated=true → snapshot status=failed（plan §4.4 P1）
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4.4 line 436-441
-- ============================================================================

SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    ordinal_position
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
