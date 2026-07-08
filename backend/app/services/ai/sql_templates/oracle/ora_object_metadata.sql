-- ============================================================================
-- Oracle Object Metadata Collection（Phase 3.6B0 C16-F0）
-- ============================================================================
-- 用途: DB_OBJECT_METADATA check 三方言扩展（与 pg_object_metadata.sql 同结构
--       5 列 5 段 UNION ALL；C16-F0 三方言合并首版）
-- 返回: 每个业务对象一行（5 列）
--       object_type, schema_name, object_name, ddl_text, comment
-- 5 段 UNION ALL: table / view / index / function / constraint
-- 只读: 仅查询 ALL_TAB_COLUMNS / ALL_VIEWS / ALL_INDEXES / ALL_IND_COLUMNS /
--       ALL_PROCEDURES / ALL_CONSTRAINTS，不做任何 DDL/DML
-- 排除: 系统 schema（同 ora_schema_columns.sql 系统 schema 黑名单）
--
-- DDL 重建策略:
--   - table:   从 ALL_TAB_COLUMNS 用 LISTAGG 拼装 CREATE TABLE
--   - view:    从 ALL_VIEWS.TEXT 取视图文本（CLOB；DDL 长度 > 4000 时截断，
--              但 PG 模板同样 1MB 截断由 callback 兜底）
--   - index:   从 ALL_INDEXES + ALL_IND_COLUMNS 用 LISTAGG 拼装 CREATE INDEX
--   - function:从 ALL_PROCEDURES + ALL_ARGUMENTS 取签名（不取 body，body 可能很大）
--   - constraint: 从 ALL_CONSTRAINTS 取约束类型 + 名称；CHECK 约束取 SEARCH_CONDITION
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - DDL 文本 1MB 截断（callback service 兜底）
--   - AI_OBJECT_METADATA_TTL_HOURS=24
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4B（C16-F0）
-- ============================================================================

-- 1. table DDL (reconstructed from ALL_TAB_COLUMNS via LISTAGG)
SELECT
    'table'                                                   AS object_type,
    tc.owner                                                  AS schema_name,
    tc.table_name                                             AS object_name,
    'CREATE TABLE "' || tc.owner || '"."' || tc.table_name || '" (' ||
    RTRIM(
        XMLAGG(
            XMLELEMENT(
                e,
                '"' || tc.column_name || '" ' || tc.data_type ||
                CASE
                    WHEN tc.data_precision IS NOT NULL
                         AND tc.data_type IN ('NUMBER', 'DECIMAL', 'FLOAT')
                    THEN '(' || tc.data_precision ||
                         CASE WHEN tc.data_scale > 0 THEN ',' || tc.data_scale ELSE '' END || ')'
                    WHEN tc.char_length > 0
                         AND tc.data_type IN ('VARCHAR2', 'NVARCHAR2', 'CHAR', 'NCHAR', 'RAW')
                    THEN '(' || tc.char_length || ')'
                    ELSE ''
                END ||
                CASE WHEN tc.nullable = 'N' THEN ' NOT NULL' ELSE '' END
            ).EXTRACT('//text()'),
            ','
        ).GETSTRINGVAL(),
        ','
    ) ||
    ');'                                                      AS ddl_text,
    (SELECT c.comments
       FROM all_tab_comments c
      WHERE c.owner = tc.owner
        AND c.table_name = tc.table_name
        AND c.column_name IS NULL)                            AS comment
FROM all_tab_columns tc
WHERE tc.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND tc.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND tc.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'
GROUP BY tc.owner, tc.table_name

UNION ALL

-- 2. view DDL (from ALL_VIEWS.TEXT — view source text)
SELECT
    'view'                                                    AS object_type,
    v.owner                                                   AS schema_name,
    v.view_name                                               AS object_name,
    'CREATE OR REPLACE VIEW "' || v.owner || '"."' || v.view_name ||
    '" AS ' || v.text                                         AS ddl_text,
    v.text_length                                             AS comment
FROM all_views v
WHERE v.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND v.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND v.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'

UNION ALL

-- 3. materialized view DDL (basic reconstruction)
SELECT
    'materialized_view'                                       AS object_type,
    mv.owner                                                  AS schema_name,
    mv.mview_name                                             AS object_name,
    'CREATE MATERIALIZED VIEW "' || mv.owner || '"."' ||
    mv.mview_name || '" BUILD IMMEDIATE REFRESH ' ||
    mv.refresh_mode || ' AS ' || mv.query                    AS ddl_text,
    mv.comments                                               AS comment
FROM all_mviews mv
WHERE mv.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND mv.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND mv.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'

UNION ALL

-- 4. index DDL (reconstructed from ALL_INDEXES + ALL_IND_COLUMNS)
SELECT
    'index'                                                   AS object_type,
    i.index_owner                                             AS schema_name,
    i.index_name                                              AS object_name,
    'CREATE ' || CASE WHEN i.uniqueness = 'UNIQUE' THEN 'UNIQUE ' ELSE '' END ||
    'INDEX "' || i.index_owner || '"."' || i.index_name ||
    '" ON "' || i.table_owner || '"."' || i.table_name ||
    '" (' ||
    RTRIM(
        XMLAGG(
            XMLELEMENT(e, '"' || ic.column_name || '"' ||
                       CASE WHEN ic.descend = 'DESC' THEN ' DESC' ELSE '' END
            ).EXTRACT('//text()'),
            ','
        ).GETSTRINGVAL() WITHIN GROUP (ORDER BY ic.column_position),
        ','
    ) ||
    ')'                                                       AS ddl_text,
    ''                                                        AS comment
FROM all_indexes i
JOIN all_ind_columns ic
    ON ic.index_owner = i.owner
   AND ic.index_name = i.index_name
WHERE i.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND i.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND i.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'
GROUP BY i.index_owner, i.index_name, i.uniqueness,
         i.table_owner, i.table_name

UNION ALL

-- 5. function/procedure signature (exclude body — too large; signature is sufficient for Dify)
SELECT
    CASE p.object_type
         WHEN 'PROCEDURE' THEN 'procedure'
         ELSE 'function'
    END                                                       AS object_type,
    p.owner                                                   AS schema_name,
    p.object_name                                             AS object_name,
    'CREATE OR REPLACE ' || p.object_type || ' "' || p.owner || '"."' ||
    p.object_name || '" (' ||
    COALESCE(
        (SELECT LISTAGG(arg_name || ' ' || data_type, ', ')
                WITHIN GROUP (ORDER BY position)
           FROM all_arguments a
          WHERE a.object_id = p.object_id
            AND a.argument_level = 0
            AND a.data_type IS NOT NULL),
        ''
    ) ||
    ') ' ||
    CASE WHEN p.object_type = 'FUNCTION' THEN 'RETURN ' || p.return_type ELSE '' END
                                                              AS ddl_text,
    ''                                                        AS comment
FROM all_procedures p
WHERE p.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND p.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND p.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'
  AND p.object_type IN ('FUNCTION', 'PROCEDURE')

UNION ALL

-- 6. constraint (PK / UK / FK / CHECK — contype: P/R/U/C, ref Oracle standard)
SELECT
    CASE c.constraint_type
         WHEN 'P' THEN 'primary_key'
         WHEN 'U' THEN 'unique_constraint'
         WHEN 'R' THEN 'foreign_key'
         WHEN 'C' THEN 'check_constraint'
    END                                                       AS object_type,
    c.owner                                                   AS schema_name,
    c.constraint_name                                         AS object_name,
    'ALTER TABLE "' || c.owner || '"."' || c.table_name ||
    '" ADD CONSTRAINT "' || c.constraint_name || '" ' ||
    CASE c.constraint_type
         WHEN 'P' THEN 'PRIMARY KEY'
         WHEN 'U' THEN 'UNIQUE'
         WHEN 'R' THEN 'FOREIGN KEY'
         WHEN 'C' THEN 'CHECK (' || c.search_condition || ')'
    END                                                       AS ddl_text,
    ''                                                        AS comment
FROM all_constraints c
WHERE c.owner NOT IN (
        'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'OLAPSYS',
        'ORDSYS', 'WMSYS', 'LBACSYS', 'DVSYS', 'DVF',
        'GSMADMIN_INTERNAL', 'OWBSYS', 'OGG',
        'SI_INFORMTN_SCHEMA', 'DBSNMP', 'SYSAUX', 'TSMSYS'
    )
  AND c.owner NOT LIKE 'APEX\_%' ESCAPE '\'
  AND c.owner NOT LIKE 'FLOWS\_%' ESCAPE '\'
  AND c.constraint_type IN ('P', 'U', 'R', 'C')
  AND c.generated = 'USER NAME'  -- 排除系统生成的约束（如 NOT NULL 隐式约束）

ORDER BY object_type, schema_name, object_name