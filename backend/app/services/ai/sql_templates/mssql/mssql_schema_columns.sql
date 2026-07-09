-- ============================================================================
-- SQL Server Schema Metadata Collection（Phase 3.6B0 C16-F0）
-- ============================================================================
-- 用途: DB_SCHEMA_METADATA_COLLECTION check 三方言扩展（与 pg_schema_columns.sql
--       同结构 6 列；C16-F0 三方言合并首版）
-- 返回: 每个业务 schema.table.column 一行（6 列）
--       table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
-- 只读: 仅查询 sys.columns / sys.objects / sys.types / sys.schemas，不做任何 DDL/DML
-- 排除: 系统 schema（sys / INFORMATION_SCHEMA / guest）
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - AI_SCHEMA_RESULT_MAX_ROWS=20000（超限按 schema 分批）
--   - AI_SCHEMA_RESULT_MAX_BYTES=10485760 (10MB)
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--   - truncated=true → snapshot status=failed（plan §4.4 P1）
--
-- 范围: sys.objects.type IN ('U', 'V') — User Table + View（与 PG information_schema
--       包含 table + view 对齐；PG 不区分常规表与视图）
--
-- 命名约定:
--   - table_schema / table_name / column_name  → 大小写保留（SQL Server 默认）
--   - data_type → sys.types.name（系统类型如 varchar / int / datetime）
--   - is_nullable → 'YES' / 'NO'（sys.columns.is_nullable 是 0/1，需转换）
--   - ordinal_position → column_id（数字）
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4B（C16-F0）
-- ============================================================================

-- NOTE: CAST(… AS VARCHAR(256)) is intentional — avoids ODBC Driver 18
-- "HY000 Unicode conversion failed (22) (SQLGetData)" when reading
-- sysname (nvarchar(128)) columns from sys.columns / sys.objects / sys.types.
-- The cast forces SQL Server to return 8-bit VARCHAR which pyodbc reads
-- without triggering driver-level Unicode conversion.
SELECT
    CAST(SCHEMA_NAME(o.schema_id) AS VARCHAR(256))              AS table_schema,
    CAST(o.name AS VARCHAR(256))                                AS table_name,
    CAST(c.name AS VARCHAR(256))                                AS column_name,
    CAST(ty.name AS VARCHAR(256))                               AS data_type,
    CASE WHEN c.is_nullable = 1 THEN 'YES' ELSE 'NO' END       AS is_nullable,
    c.column_id                                                 AS ordinal_position
FROM sys.columns c
JOIN sys.objects o ON c.object_id = o.object_id
JOIN sys.types ty ON c.user_type_id = ty.user_type_id
WHERE o.type IN ('U', 'V')  -- U = User Table, V = View
  AND SCHEMA_NAME(o.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')
ORDER BY table_schema, table_name, ordinal_position