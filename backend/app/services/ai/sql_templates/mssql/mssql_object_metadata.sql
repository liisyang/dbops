-- ============================================================================
-- SQL Server Object Metadata Collection（Phase 3.6B0 C16-F0）
-- ============================================================================
-- 用途: DB_OBJECT_METADATA check 三方言扩展（与 pg_object_metadata.sql 同结构
--       5 列 6 段 UNION ALL；C16-F0 三方言合并首版）
-- 返回: 每个业务对象一行（5 列）
--       object_type, schema_name, object_name, ddl_text, comment
-- 6 段 UNION ALL: table / view / index / function / procedure / constraint
-- 只读: 仅查询 sys.columns / sys.objects / sys.indexes / sys.index_columns /
--       sys.procedures / sys.check_constraints / sys.foreign_keys / sys.key_constraints
--       ，不做任何 DDL/DML
-- 排除: 系统 schema（同 mssql_schema_columns.sql 黑名单 sys/INFORMATION_SCHEMA/guest）
--
-- DDL 重建策略:
--   - table:   从 sys.columns + sys.types 用 STRING_AGG 拼装 CREATE TABLE
--              （OBJECT_DEFINITION 对普通 user table 返回 NULL，仅对 view/function/proc
--              有效，所以 table 必须重建）
--   - view:    用 OBJECT_DEFINITION(object_id)（返回完整 view 文本）
--   - index:   从 sys.indexes + sys.index_columns 用 STRING_AGG 拼装 CREATE INDEX
--   - function/procedure:用 OBJECT_DEFINITION(object_id)（完整 body）
--   - constraint: 4 子类（PK/UK/FK/CHECK）分别查 sys.key_constraints /
--              sys.foreign_keys / sys.check_constraints，用 sys.tables.name 拼装
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - DDL 文本 1MB 截断（callback service 兜底）
--   - AI_OBJECT_METADATA_TTL_HOURS=24
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4B（C16-F0）
-- ============================================================================

-- 1. table DDL (reconstructed from sys.columns + sys.types via STRING_AGG)
SELECT
    'table'                                                   AS object_type,
    SCHEMA_NAME(t.schema_id)                                  AS schema_name,
    t.name                                                    AS object_name,
    'CREATE TABLE [' + SCHEMA_NAME(t.schema_id) + '].[' +
    t.name + '] (' +
    STRING_AGG(
        '[' + c.name + '] ' +
        CASE
            WHEN ty.name IN ('varchar', 'nvarchar', 'char', 'nchar', 'binary', 'varbinary')
                 AND c.max_length >= 0
            THEN ty.name + '(' +
                 CASE WHEN c.max_length = -1 THEN 'MAX'
                      WHEN ty.name IN ('nvarchar', 'nchar') THEN CAST(c.max_length / 2 AS VARCHAR(10))
                      ELSE CAST(c.max_length AS VARCHAR(10))
                 END + ')'
            WHEN ty.name IN ('decimal', 'numeric')
            THEN ty.name + '(' + CAST(c.precision AS VARCHAR(10)) +
                 ', ' + CAST(c.scale AS VARCHAR(10)) + ')'
            ELSE ty.name
        END +
        CASE WHEN c.is_nullable = 0 THEN ' NOT NULL' ELSE '' END,
        ', '
    ) +
    ');'                                                      AS ddl_text,
    ISNULL(
        (SELECT CAST(value AS VARCHAR(4000))
           FROM sys.extended_properties
          WHERE major_id = t.object_id
            AND minor_id = 0
            AND class = 1),
        ''
    )                                                         AS comment
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON c.user_type_id = ty.user_type_id
WHERE SCHEMA_NAME(t.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')
GROUP BY t.object_id, t.schema_id, t.name

UNION ALL

-- 2. view DDL (use OBJECT_DEFINITION — returns full view source)
SELECT
    'view'                                                    AS object_type,
    SCHEMA_NAME(v.schema_id)                                  AS schema_name,
    v.name                                                    AS object_name,
    ISNULL(OBJECT_DEFINITION(v.object_id), '')                AS ddl_text,
    ISNULL(
        (SELECT CAST(value AS VARCHAR(4000))
           FROM sys.extended_properties
          WHERE major_id = v.object_id
            AND minor_id = 0
            AND class = 1),
        ''
    )                                                         AS comment
FROM sys.views v
WHERE SCHEMA_NAME(v.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- 3. index DDL (reconstructed from sys.indexes + sys.index_columns)
--    Note: sys.indexes has no schema_id column — join sys.objects to resolve schema
SELECT
    'index'                                                   AS object_type,
    SCHEMA_NAME(obj.schema_id)                                AS schema_name,
    i.name                                                    AS object_name,
    'CREATE ' +
    CASE WHEN i.is_unique = 1 THEN 'UNIQUE ' ELSE '' END +
    'INDEX [' + SCHEMA_NAME(obj.schema_id) + '].[' + i.name + '] ON [' +
    SCHEMA_NAME(obj.schema_id) + '].[' + OBJECT_NAME(i.object_id) + '] (' +
    STRING_AGG(
        '[' + c.name + ']' +
        CASE WHEN ic.is_descending_key = 1 THEN ' DESC' ELSE ' ASC' END,
        ', '
    ) +
    ')' +
    CASE WHEN i.has_filter = 1 THEN ' WHERE ' + i.filter_definition ELSE '' END
                                                              AS ddl_text,
    ''                                                        AS comment
FROM sys.indexes i
JOIN sys.objects obj ON obj.object_id = i.object_id
JOIN sys.index_columns ic
    ON ic.object_id = i.object_id
   AND ic.index_id = i.index_id
JOIN sys.columns c
    ON c.object_id = ic.object_id
   AND c.column_id = ic.column_id
WHERE SCHEMA_NAME(obj.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')
  AND i.is_hypothetical = 0
  AND i.type > 0  -- exclude heap (type=0)
GROUP BY i.object_id, obj.schema_id, i.name, i.is_unique, i.has_filter, i.filter_definition

UNION ALL

-- 4. function DDL (use OBJECT_DEFINITION)
SELECT
    'function'                                                AS object_type,
    SCHEMA_NAME(o.schema_id)                                  AS schema_name,
    o.name                                                    AS object_name,
    ISNULL(OBJECT_DEFINITION(o.object_id), '')                AS ddl_text,
    ''                                                        AS comment
FROM sys.objects o
WHERE o.type IN ('FN', 'IF', 'TF')  -- FN = SQL scalar fn, IF = inline TVF, TF = table-valued fn
  AND SCHEMA_NAME(o.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- 5. procedure DDL (use OBJECT_DEFINITION)
SELECT
    'procedure'                                               AS object_type,
    SCHEMA_NAME(o.schema_id)                                  AS schema_name,
    o.name                                                    AS object_name,
    ISNULL(OBJECT_DEFINITION(o.object_id), '')                AS ddl_text,
    ''                                                        AS comment
FROM sys.objects o
WHERE o.type = 'P'  -- P = SQL stored procedure
  AND SCHEMA_NAME(o.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- 6. constraint (4 子类 union: PK / UK / FK / CHECK)
-- PRIMARY KEY
SELECT
    'primary_key'                                             AS object_type,
    SCHEMA_NAME(kc.schema_id)                                 AS schema_name,
    kc.name                                                   AS object_name,
    'ALTER TABLE [' + SCHEMA_NAME(kc.schema_id) + '].[' +
    OBJECT_NAME(kc.parent_object_id) +
    '] ADD CONSTRAINT [' + kc.name + '] PRIMARY KEY (' +
    (SELECT STRING_AGG('[' + c.name + ']', ', ')
       FROM sys.index_columns ic
       JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
      WHERE ic.object_id = kc.parent_object_id
        AND ic.index_id = kc.unique_index_id) +
    ')'                                                       AS ddl_text,
    ''                                                        AS comment
FROM sys.key_constraints kc
WHERE kc.type = 'PK'
  AND SCHEMA_NAME(kc.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- UNIQUE constraint
SELECT
    'unique_constraint'                                       AS object_type,
    SCHEMA_NAME(kc.schema_id)                                 AS schema_name,
    kc.name                                                   AS object_name,
    'ALTER TABLE [' + SCHEMA_NAME(kc.schema_id) + '].[' +
    OBJECT_NAME(kc.parent_object_id) +
    '] ADD CONSTRAINT [' + kc.name + '] UNIQUE (' +
    (SELECT STRING_AGG('[' + c.name + ']', ', ')
       FROM sys.index_columns ic
       JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
      WHERE ic.object_id = kc.parent_object_id
        AND ic.index_id = kc.unique_index_id) +
    ')'                                                       AS ddl_text,
    ''                                                        AS comment
FROM sys.key_constraints kc
WHERE kc.type = 'UQ'
  AND SCHEMA_NAME(kc.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- FOREIGN KEY
SELECT
    'foreign_key'                                             AS object_type,
    SCHEMA_NAME(fk.schema_id)                                 AS schema_name,
    fk.name                                                   AS object_name,
    'ALTER TABLE [' + SCHEMA_NAME(fk.schema_id) + '].[' +
    OBJECT_NAME(fk.parent_object_id) +
    '] ADD CONSTRAINT [' + fk.name + '] FOREIGN KEY (' +
    (SELECT STRING_AGG('[' + COL_NAME(fkcols.parent_object_id, fkcols.parent_column_id) + ']', ', ')
       FROM sys.foreign_key_columns fkcols
      WHERE fkcols.constraint_object_id = fk.object_id) +
    ') REFERENCES [' + SCHEMA_NAME(fk.referenced_object_id) + '].[' +
    OBJECT_NAME(fk.referenced_object_id) + '] (' +
    (SELECT STRING_AGG('[' + COL_NAME(fkcols.referenced_object_id, fkcols.referenced_column_id) + ']', ', ')
       FROM sys.foreign_key_columns fkcols
      WHERE fkcols.constraint_object_id = fk.object_id) +
    ')'                                                       AS ddl_text,
    ''                                                        AS comment
FROM sys.foreign_keys fk
WHERE SCHEMA_NAME(fk.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

UNION ALL

-- CHECK constraint
SELECT
    'check_constraint'                                        AS object_type,
    SCHEMA_NAME(cc.schema_id)                                 AS schema_name,
    cc.name                                                   AS object_name,
    'ALTER TABLE [' + SCHEMA_NAME(cc.schema_id) + '].[' +
    OBJECT_NAME(cc.parent_object_id) +
    '] ADD CONSTRAINT [' + cc.name + '] CHECK (' +
    cc.definition + ')'                                       AS ddl_text,
    ''                                                        AS comment
FROM sys.check_constraints cc
WHERE SCHEMA_NAME(cc.schema_id) NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')

ORDER BY object_type, schema_name, object_name;