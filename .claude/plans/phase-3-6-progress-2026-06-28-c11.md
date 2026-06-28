# Phase 3.6 AI Copilot — C11 完成（sqlglot + SqlSafetyService.validate_with_ast）

**Date**: 2026-06-28
**Branch (dbops)**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `49daba1` (C10)
**New HEAD**: TBD after commit
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §5 + §14 C11

---

## ✅ 本轮已完成

C11 = requirements.txt 追加 sqlglot + `SqlSafetyService.validate_with_ast`
权威 AST 校验 + 38 个安全测试（含 28 主用例 + 10 bonus 覆盖）。

### 1. `requirements.txt` 追加依赖

```diff
+# SQL 安全 AST 校验（Phase 3.6 SqlSafetyService.validate_with_ast 权威层）
+sqlglot>=25.0.0,<26.0.0
```

已 pip 安装（`sqlglot-25.34.1`）。模块顶部用 `try/except ImportError`
兜底，sqlglot 不可用时 AST 层返回明确 error，不阻断正则 Layer 2 路径。

### 2. `SqlSafetyService.validate_with_ast` 方法（NEW）

签名（plan §5 line 573-577 + §5 P0-4）：
```python
@classmethod
def validate_with_ast(
    cls,
    sql_text: str,
    db_type_code: str,
    *,
    allowed_tables: list[str] | None = None,
    allowed_columns: dict[str, list[str]] | None = None,
    denied_columns: list[str] | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    """返回 {valid, approved_sql, approved_sql_hash, errors, warnings}"""
```

### 3. 6 层 SQL 安全模型 Layer 3 实现

| Layer | plan §5 | 实现位置 |
|-------|---------|----------|
| Layer 1 | Dify Code 节点 JSON 解析+正则预检 | Dify 端（C12/C13） |
| Layer 2 | SqlSafetyService 现有正则 (defense-in-depth) | `validate_sql_readonly`（保留） |
| **Layer 3** | **SqlSafetyService.validate_with_ast (sqlglot) ← 权威** | **本 commit** |
| Layer 4 | approved_sql 保存 (Dify SQL ≠ 审批执行 SQL) | `approved_sql_hash` 字段 + SHA-256 |
| Layer 5 | Collector EE 客户端校验 | collector_client 侧（C13+） |
| Layer 6 | 目标 DB 只读账户 | DBA 配置 |

### 4. AST 校验 10 项核心规则

| # | 规则 | 实现 |
|---|------|------|
| 1 | 方言映射 | `_DIALECT_MAP`: postgresql→postgres, mssql/sqlserver→tsql, oracle→oracle, mysql→mysql |
| 2 | 多语句拒绝 | `sqlglot.parse()` 返回 list，长度 != 1 → error |
| 3 | 非 SELECT 拒绝 | `_is_top_level_readonly` 仅接受 `exp.Select` |
| 4 | SELECT * / table.* 拒绝（P1） | `_collect_star_descriptors` 遍历 `exp.Star` + `Column(this=Star())` |
| 5 | SELECT INTO 拒绝（防御性） | `_ast_has_into_clause` |
| 6 | FOR UPDATE 拒绝（防御性） | `_ast_has_lock_clause`（sqlglot 表示为 `locks=[Lock(update=True)]`） |
| 7 | 未授权表拒绝 | `_collect_from_sources` + `find_all(exp.Table)`（覆盖 FROM+JOIN+CTE alias） |
| 8 | 未授权列拒绝 | 列名 vs `allowed_columns[schema.table]` |
| 9 | 未限定列歧义拒绝（P1） | `_resolve_column_target_table`：1 个候选 → 通过 / 多候选 → ambiguous error |
| 10 | denied_columns 拒绝（Layer 1） + 敏感列 pattern 警告（Layer 2） | 双层防护：denied → error，SENSITIVE_COLUMN_PATTERN → warning |

### 5. approved_sql 与 SHA-256 hash（plan §5 P0-4）

执行期校验链：
1. Preview 阶段：调用 `validate_with_ast` → `approved_sql` + `approved_sql_hash`
2. `approved_sql`（AST 重写后）落 `ai_sql_audit.approved_sql`
3. Execute 阶段：AWX 回调回来 `rule_config.sql_text` 必须 ==
   `approved_sql`，且 `SHA-256(sql_text) == approved_sql_hash`
4. `schema_policy_hash` 变化 → 拒绝执行 → 要求重新 Preview

### 6. 关键设计权衡

| 决策 | 理由 |
|------|------|
| 用 `sqlglot.parse()`（list）而不是 `parse_one()` 检测多语句 | `parse_one` 静默返回第一条，导致 `SELECT 1; DROP TABLE x` 只校验 SELECT |
| CTE alias 不入 `allowed_tables` 白名单检查 | CTE 是查询本地虚拟表，其列通过 `find_all(Column)` 走列白名单 |
| `_extract_all_physical_columns` 仅扫描顶层 SELECT 作用域 | 避免 CTE body / 子查询的列污染外层歧义判断 |
| 敏感 pattern 仅 warning，不阻断 | Layer 2 是兜底，由执行器在 fetch 时 mask；plan §5 明确 P1 两层防护分工 |
| `max_rows` 钳制 + warning | 实际限行由 Collector EE 强制；后端提前钳制避免异常传播 |
| 解析失败时 `approved_sql_hash` 仍存在 | 审计追溯：拒绝的原始输入也要可验证 |
| 子查询 alias 列解析在 C11 范围外 | 需要跟踪子查询输出列；记入 §14 收尾工单 |

### 7. 测试（`test_sql_safety_service.py` NEW, 38 用例全过）

主用例 28 项（按 plan §14 C11 约定）：

| # | 测试 | 覆盖 |
|---|------|------|
| 1-3 | `test_empty_sql_returns_invalid` / `test_whitespace_only_sql_returns_invalid` / `test_multi_statement_rejected` | 空 / 空白 / 多语句 |
| 4-5 | `test_unparseable_sql_rejected` / `test_unsupported_db_type_rejected` | 解析失败 / db_type 未知 |
| 6-10 | `test_postgres_happy_path_valid` / `test_oracle_dialect_mapped` / `test_mssql_dialect_mapped` / `test_sqlserver_alias_maps_to_tsql` / `test_mysql_dialect_mapped` | 5 方言 happy path |
| 11-13 | `test_bare_select_star_rejected` / `test_qualified_select_star_rejected` / `test_qualified_select_star_in_join_rejected` | P1 SELECT * |
| 14-17 | `test_disallowed_table_rejected` / `test_bare_table_name_also_accepted_in_whitelist` / `test_join_with_alias_accepted` / `test_no_from_clause_rejected` | 表白名单 |
| 18-21 | `test_disallowed_column_rejected` / `test_unqualified_column_resolves_in_single_source` / `test_unqualified_column_ambiguous_in_multi_source_rejected` / `test_unqualified_column_not_in_any_whitelist_rejected` | 列白名单 + 解析 |
| 22-24 | `test_denied_column_rejected` / `test_sensitive_column_pattern_emits_warning_only` / `test_phone_column_pattern_emits_warning` | Layer 1 + Layer 2 |
| 25-28 | `test_approved_sql_hash_stable_for_same_input` / `test_approved_sql_hash_is_64_hex_for_rejected_input` / `test_select_into_rejected_by_ast` / `test_for_update_rejected_by_ast` | hash + 防御性兜底 |

Bonus 10 项（覆盖扩展）：

| # | 测试 | 覆盖 |
|---|------|------|
| 29-31 | INSERT / UPDATE / DELETE 拒绝 | 非 SELECT 语句 |
| 32-33 | CTE 显式列通过 / CTE 内 SELECT * 拒绝 | CTE |
| 34-35 | max_rows 钳制 / max_rows 非法类型拒绝 | max_rows 边界 |
| 36-37 | allowed_columns 开放策略 / allowed_tables 开放策略 | 策略容错 |
| 38 | `test_resolve_dialect_helper_public` | `resolve_dialect` 公开方法 |

---

## ✅ 验证结果

```
backend pytest .......................... 408 passed / 2 skipped / 0 failed
                                            (+38 from C11; prev C10: 370/2/0)
verify.sh ............................... failed=0 / skipped=2 / OK
```

---

## 📁 文件清单 (C11 共 4 文件)

```
backend/requirements.txt                                  | M +3    (sqlglot 依赖)
backend/app/services/sql_safety_service.py                | M +512  (validate_with_ast + 8 辅助函数)
backend/tests/test_sql_safety_service.py                  | A +397  (38 tests)
.claude/plans/phase-3-6-progress-2026-06-28-c11.md       | A +本文件
```

---

## 🚫 明确不在 C11 范围

| 不做项 | 原因 | 后续 commit |
|--------|------|-------------|
| SQL Preview API (`/ai/sql/preview`) | plan §5+ §5.2 — 需 AiSqlPreviewService + schema_policy_hash 路由 | C12 |
| SQL Execute API (`/ai/sql/execute`) | plan §6 — 需 ai_sql_audit + business_context + AWX callback | C17-C19 |
| 子查询 alias 列解析 | 需跟踪子查询输出列；当前实现仅支持顶层 FROM/JOIN 源 | C12+ (subquery_scope 优化) |
| Oracle q'[...]' 字符串字面量 | sqlglot 已自动 mask；现有正则 Layer 2 兜底 | — |
| Oracle q-quote 替代引号反混淆 | 非 P0；当前正则 Layer 2 已知 limitation | — |
| approved_sql_hash 在 ai_sql_audit 表的落库 | DDL + Model 在 C17-C18 | C17 |
| Dify SQL generator app 集成 | 独立 C 起手 | C12-C13 |

---

## 🚀 下一会话快速恢复 (C12 起手)

C12 = `AiSqlPreviewService` + `/ai/sql/preview` API + 复用
`AiSchemaContextService` 的 schema_policy_hash + Dify SQL generator app 调用。

1. 加载本文件 + `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §5.2 + §5.3
2. 新增 `backend/app/services/ai/ai_sql_preview_service.py`
   - `preview_sql(db, *, instance_id, database_name, sql_generator_input)`
     → Dify sql-generator app → 拿到 generated_sql → 调
     `SqlSafetyService.validate_with_ast` 拿到 approved_sql →
     构造 schema_policy_hash（复用 C10 逻辑）→ 落 ai_sql_audit
3. 新增 `POST /api/sql/preview` API
4. 复用 AiChatService 的 Redis idempotency + 启动清理模式
5. `tests/test_ai_sql_preview_service.py` + 集成 verify.sh

---

## 📋 收尾待办 (按 plan §14 顺序)

- ✅ ~~C6: SQL Schema Snapshot 底座~~ (`d6bfbba`)
- ✅ ~~C7: PostgreSQL 固定元数据 SQL 模板~~ (`7850c43`)
- ✅ ~~C8: Builder + Role + Playbook 路由~~ (`a64e626` + `9b93fb3`)
- ✅ ~~C9: Callback 落库服务~~ (`fad6b66`)
- ✅ ~~C10: API 端点 + AiSchemaContextService~~ (`49daba1`)
- ✅ C11: requirements + sqlglot + validate_with_ast + 28 安全测试 (本 commit)
- C12-C16: SQL Preview / ai_sql_audit
- C17-C19: SQL Execute + Callback
- C20-C21: 前端 SchemaInspector + SqlPreview
- C22-C26: Inspection AI Analysis
- C27: DOCX AI
- C28-C32: 收尾