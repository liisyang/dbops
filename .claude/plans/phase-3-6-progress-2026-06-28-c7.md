# Phase 3.6 AI Copilot — C7 完成（PostgreSQL 固定元数据 SQL 模板）

**Date**: 2026-06-28
**Branch**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `d6bfbba` (C6)
**New HEAD**: (本 commit)
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §4.4 line 433-441

---

## ✅ 本轮已完成

C7 = **PostgreSQL 固定元数据 SQL 模板**（plan §4.4）。

### 1. SQL 模板（`backend/app/services/ai/sql_templates/postgresql/pg_schema_columns.sql`）

- 单条 SELECT，查 `information_schema.columns`
- 返回 6 列：table_schema / table_name / column_name / data_type / is_nullable / ordinal_position
- WHERE 排除 `pg_catalog` + `information_schema`
- ORDER BY 稳定（schema → table → ordinal）→ 保证幂等 hash
- header 注释含 Phase 标识 + plan 参考 + 完整性约束说明

### 2. 单元测试（`backend/tests/test_pg_schema_columns_sql.py`）

- **30 个测试**，全部通过
- 6 类覆盖：
  1. 文件存在 + 可读 + 含 Phase 3.6 标识
  2. SQL 只读性：11 个禁止关键字（INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE/GRANT/REVOKE/VACUUM/COPY）
  3. SELECT 列集合：6 列参数化测试 + 列数恰好 6
  4. WHERE 过滤：含 pg_catalog / 含 information_schema / 用 information_schema.columns 视图
  5. ORDER BY：稳定 + 键顺序 (table_schema, table_name, ordinal_position)
  6. Header 注释：含用途 + 含只读说明

### 3. Live 验证（dev 库 10.134.185.85:5432）

- SQL 跑通：**981 行 / 1 schema (dbops) / 56 tables**
- 6 列结构与 DDL/Model 一致
- data_type 涵盖 bigint / uuid / character varying / text / jsonb / integer / timestamp with time zone
- pg_catalog / information_schema 正确排除

---

## ✅ 验证结果

```
tests/test_pg_schema_columns_sql.py ........... 30 passed in 0.10s
verify.sh ..................................... 269 passed / 30 new = 299 passed, 2 skipped, 0 failed
```

---

## 📁 文件清单（C7 共 2 文件）

```
backend/app/services/ai/sql_templates/postgresql/pg_schema_columns.sql | A +33   (固定 SQL 模板)
backend/tests/test_pg_schema_columns_sql.py                            | A +178  (30 个测试)
.claude/plans/phase-3-6-progress-2026-06-28-c7.md                      | A +本文件
```

---

## 🚫 明确不在 C7 范围

| 不做项 | 原因 | 后续 commit |
|--------|------|-------------|
| `_AiSchemaMetadataBuilder` | 需配合 Role + Playbook | C8 |
| 独立 Role `db_schema_metadata_collect` | 需 Ansible 端配合 | C8 |
| Playbook 路由 + check_codes 更新 | 需 Ansible 端配合 | C8 |
| Callback 落库（truncated → failed） | 需 AWX callback 链 | C9 |
| 完整性校验逻辑 | collector_client 层 + callback | C9 |
| 多个 SQL 模板 | plan §4.4 只列 1 个 | 待 Phase 3.6+ |

---

## 🚀 下一会话快速恢复（C8 起手）

C8 = `_AiSchemaMetadataBuilder`（check_code=DB_SCHEMA_METADATA_COLLECTION, business_domain=ai_schema）+ 独立 Role `db_schema_metadata_collect` + Playbook 路由更新。

1. 加载本文件
2. 在 `backend/app/services/collector/check_item_builder/` 加 `_AiSchemaMetadataBuilder`
3. 在 `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml` 新增 Role
4. 在 `ansible-playbooks/playbooks/dbops_collector_generic.yml` 加路由
5. 更新 `db_python_collect_check_codes` 加 `'DB_SCHEMA_METADATA_COLLECTION'`
6. **跨仓库** commit：dbops + ansible-playbooks

---

## 📋 收尾待办（按 plan §14 顺序）

- ✅ ~~C6: SQL Schema Snapshot 底座~~（`d6bfbba`）
- ✅ ~~C7: PostgreSQL 固定元数据 SQL 模板~~（本 commit）
- C8: Builder + Role + Playbook 路由（**跨 ansible-playbooks 仓库**）
- C9: Callback 落库服务
- C10: API 端点 + AiSchemaContextService
- C11-C26: SQL Preview → SQL Execute → Inspection AI Analysis
- C28-C32: 收尾
