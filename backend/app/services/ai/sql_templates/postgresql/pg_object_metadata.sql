-- ============================================================================
-- PostgreSQL Object Metadata Collection（Phase 3.6B0 F3 / C16-F3）
-- ============================================================================
-- 用途: DB_OBJECT_METADATA check（Builder + Role 引用）
-- 返回: 每个业务对象一行（5 列）
--       object_type, schema_name, object_name, ddl_text, comment
-- 5 段 UNION ALL: table / view / index / function / constraint
-- 只读: 仅查询 pg_catalog / pg_class / pg_proc / pg_constraint，不做任何 DDL/DML
-- 排除: pg_catalog / information_schema / pg_toast（系统 schema）
--
-- 完整性约束（由 collector_client / callback 强制，本文件不控制）:
--   - DDL 文本 1MB 截断（callback service 兜底）
--   - AI_OBJECT_METADATA_TTL_HOURS=24
--   - callback 返回必须包含 total_rows / returned_rows / truncated
--
-- Plan 参考: .claude/plans/phase-3-6-ai-copilot-full-plan.md §4 + F3 段落
-- ============================================================================

-- 1. table DDL (relkind: r=ordinary, p=partitioned)
SELECT
    'table'::text                                AS object_type,
    n.nspname                                    AS schema_name,
    c.relname                                    AS object_name,
    format(
        'CREATE TABLE %I.%I (%s)%s;',
        n.nspname, c.relname,
        string_agg(
            format('%I %s%s',
                   a.attname,
                   format_type(a.atttypid, a.atttypmod),
                   CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END),
            ', ' ORDER BY a.attnum),
        coalesce(
            (SELECT format(' /* %s */', d.description)
             FROM pg_description d
             WHERE d.objoid = c.oid AND d.objsubid = 0),
            '')
    )                                            AS ddl_text,
    coalesce(
        (SELECT d.description
         FROM pg_description d
         WHERE d.objoid = c.oid AND d.objsubid = 0),
        ''
    )                                            AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
GROUP BY n.nspname, c.relname, c.oid

UNION ALL

-- 2. view DDL (relkind: v=view, m=materialized_view)
SELECT
    CASE c.relkind WHEN 'm' THEN 'materialized_view' ELSE 'view' END AS object_type,
    n.nspname                                                         AS schema_name,
    c.relname                                                         AS object_name,
    format(
        'CREATE %s VIEW %I.%I AS %s;',
        CASE c.relkind WHEN 'm' THEN 'MATERIALIZED' ELSE '' END,
        n.nspname, c.relname, pg_get_viewdef(c.oid, true)
    )                                                                 AS ddl_text,
    coalesce(
        (SELECT description FROM pg_description WHERE objoid = c.oid AND objsubid = 0),
        ''
    )                                                                 AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')

UNION ALL

-- 3. index DDL (relkind: i=index; exclude exclusion index to avoid noise)
SELECT
    'index'::text,
    n.nspname,
    c.relname,
    format('CREATE %s INDEX %I.%I %s;',
           CASE WHEN ix.indisunique THEN 'UNIQUE' ELSE '' END,
           n.nspname, c.relname, pg_get_indexdef(c.oid)),
    coalesce(
        (SELECT description FROM pg_description WHERE objoid = c.oid AND objsubid = 0),
        ''
    )
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index ix ON ix.indexrelid = c.oid
WHERE c.relkind = 'i'
  AND NOT ix.indisexclusion
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')

UNION ALL

-- 4. function/procedure signature (prokind: f=function, p=procedure, w=window agg)
SELECT
    CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END      AS object_type,
    n.nspname                                                         AS schema_name,
    p.proname                                                         AS object_name,
    format(
        'CREATE %s %s.%I(%s)%s;',
        CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END,
        n.nspname, p.proname,
        pg_get_function_arguments(p.oid),
        CASE WHEN p.prokind = 'f'
             THEN format(' RETURNS %s', pg_get_function_result(p.oid))
             ELSE '' END
    )                                                                 AS ddl_text,
    coalesce(
        (SELECT description FROM pg_description WHERE objoid = p.oid),
        ''
    )                                                                 AS comment
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prokind IN ('f', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')

UNION ALL

-- 5. constraint (contype: p=PK, u=UK, f=FK, c=CHECK)
SELECT
    CASE con.contype
         WHEN 'p' THEN 'primary_key'
         WHEN 'u' THEN 'unique_constraint'
         WHEN 'f' THEN 'foreign_key'
         WHEN 'c' THEN 'check_constraint'
    END                                                              AS object_type,
    n.nspname                                                        AS schema_name,
    con.conname                                                      AS object_name,
    pg_get_constraintdef(con.oid)                                    AS ddl_text,
    ''                                                               AS comment
FROM pg_constraint con
JOIN pg_namespace n ON n.oid = con.connamespace
WHERE con.contype IN ('p', 'u', 'f', 'c')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')

ORDER BY object_type, schema_name, object_name;
