-- ============================================================================
-- Oracle Schema Metadata Collection（Phase 3.6B0 C16-F0）
-- ============================================================================
-- 用途: DB_SCHEMA_METADATA_COLLECTION check 三方言扩展（与 pg_schema_columns.sql
--       同结构 6 列；C16-F0 三方言合并首版）
-- 返回: 每个业务 schema.table.column 一行（6 列）
--       table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
-- 只读: 仅查询 ALL_TAB_COLUMNS，不做任何 DDL/DML
-- 排除: 系统 schema（SYS / SYSTEM / XDB / CTXSYS / MDSYS / OLAPSYS / ORDSYS /
--       WMSYS / LBACSYS / DVSYS / GSMADMIN_INTERNAL / APEX_* / FLOWS_* / OWBSYS /
--       OGG / SI_INFORMTN_SCHEMA / DBSNMP / SYSAUX / TSMSYS）
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - AI_SCHEMA_RESULT_MAX_ROWS=20000（超限按 schema 分批）
--   - AI_SCHEMA_RESULT_MAX_BYTES=10485760 (10MB)
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--   - truncated=true → snapshot status=failed（plan §4.4 P1）
--
-- 命名约定:
--   - table_schema / table_name / column_name / data_type  → 大写（Oracle 默认）
--   - is_nullable → 'YES' / 'NO'（与 PG information_schema 一致；ALL_TAB_COLUMNS.nullable 是 'Y'/'N'，需转换）
--   - ordinal_position → column_id（数字）
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4B（C16-F0）
-- ============================================================================

SELECT
    owner                                                  AS table_schema,
    table_name,
    column_name,
    data_type,
    CASE nullable WHEN 'Y' THEN 'YES' ELSE 'NO' END        AS is_nullable,
    column_id                                              AS ordinal_position
FROM all_tab_columns
WHERE owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND owner NOT LIKE 'FLOWS\_%' ESCAPE '\'
ORDER BY table_schema, table_name, ordinal_position;