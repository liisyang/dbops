# Phase 3.6 AI Copilot — C10 完成（Schema Snapshot API + AiSchemaContextService）

**Date**: 2026-06-28
**Branch (dbops)**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `fad6b66` (C9)
**New HEAD**: TBD after commit
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §4.1 + §4.6 + §18 C32

---

## ✅ 本轮已完成

C10 = `AiSchemaSnapshotService` + `AiSchemaContextService` + 4 个 API 端点 +
启动时 running timeout 清理。

### 1. `ai_schema_snapshot_service.py`（NEW, 343 行）

入口（全部 staticmethod / classmethod，签名 `Service.method(db, *, kw=...)`）:

| 方法 | 用途 | plan 引用 |
|------|------|----------|
| `trigger_collection(db, *, instance_id, database_name, requested_by, request_base_url)` | POST collect：复用 CollectorService.launch_collector_run(run_type="ai_schema") 调起 AWX | §4.1 |
| `get_snapshot_status(db, *, instance_id, database_name)` | 内部：返回 is_current=true snapshot | §4.6 |
| `get_latest_any_status(db, *, instance_id, database_name)` | GET status：is_current 优先，否则最新任意状态 | §4.1 |
| `list_history(db, *, instance_id, database_name, limit)` | GET history：created_at DESC | §4.1 |
| `cleanup_running_timeouts(db)` | 启动时清理 running 超时 → failed (COLLECTION_TIMEOUT) | §18 C32 |

异常（与 C9 callback 同款分层）:
- `InstanceNotFoundError` → 404
- `FeatureDisabledError` → 503 (AI_SQL_PREVIEW_ENABLED=false)
- `UnsupportedDbTypeError` → 422 (db_type 不在 capabilities)
- `AwxLaunchError` → 502 (AWX launch 失败)
- `AiSchemaSnapshotError` → 基类

`_normalize_database_name`：空值 → `<default>`（与 C9 callback 一致）；200+ 字符截断到 200。

### 2. `ai_schema_context_service.py`（NEW, 366 行）

`build_schema_context(db, *, instance_id, database_name) -> dict`

核心不变量（plan §4.5 P0-3 + §4.6）:
- DB **不保存** schema_context 展示文本，仅保存结构化 JSON 字段
- schema_context 文本**每次调用前实时构建**
- `schema_policy_hash` 基于**规范化策略内容**（canonical JSON of
  {snapshot_hash, allowed_schemas, allowed_tables, allowed_columns,
  denied_columns, policy_version}）— 文本格式变化不应让 Execute 误判
  策略变更
- 字符上限受 `AI_SCHEMA_CONTEXT_MAX_CHARS` (默认 30000) 控制；超长追加
  `…(truncated)` 标记（**不**参与 hash）
- tables/columns 受 `AI_SCHEMA_MAX_TABLES` / `AI_SCHEMA_MAX_COLUMNS_PER_TABLE` 截断
- available=false 时 schema_policy_hash 必须为 None

`POLICY_VERSION = "2026-06-28-v1"` 常量（改值会破坏 Execute 阶段 hash 校验）。

未通过 `is_usable()` 检查的原因映射到 `ContextUnavailableReason`:
- `no_snapshot`
- `snapshot_not_success` (pending/running/failed)
- `snapshot_not_current`
- `snapshot_expired`

### 3. `api/ai.py` 追加 4 端点（C10-4）

| Method | Path | 状态码 | 行为 |
|--------|------|--------|------|
| POST | `/ai/sql/schema-snapshots/{instance_id}/collect` | 202 | 调 AWX，返回 collector_run_id |
| GET  | `/ai/sql/schema-snapshots/{instance_id}` | 200 | 最新 snapshot（is_current 优先，否则 latest） |
| GET  | `/ai/sql/schema-snapshots/{instance_id}/history` | 200 | 历史 snapshot 列表 |
| GET  | `/ai/sql/schema-snapshots/{instance_id}/context` | 200 | 实时 Dify inputs (schema_context + schema_policy_hash) |

异常映射（统一在 api 层）：
- `InstanceNotFoundError` → 404
- `FeatureDisabledError` → 503
- `UnsupportedDbTypeError` → 422
- `AwxLaunchError` → 502
- `AiSchemaSnapshotError` → 400

### 4. `app/schemas/ai.py` 追加 4 个 Pydantic schema

- `AiSchemaSnapshotCollectRequest`
- `AiSchemaSnapshotCollectResponse`
- `AiSchemaSnapshotListResponse`（items + total）
- `AiSchemaContextResponse`（available + 全字段 + reason）

### 5. `main.py` 启动清理（C10-5）

在 lifespan 中，与 chat cleanup 平级，新增：
```python
if settings.AI_SQL_PREVIEW_ENABLED:
    cleaned = await asyncio.to_thread(
        lambda: AiSchemaSnapshotService.cleanup_running_timeouts(SessionLocal())
    )
```
防止 collector 中途异常退出后 running 永久卡住（plan §18 C32）。

### 6. 测试（`test_ai_schema_snapshot_service.py` + `test_ai_schema_context_service.py`，37 用例全过）

#### test_ai_schema_snapshot_service.py（17 用例）

| # | 测试 | 覆盖 |
|---|------|------|
| 1-3 | `test_no_snapshot_returns_none` / `test_is_current_preferred` / `test_get_latest_any_status_falls_back_to_newest` | 状态查询 3 路径 |
| 4-5 | `test_history_respects_limit` / `test_history_empty` | history |
| 6-8 | `test_marks_old_running_as_failed` / `test_no_op_when_no_running` / `test_cutoff_uses_configured_timeout` | cleanup_running_timeouts |
| 9-13 | `test_feature_disabled_raises` / `test_unsupported_db_type_raises` / `test_instance_not_found_raises` / `test_happy_path` / `test_awx_launch_error_translated` | trigger_collection 5 异常路径 |
| 14-17 | `test_none_to_default` / `test_empty_string_to_default` / `test_truncate_long_name` / `test_normal_name_kept` | _normalize_database_name |

#### test_ai_schema_context_service.py（20 用例）

| # | 测试 | 覆盖 |
|---|------|------|
| 1-5 | unavailable 5 路径（no_snapshot / pending / running / not_current / expired） | 状态机 |
| 6-10 | `test_happy_path_returns_available` / `test_schema_policy_hash_stable_for_same_input` / `test_schema_policy_hash_changes_with_snapshot_hash` / `test_schema_policy_hash_changes_with_policy_version` / `test_schema_policy_hash_independent_of_text_format` | schema_policy_hash 5 不变量 |
| 11 | `test_dialect_mapping`（6 个 db_type_code 参数化） | SQL dialect |
| 12-14 | `test_short_text_unchanged` / `test_long_text_truncated_with_marker` / `test_no_tables_section` | 文本渲染 3 路径 |
| 15 | `test_policy_version_stable` | POLICY_VERSION 常量 |

测试策略：自制 FakeSession + InMemoryQueryStore（与 C9 callback 测试同款），不连真实 DB。

---

## ✅ 验证结果

```
backend pytest .................... 370 passed / 2 skipped / 0 failed
                                      (+37 from C10; prev C9: 333 passed)
verify.sh ......................... failed=0 / skipped=2 / OK
```

---

## 📁 文件清单 (C10 共 6 文件)

```
backend/app/services/ai/ai_schema_snapshot_service.py     | A +343  (NEW trigger/status/history/cleanup)
backend/app/services/ai/ai_schema_context_service.py      | A +366  (NEW build_schema_context)
backend/app/api/ai.py                                     | M +137  (4 endpoints + imports)
backend/app/schemas/ai.py                                 | M +67   (4 Pydantic schemas)
backend/app/main.py                                       | M +25   (lifespan startup cleanup)
backend/tests/test_ai_schema_snapshot_service.py          | A +477  (17 tests)
backend/tests/test_ai_schema_context_service.py           | A +387  (20 tests)
.claude/plans/phase-3-6-progress-2026-06-28-c10.md       | A +本文件
```

---

## 🚫 明确不在 C10 范围

| 不做项 | 原因 | 后续 commit |
|--------|------|-------------|
| SQL Preview API (`/ai/sql/preview`) | plan §4.5+ §5 — 需 sqlglot AST + SqlSafetyService | C13 |
| SQL Execute API (`/ai/sql/execute`) | plan §6 — 需 ai_sql_audit + business_context 路由 | C17-C19 |
| Inspection AI Analysis | plan §2.4 §8 — 独立 ai_analysis 表 + 两阶段发布 | C22-C26 |
| Frontend `src/views/ai/SchemaInspector.vue` | plan §4.1 提示 — 后续 UI commit | C14+ (frontend) |
| `chat_enabled` capabilities 检查（schema snapshot 端点独立） | plan §11 — 现状已 OK | — |

---

## 🚀 下一会话快速恢复 (C11 起手)

C11 = requirements.txt + sqlglot + `SqlSafetyService.validate_with_ast` + 28 安全测试。

1. 加载本文件 + `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §5
2. `requirements.txt` 新增 `sqlglot>=25.0.0,<26.0.0`
3. `app/services/sql_safety_service.py` 新增 `validate_with_ast` 方法
4. 实现 §5 P1 SELECT * 拒绝、§5 P1 敏感列掩码
5. `tests/test_sql_safety_service.py` 追加 28 安全用例
6. `bash scripts/ai/verify.sh`

---

## 📋 收尾待办 (按 plan §14 顺序)

- ✅ ~~C6: SQL Schema Snapshot 底座~~ (`d6bfbba`)
- ✅ ~~C7: PostgreSQL 固定元数据 SQL 模板~~ (`7850c43`)
- ✅ ~~C8: Builder + Role + Playbook 路由~~ (`a64e626` + `9b93fb3`)
- ✅ ~~C9: Callback 落库服务~~ (`fad6b66`)
- ✅ C10: API 端点 + AiSchemaContextService (本 commit)
- C11: requirements + sqlglot + validate_with_ast + 28 安全测试
- C12-C19: SQL Preview/Execute + ai_sql_audit
- C22-C26: Inspection AI Analysis
- C27: DOCX AI
- C28-C32: 收尾