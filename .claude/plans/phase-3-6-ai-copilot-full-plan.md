# Phase 3.6 AI Copilot — 完整实施计划（v4，第三轮审查修正 6 P0 + 15 P1）

**Source**: `/home/lisiyang/aiplan/claude-code-plan-ai-phase3_6-complete.md`
**Date**: 2026-06-27
**Branch**: feature/phase-3.5-db-readonly-sql-exec
**Complexity**: LARGE（6 个 Phase × ~32 Commits × ~60 文件变更）
**Review**: 三轮审查 — 6 P0 + 15 P1 修正，均基于真实代码验证
**Status**: ✅ 可进入编码

---

## 0. 真实仓库现状核对 + 关键代码证据

### 0.1 数据库迁移方式
**纯 SQL 文件**在 `backend/db/`。无 Alembic。
→ **按 Phase 拆分 DDL**：共 8 个文件（4 正向 + 4 回滚）：

```text
dbops_phase3_6a_ai_chat.sql          / rollback_phase3_6a_ai_chat.sql
dbops_phase3_6b0_schema_snapshot.sql  / rollback_phase3_6b0_schema_snapshot.sql
dbops_phase3_6b_ai_sql.sql            / rollback_phase3_6b_ai_sql.sql
dbops_phase3_6c_inspection_ai.sql     / rollback_phase3_6c_inspection_ai.sql
```

### 0.2 SQLAlchemy
**纯同步**（`database.py:12-21`）。`sessionmaker(autocommit=False, autoflush=False)`，`get_db()` 返回同步 `Session`。
→ DifyService 使用 `httpx.Client`（同步，连接池复用）。禁止混用同步/异步数据库会话。

### 0.3 AI Router prefix
**无 AI Router**。现有路由 prefix=`/api/v1`（`main.py:67-75`）。
→ 新增 `app.include_router(ai.router, prefix="/api/v1", tags=["ai"])`。

### 0.4 DB_READONLY_SQL_EXEC
**异步 callback**（`inspection_service.py:404-587`）：创建 CollectorRun → AWX launch → callback → handle_callback。
→ ai/sql/execute 复用此链路。callback 必须回写 `ai_sql_audit`。

### 0.5 schema_context
**不存在**。无表/字段元数据。
→ **必须新增 Phase 3.6B0（Schema Snapshot + Schema Policy）**，否则 SQL Preview 大多数请求只能返回 `schema_context_unavailable`。

### 0.6 SqlSafetyService
**已有正则实现**（`sql_safety_service.py`，241 行），不是 AST。
→ 引入 `sqlglot` 为权威 AST 校验，保留正则为 defense-in-depth。

### 0.7 巡检报告/DOCX
已全部对照代码确认文件路径和行号正确。

### 0.8 前端规范
已确认：路由延迟加载、菜单在 `Layout.vue:131-207` 内联、API 均在 `assets.ts` 的 `assetsApi` 对象中。

### 0.9 关键代码证据（P0 审查新增）

| # | 证据 | 文件:行号 |
|---|---|---|
| E1 | Playbook 验证 `business_domain in ['inspection', 'inspection_verify', 'backup_status']` | `ansible-playbooks/.../dbops_collector_generic.yml:183` |
| E2 | db_sql_readonly role 验证 `check_code == 'DB_READONLY_SQL_EXEC'` + `business_domain` 白名单 | `ansible-playbooks/.../db_sql_readonly_collect/tasks/main.yml:30-32` |
| E3 | Builder 硬编码 `business_domain="inspection"` | `check_item_builder_registry.py:877` |
| E4 | `CollectorService.handle_callback` 仅分发 `inspection` (line 1338) 和 `backup_status` (line 1351)，无 `ai_sql`/`ai_schema` | `collector_service.py:1338-1352` |
| E5 | 项目不使用 `httpx` 也不使用 `requests` | `requirements.txt` grep 结果为空 |
| E6 | Registry 按 `check_code` 单键注册 | `check_item_builder_registry.py:132` — `cls._builders[check_code] = builder` |
| E7 | `db_python_collect_check_codes = db_fact_check_codes + ['DB_READONLY_SQL_EXEC']` | `dbops_collector_generic.yml:124` |
| E8 | SQLAlchemy `metadata` 是 Base 保留属性 | `dbops_assets.py:25` — `DbopsAssetBase.metadata.schema = "dbops"` |
| E9 | 无 Dify 配置在 `.env` | `.env` 无 DIFY_* 前缀变量 |

---

## 1. 总体架构

```
前端 Chat.vue (AiMessageList/Bubble/Composer) + ReportDetail/InstanceReport (AiAnalysisCard)
    │ /api/v1/ai/*                     │ /api/v1/inspection/*/ai-analysis
    ▼                                  ▼
FastAPI (同步 Session)
  api/ai.py ─ ai_chat_service ─ ai_sql_service ─ inspection_ai_service
    │               │                    │
    ▼               ▼                    ▼
 DifyService    SqlSafetyService    InspectionAiContextService
 (httpx pool)   (regex + sqlglot)   (source data builder)
    │               │                    │
    ▼               ▼                    ▼
 Dify HTTP      Collector/AWX        inspection_ai_analysis
 (3 apps)       (business_domain=    (two-phase publish:
                 ai_sql → callback    new ready → old superseded)
                 → AiSqlCallbackService
                 → ai_sql_audit)
```

---

## 2. 数据库迁移（按 Phase 拆分）

### 2.1 Phase 3.6A — Chat（`dbops_phase3_6a_ai_chat.sql`）

**ai_chat_session**: id, session_code(UNIQUE), user_id(FK→users), title, dify_conversation_id, model_provider, message_count, last_message_at, created/updated_at

**ai_chat_message**: id, session_id(FK CASCADE), user_id(FK SET NULL), **client_request_id UUID**, role(user/assistant/system), message_type(chat/sql_preview/sql_result/error), **status(pending/completed/failed/stale)**, content, **parent_message_id**(FK self), **metadata_json JSONB** (列名 `metadata`, Python 属性 `metadata_json`), dify_task_id/workflow_run_id/elapsed_ms/total_tokens, error_code, **processing_started_at TIMESTAMPTZ NULL**, **processing_expires_at TIMESTAMPTZ NULL**, **attempt_count INTEGER NOT NULL DEFAULT 0**, created_at

关键约束（P0-5 修正 — 租约机制）：
- **`client_request_id` 只写在 user message**，assistant message 的 client_request_id=NULL
- 部分唯一索引: `UNIQUE(session_id, client_request_id) WHERE role='user' AND client_request_id IS NOT NULL`
- 并发 pending 约束: `UNIQUE(session_id) WHERE role='assistant' AND status='pending'` — 第二个并发请求直接 409
- CHECK constraints on role, message_type, status
- **租约机制**: 新消息发送时设置 `processing_expires_at = now() + 90s`。新请求遇到 pending 时：
  - `processing_expires_at > now()` → 409（正常处理中）
  - `processing_expires_at <= now()` → 将旧 pending 标记 `stale`，允许创建新请求
- **定时清理**: 启动时或定时任务执行 `UPDATE SET status='stale', error_code='PROCESSING_LEASE_EXPIRED' WHERE role='assistant' AND status='pending' AND processing_expires_at < now()`
- Chat Message 状态机: `pending → completed / failed / stale`

> **注意**: `metadata` 是 SQLAlchemy Declarative Base 的保留属性（`DbopsAssetBase.metadata.schema = "dbops"`）。Model 中必须使用 `metadata_json = Column("metadata", JSONB, ...)` 映射，不能直接声明 `metadata = Column(...)`。

### 2.2 Phase 3.6B0 — Schema Snapshot（`dbops_phase3_6b0_schema_snapshot.sql`）

**ai_sql_schema_snapshot**: id, instance_id(NOT NULL), db_type_code(NOT NULL), **database_name VARCHAR(200) NOT NULL**, schema_name, **status** VARCHAR(20) NOT NULL DEFAULT 'pending' (pending/running/success/failed/unavailable), allowed_schemas JSONB DEFAULT '[]', allowed_tables JSONB DEFAULT '[]', allowed_columns JSONB DEFAULT '{}', denied_columns JSONB DEFAULT '[]', **is_current** BOOLEAN DEFAULT false, collector_run_id, **snapshot_hash VARCHAR(64) NULL**, **total_tables INT**, **total_columns INT**, **expires_at** TIMESTAMPTZ, **error_code VARCHAR(100) NULL**, **error_message TEXT NULL**, collected_at, created_at

> **设计决策**: 数据库**不保存** `schema_context` 展示文本。只保存结构化策略 JSON（`allowed_schemas`/`allowed_tables`/`allowed_columns`/`denied_columns`）。调用 Dify 前根据 JSON **实时稳定生成** `schema_context` 文本并纳入 `snapshot_hash`。安全策略只有一个事实源，不会出现文本与 JSON 不一致。

**P0-2 修正 — NOT NULL → NULL + 状态约束**：

```sql
-- snapshot_hash 改为 NULLABLE（pending/running 阶段无值）
snapshot_hash VARCHAR(64) NULL,

-- 状态相关 CHECK（注意：schema_context 不存储在数据库，调用 Dify 前实时生成）
CONSTRAINT chk_ai_sql_schema_snapshot_payload CHECK (
    (
        status = 'success'
        AND snapshot_hash IS NOT NULL
        AND allowed_schemas IS NOT NULL
        AND collected_at IS NOT NULL
        AND expires_at IS NOT NULL
    )
    OR
    (
        status IN ('pending', 'running')
        AND error_message IS NULL
        AND error_code IS NULL
    )
    OR
    (
        status IN ('failed', 'unavailable')
        AND error_message IS NOT NULL
    )
)
```

**database_name NOT NULL**: 不允许 NULL（PostgreSQL 部分唯一索引对 NULL 处理不同）。无明确 database_name 时存 `<default>`。

**is_current 默认 false**: 新 Snapshot 只有采集成功后才设为 true。旧 success Snapshot 在新 Snapshot 成功前继续保持 current（two-phase publish，同巡检分析）。

**唯一约束**:
```sql
-- Partial unique index
CREATE UNIQUE INDEX uq_ai_sql_schema_snapshot_current
    ON ai_sql_schema_snapshot (instance_id, database_name)
    WHERE is_current = true;
```

**Schema Snapshot 状态机**:
```
pending → running → success
                  ├→ failed
                  └→ unavailable
```

**Snapshot 超时恢复**: `running` 超过 `AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS`（默认 300s）→ 标记 `failed`，`error_code='COLLECTION_TIMEOUT'`。

**schema JSON 格式**（含 allowed_schemas — P1 新增）:
```json
{
  "allowed_schemas": ["app", "reporting"],
  "allowed_tables": ["app.orders", "app.customers"],
  "allowed_columns": {"app.orders": ["id", "status", "created_at"]},
  "denied_columns": ["password_hash", "secret_key", "token", "api_key", "credential"]
}
```

**schema_context 不存储**: 数据库只保存结构化 JSON（`allowed_schemas`/`allowed_tables`/`allowed_columns`/`denied_columns`）。`schema_context`（给 LLM 的文本摘要）在调用 Dify 前**实时生成**，从 JSON 字段确定性构建，并纳入 `snapshot_hash` 计算。安全策略只有一个事实源。

配置:
```bash
AI_SCHEMA_SNAPSHOT_TTL_HOURS=24
AI_SCHEMA_CONTEXT_MAX_CHARS=30000
AI_SCHEMA_MAX_TABLES=100
AI_SCHEMA_MAX_COLUMNS_PER_TABLE=100
AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS=300
AI_SCHEMA_RESULT_MAX_ROWS=20000      # 独立限制，远大于通用 SQL
AI_SCHEMA_RESULT_MAX_BYTES=10485760  # 10MB
```

### 2.3 Phase 3.6B — SQL Audit（`dbops_phase3_6b_ai_sql.sql`）

**ai_sql_audit**: id, session_id(FK SET NULL), message_id(FK SET NULL), **result_message_id**(FK SET NULL), user_id(FK SET NULL), instance_id(NOT NULL), db_type_code, user_question,
  **generated_sql**(Dify原始), **generated_sql_hash**, **approved_sql**(AST重写后), **approved_sql_hash**,
  **preview_safety_status**(passed/rejected), **preview_safety_reason**, **execution_safety_status**(passed/rejected), **execution_safety_reason**,
  safety_policy_version, **schema_snapshot_id**(FK→ai_sql_schema_snapshot), schema_policy_hash, dify_workflow_run_id, **sql_workflow_version**,
  previewed_at, **execution_status**(not_requested/pending/running/success/failed/timeout/cancelled),
  collector_run_id, collector_run_item_id, row_count, duration_ms, error_message, executed_at, **completed_at**, created_at

**P0-6 修正 — 状态机使用条件 UPDATE，不依赖 CHECK 约束**：

普通 CHECK 只能检查当前行，无法比较 OLD vs NEW。状态转换由应用层条件更新实现：

```python
# AiSqlService / AiSqlCallbackService 中:
affected = db.execute(
    update(AiSqlAudit)
    .where(AiSqlAudit.id == audit_id)
    .where(AiSqlAudit.execution_status.in_(['not_requested', 'pending', 'running']))
    .values(execution_status=new_status, ...)
).rowcount

if affected == 0:
    # 已被其他 callback 完成或状态不允许转换 — 幂等处理
    logger.info("audit %s state transition rejected (already terminal or raced)", audit_id)
```

**执行状态机**:
```
not_requested → pending → running → success
                                  ├→ failed
                                  ├→ timeout
                                  └→ cancelled
```

数据库 CHECK 只负责限制枚举值：
```sql
CONSTRAINT chk_execution_status CHECK (
    execution_status IN ('not_requested', 'pending', 'running', 'success', 'failed', 'timeout', 'cancelled')
)
```

**Preview 与 Execute 分离**:
- `not_requested`: Preview 完成但尚未点击执行
- `pending`: 已请求执行，等待 AWX 调度
- `running`: AWX Job 已启动

**Preview 时固定绑定**: schema_snapshot_id + schema_policy_hash。Execute 时检查 snapshot 仍 current、未过期、hash 一致。不符 → 409 要求重新采集+Preview。

### 2.4 Phase 3.6C — Inspection AI Analysis（`dbops_phase3_6c_inspection_ai.sql`）

**inspection_ai_analysis**: id, report_id(FK CASCADE), instance_report_id(FK CASCADE nullable), analysis_scope(overall/instance),
  **version**(INT DEFAULT 1), **is_current**(BOOL DEFAULT false), **superseded_at**,
  analysis_status(**pending**/ready/failed/reviewed), model_provider, dify_workflow_run_id, **workflow_version**,
  source_data_hash, analysis_result **NULLABLE**, summary **NULLABLE**, risk_level, confidence,
  **error_code**, **error_message**,
  reviewed_by(FK→users), reviewed_at, review_comment TEXT NULL, created_by(FK→users), created/updated_at,
  **processing_started_at TIMESTAMPTZ NULL**, **processing_expires_at TIMESTAMPTZ NULL**

**P0-4 修正 — 两阶段发布（成功后切换 current）**:

第一阶段（请求分析）:
```
1. SELECT report FOR UPDATE（行锁）
2. 旧 ready/reviewed 版本继续 is_current=true（不修改！）
3. 插入新 pending 版本，is_current=false
4. COMMIT
```

第二阶段（Dify 返回后）:
```
成功:
  事务:
    1. SELECT report FOR UPDATE
    2. 旧 current → is_current=false, superseded_at=now()
    3. 新版本 → status=ready, is_current=true
    4. COMMIT

失败:
  事务:
    1. 新版本 → status=failed, is_current=false, error_code=...
    2. 旧版本继续 is_current=true（不受影响）
    3. COMMIT
```

**超时恢复**: pending 超过 `DIFY_REPORT_TIMEOUT_SECONDS + 30` → 标记 `failed`，`error_code='ANALYSIS_TIMEOUT'`。

**CHECK 约束**:
```sql
CONSTRAINT chk_inspection_ai_analysis_payload CHECK (
    (
        analysis_status IN ('ready', 'reviewed')
        AND analysis_result IS NOT NULL
        AND summary IS NOT NULL
    )
    OR
    (
        analysis_status = 'failed'
        AND error_message IS NOT NULL
    )
    OR
    (
        analysis_status = 'pending'
        AND analysis_result IS NULL
        AND error_message IS NULL
    )
)
```

- Partial UNIQUE INDEX (report_id) WHERE scope=overall AND is_current=true
- Partial UNIQUE INDEX (report_id, instance_report_id) WHERE scope=instance AND is_current=true

**Inspection AI Analysis 状态机**:
```
pending → ready → reviewed
       └→ failed
```

---

## 3. DifyService 设计

`backend/app/services/dify_service.py` (NEW)

```python
class DifyService:
    _client: httpx.Client | None = None

    @classmethod
    def init_client(cls, base_url: str, timeout: int) -> None:
        """在 app lifespan 中调用一次。base_url 自动 rstrip('/')。"""
        cls._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    @classmethod
    def close_client(cls) -> None: ...

    @classmethod
    def chat_message(cls, *, query, inputs, user, conversation_id=None) -> dict
        # POST /chat-messages (blocking)

    @classmethod
    def run_sql_workflow(cls, *, inputs, user) -> dict
        # POST /workflows/run (blocking)

    @classmethod
    def run_report_workflow(cls, *, inputs, user) -> dict
        # POST /workflows/run (blocking)
```

**P1 — 独立超时配置**:
```bash
DIFY_CONNECT_TIMEOUT_SECONDS=10
DIFY_CHAT_TIMEOUT_SECONDS=60
DIFY_SQL_TIMEOUT_SECONDS=60
DIFY_REPORT_TIMEOUT_SECONDS=120
```

Chat/Workflow POST **默认不自动重试**（网络超时不代表 Dify 没有执行成功，盲目重试可能产生重复 Workflow Run）。

异常: DifyError(base) / DifyConfigurationError / DifyTimeoutError / DifyConnectionError / DifyHttpError / DifyResponseFormatError / DifyWorkflowFailedError

依赖版本: `httpx>=0.27.0,<0.29.0`

---

## 4. Schema Snapshot 完整异步采集闭环（Phase 3.6B0）

**SQL Preview 必须在 Schema Snapshot 具备后才能实际工作**。`ensure_schema_snapshot()` 不能在同步请求里假装返回 schema（AWX callback 尚未完成），必须有独立采集链路。

### 4.1 API 端点

```text
POST /api/v1/ai/sql/schema-snapshots/{instance_id}/collect
  → 创建 CollectorRun(check_code=DB_SCHEMA_METADATA_COLLECTION, business_domain=ai_schema)
  → 返回 202 + collector_run_id

GET  /api/v1/ai/sql/schema-snapshots/{instance_id}
  → 返回最新 Snapshot 状态: {status, snapshot_hash, total_tables, total_columns, collected_at, expires_at, ...}
  → 不存在或过期 → 提示重新采集
```

### 4.2 Collector 链路 — P0-1 修正：使用独立 Role

**问题**: 现有 `db_sql_readonly_collect` Role 硬编码校验:
- `check_code == 'DB_READONLY_SQL_EXEC'` (main.yml:30)
- `business_domain in ['inspection', 'inspection_verify', 'backup_status']` (main.yml:32)
- `db_python_collect_check_codes` 只包含 `db_fact_check_codes + ['DB_READONLY_SQL_EXEC']` (generic.yml:124)

`DB_SCHEMA_METADATA_COLLECTION` 直接复用会全线失败。

**推荐方案：新增独立 Role**（语义清晰，安全边界独立）:

```
ansible-playbooks/playbooks/roles/db_schema_metadata_collect/
└── tasks/main.yml
```

职责:
1. 只接受 `check_code=DB_SCHEMA_METADATA_COLLECTION`
2. 只允许后端内置的元数据查询模板（不接受 Dify/用户传入 sql_text）
3. 调用相同 `collector_client`
4. 返回标准 `columns / rows / duration_ms / sql_hash / total_rows / returned_rows / truncated`

Playbook 新增路由:
```yaml
- name: Route DB schema metadata items
  ansible.builtin.include_role:
    name: db_schema_metadata_collect
  loop: "{{ items }}"
  loop_control:
    loop_var: collector_item
  when:
    - collector_item.check_code == 'DB_SCHEMA_METADATA_COLLECTION'
    - collector_item.executor_type | default('') == 'db_sql_readonly'
```

同时更新 `db_python_collect_check_codes`:
```yaml
db_python_collect_check_codes: "{{ db_fact_check_codes + ['DB_READONLY_SQL_EXEC', 'DB_SCHEMA_METADATA_COLLECTION'] }}"
```

**备选方案**（不推荐）: 修改现有 Role 的三个断言 + Playbook 路由 + check_codes 列表 + callback schema。风险高，语义混乱。

### 4.3 Callback 闭环

```
AWX callback → CollectorService.handle_callback
  → 检测 business_domain == 'ai_schema'
  → AiSchemaSnapshotCallbackService.handle_result(db, run, callback_items)  ← NEW
  → 幂等 upsert ai_sql_schema_snapshot:
      成功: status=success, is_current=true, 旧版本 is_current=false
      失败: status=failed, error_message=..., is_current=false
  → 不进入 InspectionService/BatchCollectorService
```

### 4.4 固定元数据 SQL 模板 + 完整性校验

**首版只支持 PostgreSQL**。Oracle/SQL Server/MySQL 放入后续 Phase，不创建未启用的半成品模板。

**C7（修正后）**: PostgreSQL 固定元数据 SQL 模板与完整性校验。

**PostgreSQL**:
```sql
SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
```

**P1 — 采集完整性保证**:

Schema Collector 使用独立限制（远大于通用 SQL）:
```bash
AI_SCHEMA_RESULT_MAX_ROWS=20000
AI_SCHEMA_RESULT_MAX_BYTES=10485760  # 10MB
```

Callback 返回必须包含:
```json
{
  "total_rows": 1234,
  "returned_rows": 1234,
  "truncated": false
}
```

- `truncated=true` → status=`failed`, error_code=`RESULT_TRUNCATED`，不允许 success
- 若超过限制，按 schema 分批采集，不静默截断

**P1 — 不默认扫描所有业务 schema**:

Schema Policy 增加 `allowed_schemas` / `denied_schemas`:
```json
{
  "allowed_schemas": ["app", "reporting"],
  "denied_schemas": ["security", "credential"]
}
```

实例没有配置 `allowed_schemas` 时: Snapshot 可采集但 SQL Preview 默认关闭。管理员配置允许范围后再启用。

### 4.5 Preview/Execute 强绑定 — P0-3 修正

**P0-3 修正**: 原计划 Execute 步骤第 2 条 "该 snapshot 仍是 is_current=true → 拒绝" 写反了。

修正后的完整判断:
```text
Execute 时:
1. 读取 audit 绑定的 schema_snapshot_id
2. snapshot 不存在 → 409 "snapshot not found, re-preview required"
3. snapshot.status != 'success' → 409 "snapshot is not in success state"
4. snapshot.is_current != true → 409 "snapshot is no longer current, re-preview required"
5. snapshot.expires_at <= now() → 409 "snapshot expired, re-collect + re-preview required"
6. snapshot.snapshot_hash 与 Preview 时不匹配 → 409 "snapshot changed, re-preview required"
7. schema_policy_hash 与 Preview 时不匹配 → 409 "policy changed, re-preview required"
8. 全部通过后才创建 CollectorRun
```

`schema_policy_hash` 基于规范化安全策略内容计算:
```json
{
  "snapshot_hash": "...",
  "allowed_schemas": ["app"],
  "allowed_tables": ["app.orders"],
  "allowed_columns": {"app.orders": ["id", "status"]},
  "denied_columns": ["password_hash"],
  "policy_version": "2026-06-27-v1"
}
```
不能只对展示给 LLM 的 `schema_context` 文本计算（文本格式变化不一定代表安全策略变化）。

### 4.6 AiSchemaContextService

```python
class AiSchemaContextService:
    @staticmethod
    def trigger_collection(db, *, instance_id, requested_by) -> dict:
        """POST /collect → 创建 CollectorRun → 返回 202 + collector_run_id"""

    @staticmethod
    def get_snapshot_status(db, *, instance_id) -> dict:
        """GET / → 返回最新 snapshot 状态"""

    @staticmethod
    def build_schema_context(db, *, instance_id) -> dict:
        """从最新 is_current=true snapshot 构建 Dify inputs:
        {available, db_type_code, sql_dialect, schema_context(给LLM的摘要，实时构建),
         allowed_schemas, allowed_tables, allowed_columns, denied_columns,
         schema_snapshot_id, schema_policy_hash}
        available=false → 不可用于 Preview
        """
```

### 4.7 需新增/修改的文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `services/ai_schema_snapshot_service.py` | NEW | 采集触发 + 状态查询 |
| `services/ai_schema_snapshot_callback_service.py` | NEW | callback 落库 |
| `services/ai_schema_context_service.py` | NEW | build_schema_context |
| `services/check_item_builder_registry.py` | UPDATE | 新增 `_AiSchemaMetadataBuilder` (check_code=DB_SCHEMA_METADATA_COLLECTION) |
| `services/collector_service.py` | UPDATE | callback 分发 `ai_schema` |
| `api/ai.py` | UPDATE | schema-snapshot endpoints |
| `ansible-playbooks/.../dbops_collector_generic.yml` | UPDATE | 新增路由 + check_codes |
| `ansible-playbooks/.../roles/db_schema_metadata_collect/tasks/main.yml` | **NEW** | 独立 Role |

### 4.8 首版数据库支持范围 — P1 统一

- PostgreSQL: ✅ 首版支持
- Oracle: ⏳ 后续 Phase
- SQL Server: ⏳ 后续 Phase
- MySQL: ⏳ 后续 Phase

**capabilities 明确声明**:
```json
{
  "sql_supported_db_types": ["POSTGRESQL"]
}
```
Preview 拒绝 SQL Server/Oracle/MySQL → `422 unsupported_db_type`。AST 方言映射保留代码框架但测试不要求通过。

---

## 5. SQL 安全模型

### 6 层 defense
```
Layer 1: Dify Code 节点 JSON 解析+正则预检
Layer 2: SqlSafetyService 现有正则 (defense-in-depth)
Layer 3: SqlSafetyService.validate_with_ast (sqlglot) ← 权威
Layer 4: approved_sql 保存 (Dify SQL ≠ 审批执行 SQL)
Layer 5: Collector EE 客户端校验
Layer 6: 目标 DB 只读账户
```

### sqlglot 集成
`requirements.txt` 新增 `sqlglot>=25.0.0,<26.0.0`。

```python
@classmethod
def validate_with_ast(cls, sql_text, db_type_code, *, allowed_tables, allowed_columns,
                      denied_columns, max_rows=100) -> dict:
    """返回 {valid, approved_sql, approved_sql_hash, errors, warnings}"""
```

方言映射: postgresql→postgres, mssql/sqlserver→tsql, oracle→oracle, mysql→mysql（首版只要求 PostgreSQL 通过测试）。

### P0-4: generated_sql vs approved_sql

| 字段 | 写入时机 | 用途 |
|---|---|---|
| generated_sql | Preview(Dify 原始) | 审计追溯 |
| approved_sql | Preview(AST 重写后) | **执行时唯一使用** |

执行时验证 `SHA-256(approved_sql) == approved_sql_hash`。`schema_policy_hash` 变化 → 拒绝执行 → 要求重新 Preview。

### P1 — SELECT * 规则

首版明确拒绝:
1. `SELECT *` — 拒绝
2. `table.*` — 拒绝
3. 所有输出列必须显式声明
4. 所有物理表列引用必须能解析到 `allowed_columns`
5. 无法唯一解析的未限定列名直接拒绝

比自动展开 `*` 更安全，更容易审计。

### P1 — 敏感列掩码改进

两层防护:
- **第一层**: Schema Policy 中明确 `denied_columns`（优先在 Preview 阶段拒绝命中 SQL）
- **第二层**: 通用敏感字段 pattern 作为兜底（`password|secret|token|credential|key` + `phone|email|id_card|ssn`）

响应记录:
```json
{
  "columns": ["username", "email", "created_at"],
  "masked_columns": ["email"],
  "rows": [["test", "***", "2024-01-01"]],
  "truncated": false
}
```

---

## 6. Collector 集成 — business_domain=ai_sql

### 6.1 ai_sql 执行：内联构造 CollectorRun

`ai_sql` 不走 Registry/Builder（避免 `check_code='DB_READONLY_SQL_EXEC'` 的 Builder 冲突）。在 `AiSqlService.execute` 中直接构造 CollectorRun + CollectorRunItem（参考 `InspectionService.verify_sql` pattern）:

```python
# AiSqlService.execute:
run = CollectorRun(
    check_code="DB_READONLY_SQL_EXEC",
    business_domain="ai_sql",
    ...
)
db.add(run)
db.flush()

# 每个目标实例一个 item
item = CollectorRunItem(
    run_id=run.id,
    item_key=f"ai_sql:{audit_id}:{instance_id}",
    check_code="DB_READONLY_SQL_EXEC",
    executor_type="db_sql_readonly",
    business_domain="ai_sql",
    business_context=json.dumps({          # P1 — 标准化 business_context
        "audit_id": audit_id,
        "session_id": session_id,
    }),
    rule_config={"sql_text": approved_sql, ...},
    ...
)
```

### 6.2 business_context 标准化（P1）

不使用顶层零散字段，统一使用:
```json
{
  "business_domain": "ai_sql",
  "business_context": {
    "audit_id": 123,
    "session_id": 10
  }
}
```

Callback 只解析 `business_context` 对象。`session_id` 从 `audit_id` 反查数据库确认（以数据库记录为准，callback context 只用于定位，不用于授权）。

### 6.3 需要修改的文件

| 文件 | 改动 |
|---|---|
| `ansible-playbooks/.../dbops_collector_generic.yml:183` | `business_domain` 列表新增 `'ai_sql'` |
| `ansible-playbooks/.../db_sql_readonly_collect/tasks/main.yml:32` | `business_domain` 列表新增 `'ai_sql'` |
| `backend/.../services/ai_sql_callback_service.py` | **NEW**: callback 完成闭环 |
| `backend/.../services/collector_service.py:~1339` | callback 分发新增 `ai_sql` 分支 |

### 6.4 确认自定义字段保留到 callback

必须验证以下字段在 AWX callback payload 中不被字段白名单丢弃:
```text
audit_id        (→ ai_sql_audit.id)
session_id      (→ ai_sql_audit.session_id)
business_domain (→ 分发路由)
```
均放在 `business_context` JSON 内传递。

### 6.5 Callback 闭环
```
AWX callback → CollectorService.handle_callback
  → 检测 business_domain == 'ai_sql'
  → AiSqlCallbackService.handle_result(db, run, callback_items)
  → 条件 UPDATE（P0-6）ai_sql_audit (execution_status, row_count, duration_ms, completed_at)
  → 幂等写入 ai_chat_message(type=sql_result) (result_message_id 去重)
  → 不进入 InspectionService.save_callback_results
```

---

## 7. Chat 事务边界和幂等

### 关键设计

1. **`client_request_id` 只写在 user message**。Assistant message 的 `client_request_id=NULL`，通过 `parent_message_id` 关联
2. **部分唯一索引** `UNIQUE(session_id, client_request_id) WHERE role='user' AND client_request_id IS NOT NULL` — 用户消息幂等，assistant 不冲突
3. **并发 pending 约束** `UNIQUE(session_id) WHERE role='assistant' AND status='pending'` — 数据库级保护

### 发送消息流程（含租约机制 — P0-5）

```
事务 1:
  1. 校验 session 所有权（user_id）
  2. 幂等检查: SELECT WHERE session_id=? AND role='user' AND client_request_id=?
     已存在 → 返回已有 user+assistant 消息 → 200 OK
  3. 检查是否存在 pending assistant:
     SELECT WHERE session_id=? AND role='assistant' AND status='pending'
     存在 AND processing_expires_at > now() → 409 Conflict（正常处理中）
     存在 AND processing_expires_at <= now() → UPDATE status='stale', error_code='PROCESSING_LEASE_EXPIRED' → 继续
  4. 创建 user message (role=user, client_request_id=前端UUID, status=completed)
  5. 创建 assistant message (role=assistant, client_request_id=NULL, status=pending,
     processing_started_at=now(), processing_expires_at=now()+90s)
  6. COMMIT

事务外:
  7. 调用 Dify（不持有 DB 事务）
  8. 成功/失败 → 进入事务 2

事务 2:
  9. 更新 assistant message: content, status=completed/failed, dify_*, error_code
  10. 更新 dify_conversation_id（Dify 返回的）
  11. 更新 session.last_message_at + message_count
  12. COMMIT
```

### 启动清理
```sql
UPDATE dbops.ai_chat_message
SET status = 'stale',
    error_code = 'PROCESSING_LEASE_EXPIRED'
WHERE role = 'assistant'
  AND status = 'pending'
  AND processing_expires_at < now();
```
同样逻辑应用于巡检分析 pending 和 Schema Snapshot running 记录。

### Dify inputs 安全

```text
Dify user:          "dbops:{current_user.id}"
role:               来自 current_user.role（不接受前端传入）
locale:             来自 current_user.language，空值时默认 zh-CN（不接受前端传入）
current_page:       允许前端传入，但必须通过后端白名单验证
conversation_id:    只能从 ai_chat_session.dify_conversation_id 读取（不接受前端传入）
```

白名单: `ai_chat`, `inspection_report`, `instance_report`, `instance_detail`。

---

## 8. 巡检分析版本历史与并发锁（P0-4 两阶段发布）

### 重新分析流程（含事务锁 + 两阶段发布）

```text
POST /inspection/reports/{id}/ai-analysis {force: true}
  ↓
事务 1（SELECT ... FOR UPDATE）:
  1. 锁定 inspection_report 行（overall）或 inspection_instance_report 行（instance）
  2. 查询当前 is_current=true 记录
  3. 【关键】不修改旧记录！旧 ready/reviewed 版本继续 is_current=true
  4. 插入新记录 version=old_version+1, is_current=false, status=pending
  5. COMMIT
  ↓
事务外: 调用 Dify
  ↓
成功 → 事务 2（SELECT ... FOR UPDATE）:
  1. 锁定 report
  2. 旧 current → is_current=false, superseded_at=now()
  3. 新版本 → status=ready, is_current=true
  4. COMMIT

失败 → 事务 2:
  1. 新版本 → status=failed, is_current=false, error_code=..., error_message=...
  2. 旧版本继续 is_current=true（不受影响）
  3. COMMIT
```

**并发保护**: `SELECT ... FOR UPDATE`（PostgreSQL 行锁）保证两个并发 force 请求不会产生两个 `is_current=true` 记录。

### API

```text
POST /inspection/reports/{id}/ai-analysis {force:true}
GET  /inspection/reports/{id}/ai-analysis              → 返回 is_current=true
GET  /inspection/reports/{id}/ai-analysis/history      → 所有版本(version DESC)
POST /inspection/reports/{id}/ai-analysis/{aid}/review → 标记 reviewed(review_comment optional)
```

### reviewed 行为

- 同 `source_data_hash + workflow_version` + `reviewed`: 返回 reviewed 版本
- `source_data_hash` 已变化: 可创建新版本，旧 reviewed 版本保留为历史
- 同 hash 强制重跑 reviewed: 仅 admin

### 缓存键
`source_data_hash + workflow_version`（`workflow_version` 从 `DIFY_REPORT_WORKFLOW_VERSION` 配置读取）。

---

## 8b. DOCX 集成（指定 analysis_id + 固定免责声明）

### 端点

```http
POST /api/v1/inspection/reports/{report_id}/export?include_ai=true&analysis_id=123
POST /api/v1/inspection/reports/{report_id}/instances/{type}/{id}/export?include_ai=true
```

### analysis_id 规则 — P1 修正（404 代替 403）

- 传 `analysis_id` → 校验该 analysis 属于当前 report 且状态为 ready/reviewed
- 未传 → 使用当前 `is_current=true` 的 ready/reviewed 分析
- analysis_id 不属于 report → **404**（避免泄露该 analysis_id 是否存在）
- 分析不存在 → 400 "尚未生成 AI 分析"
- 和 Chat session、SQL audit 的资源归属策略一致

### 导出审计

DOCX 元数据中记录: `analysis_id`, `analysis_version`, `workflow_version` — 保证 DOCX 可追溯到具体 AI 分析版本。

### 固定免责声明（必须包含在 AI 章节末尾）

> 本章节由 AI 基于 DBOPS 巡检结果生成，仅用于辅助分析。健康等级、健康分数、异常状态以规则引擎结果为准。

---

## 9. 权限矩阵

| 功能 | viewer | operator | admin |
|---|---|---|---|
| 普通聊天 | ✅ | ✅ | ✅ |
| SQL Preview / Execute | ❌ | ✅ | ✅ |
| 查看 AI 分析 | ✅ | ✅ | ✅ |
| 生成 AI 分析 | ❌ | ✅ | ✅ |
| mark-reviewed / force override | ❌ | ❌ | ✅ |

所有目标实例操作需校验用户对 instance_id 的访问权限。

---

## 10. SQL 结果存储与截断策略

- `ai_chat_message.content`: 仅摘要 "查询完成，共返回 N 行"
- `ai_chat_message.metadata_json`: 仅 `{columns, row_count, duration_ms, audit_id, masked_columns, truncated, truncated_reason}`
- 完整 rows 不存入 Chat 消息/ai_sql_audit。从 `CollectorRunResult.raw_result` 按权限读取

```bash
AI_SQL_RESULT_MAX_ROWS=200          # 返回行数上限
AI_SQL_RESULT_MAX_COLUMNS=100       # 返回到数上限
AI_SQL_RESULT_MAX_CELL_CHARS=4000   # 单个单元格截断
AI_SQL_RESULT_MAX_BYTES=2097152     # 总响应体硬上限 (2MB)
```

返回前执行: 行数列数限制 → 单元格截断 → 敏感字段掩码 → 总字节数限制。

需确认: `CollectorRunResult.raw_result` 是否永久保存、是否存在清理任务、callback 是否已截断 max_rows。

---

## 11. 前端能力查询 + Dify 输入安全 + 响应规范 + 配置校验解耦

### 能力查询接口

```http
GET /api/v1/ai/capabilities
```

响应:
```json
{
  "chat_enabled": true,
  "sql_preview_enabled": false,
  "sql_execution_enabled": false,
  "report_analysis_enabled": true,
  "report_export_ai_enabled": false,
  "stream_enabled": false,
  "sql_supported_db_types": ["POSTGRESQL"]
}
```

前端根据能力隐藏/禁用对应 UI 元素。接口严禁返回 API Key、Dify URL、内部模型配置。

### P1 — 能力开关与配置校验解耦

```text
AI_CHAT_ENABLED=false        → 不要求 DIFY_CHAT_API_KEY
AI_SQL_PREVIEW_ENABLED=false → 不要求 DIFY_SQL_WORKFLOW_KEY
AI_REPORT_ANALYSIS_ENABLED=false → 不要求 DIFY_REPORT_WORKFLOW_KEY
```

配置校验按功能启用状态执行，否则只启用聊天时也可能因报告 Key 为空导致应用启动失败。

### Dify Chat inputs 安全

```text
Dify user:          "dbops:{current_user.id}"
role:               来自 current_user.role（不接受前端传入）
locale:             来自 current_user.language，空值时默认 zh-CN
current_page:       允许前端传入，但必须通过后端白名单验证
conversation_id:    只能从 ai_chat_session.dify_conversation_id 读取
```

### 响应包装规范

项目现有统一格式为 `{code: 0, data: ...}`（见 `request.js` 响应拦截器）。新 API 必须复用此规范。

错误状态码:
| 场景 | HTTP |
|---|---|
| 参数校验失败 | 422 |
| 会话正在生成 / Snapshot 过期或变化 | 409 |
| 无权限 | 403 |
| 资源不存在或不属于当前用户 | 404 |
| 功能开关关闭 | 503 |
| Dify 不可用 | 502 |
| Dify 超时 | 504 |
| Collector 正在执行 | 200/202（按现有规范） |
| SQL 方言不支持 | 422 |

### Markdown 安全
**首版: 纯文本 + `white-space: pre-wrap` CSS**。不用 `v-html`。后续如需 Markdown: `markdown-it`（禁用 HTML）+ `DOMPurify.sanitize()` + 链接协议白名单。

### 功能开关
```bash
AI_CHAT_ENABLED=true
AI_SQL_PREVIEW_ENABLED=false
AI_SQL_EXECUTION_ENABLED=false
AI_REPORT_ANALYSIS_ENABLED=false
AI_REPORT_EXPORT_AI_ENABLED=false
```

### .env
- 修改 `backend/.env.example`，不修改 `backend/.env`
- ❗Dangerous: Dify API Key 不应出现在任何 plan/代码/日志中
- 通用检测: `grep -RIlE --exclude='.env' --exclude='*.log' --exclude-dir='.git' "app-[A-Za-z0-9_-]{20,}" backend/ frontend/dist/`（只列文件名，不打印内容）

### 实例级权限
当前项目无实例级 RBAC。本阶段使用 `role + is_active` 校验，明确记录 "实例级 RBAC 延后到 Phase 3.7"。巡检报告 AI 分析复用报告现有权限判断（task_id 可追溯），不虚构不存在的权限表。

---

## 12. 文件变更清单（~60 文件）

### 后端新增 (25)
`db/` 8 个 SQL 文件（4 正向 + 4 回滚）, `models/ai.py`, `schemas/ai.py`, `services/dify_service.py`, `services/ai_chat_service.py`, `services/ai_schema_snapshot_service.py`, `services/ai_schema_snapshot_callback_service.py`, `services/ai_schema_context_service.py`, `services/ai_sql_service.py`, `services/ai_sql_callback_service.py`, `services/inspection_ai_context_service.py`, `services/inspection_ai_service.py`, `api/ai.py`, `tests/` 7 个测试文件

### 后端修改 (9)
`config.py`, `main.py`, `sql_safety_service.py`, `api/inspection.py`, `services/report_export_service.py`, `services/collector_service.py`, `services/check_item_builder_registry.py`, `requirements.txt`, `.env.example`

### Playbook 新增+修改 (3)
`dbops_collector_generic.yml` (UPDATE), `db_sql_readonly_collect/tasks/main.yml` (UPDATE), `roles/db_schema_metadata_collect/tasks/main.yml` (**NEW**)

### 前端新增 (10)
`api/ai.ts`, `types/ai.ts`, `views/ai/Chat.vue`, `components/ai/AiMessageList.vue`, `AiMessageBubble.vue`, `AiComposer.vue`, `AiInstanceSelector.vue`, `AiSqlPreviewCard.vue`, `AiSqlResultTable.vue`, `InspectionAiAnalysisCard.vue`

### 前端修改 (5)
`router/index.ts`, `views/Layout.vue`, `types/api.ts`, `views/inspection/ReportDetail.vue`, `views/inspection/InstanceReport.vue`

### 文档 (4)
`.env.example`, `scripts/ai/verify.sh`, `docs/10-module-map.md`, `docs/schema-snapshot.md`

---

## 13. 测试矩阵（~105 用例）

### SqlSafetyService AST (28)
合法 SELECT/WITH/JOIN/子查询, 拒绝 DELETE/UPDATE/INSERT/DROP/TRUNCATE/多语句, 拒绝 SELECT INTO/FOR UPDATE/数据修改CTE, 拒绝 pg_sleep/dblink/OPENROWSET/OPENQUERY/Oracle DB link/INTO OUTFILE, 拒绝 SELECT */table.*, allowed_tables外/denied_columns拒绝, CTE别名不误判/无LIMIT自动补充/超500行收敛/NUL字符, schema_policy_hash变化拒绝执行, 未限定列名拒绝

### Schema Snapshot (8)
POST collect 返回 202（不假装同步完成）、ai_schema callback 成功生成 Snapshot、callback 重复到达保持幂等、Snapshot 过期后 Preview 被拒绝、Snapshot 在 Preview 后变化 Execute 返回 409、首版只支持 PostgreSQL、truncated=true 不允许 success、Snapshot running 超时→failed

### AiSqlService (13)
preview 合法/preview need_execute=false/preview schema_context_unavailable/preview snapshot_expired/Dify非法JSON/execute只接受audit_id/跨用户/approved_sql_hash不一致/二次校验失败/schema_policy_hash变化/Collector成功/Collector timeout/Collector失败

### AiSqlCallbackService (6)
callback正常回写/callback创建sql_result消息/callback重复到达幂等/callback不进InspectionService/用户不轮询audit仍完成/business_context字段(包括audit_id)不丢失

### InspectionAiService (17)
整体/单实例分析成功/workflow failed/analysis_json非法/confidence越界/非法risk_level/hash+version相同缓存/hash变化重分析/force=true/旧版本is_current=false/AI不修改inspection_result/AI不修改health_level/403/普通用户force=true reviewed→403/两个并发force不会产生两个current版本/analysis_id不属于report时DOCX导出404/Dify故障旧版本仍current

### Chat (12)
创建会话/发送Mock/发送Dify(conversation_id复用)/用户隔离/消息历史/空query拒绝/user消息幂等(client_request_id)/同session并发发送第二个请求→409/pending超时→stale→允许新请求/启动清理stale/前端role/locale/conversation_id被忽略

### DOCX (6)
include_ai=false原格式/include_ai=true含AI/analysis_id指定版本/分析不存在400/固定免责声明/导出审计含analysis_id+version+workflow_version

### 安全+基础设施 (11)
API Key不进bundle/不进日志/密码不发Dify/schema_context无敏感数据/session隔离/sql_audit隔离/ai_analysis隔离/SQL不绕过preview/Markdown XSS/功能关闭时capabilities与UI一致/配置校验按功能启用解耦

### SQL Result (4)
超最大字节截断/敏感列掩码/cell截断/SQLAlchemy新模型测试DB正确注册

**总计: ~105 用例**

---

## 14. Commit 顺序（~32 Commits）

### Phase 3.6A: Chat MVP
- C1: config（含 5 个独立开关 + DIFY_* + 独立超时 + **配置按功能启用解耦校验**）+ dify_service（lifespan Client）+ **Capabilities 后端契约** + 单测
- C2: DDL phase3_6a + rollback 文件 + models/ai.py（chat 部分，含 metadata_json 映射 + lease 字段）+ schemas/ai.py（chat 部分）
- C3: ai_chat_service（幂等/并发约束/租约机制/事务边界）+ Chat API + capabilities endpoint
- C4: 前端 api/ai.ts + types/ai.ts + router + menu + **Capabilities 初始化 + 菜单按钮灰度**（一次到位，避免后期重构）
- C5: Chat.vue + 消息组件（纯文本渲染，`white-space: pre-wrap`）

### Phase 3.6B0: Schema Snapshot
- C6: DDL phase3_6b0 + rollback + Model + Schema（含 nullable + CHECK + database_name NOT NULL + allowed_schemas）
- C7: PostgreSQL 固定元数据 SQL 模板与完整性校验（truncated/total_rows/returned_rows 检查）
- C8: `_AiSchemaMetadataBuilder`（check_code=DB_SCHEMA_METADATA_COLLECTION, business_domain=ai_schema）+ **独立 Role** `db_schema_metadata_collect` + Playbook 路由更新
- C9: AiSchemaSnapshotCallbackService + CollectorService dispatch + truncated 拒绝 + 幂等测试
- C10: Schema Snapshot API（POST collect / GET status）+ AiSchemaContextService + TTL/hash + 两阶段 is_current 切换

### Phase 3.6B1: SQL Preview
- C11: requirements.txt + sqlglot + validate_with_ast + SELECT * 拒绝 + 28 安全测试
- C12: DDL phase3_6b + rollback + ai_sql_audit Model+Schema（含 preview/execution split + not_requested 状态 + 条件 UPDATE 状态转换）
- C13: ai_sql_service.preview + /ai/sql/preview API（含 schema_snapshot 检查 + allowed_schemas 过滤 + PostgreSQL-only 验证）+ 13 测试
- C14: 前端 AiInstanceSelector + AiSqlPreviewCard
- C15: Chat 集成 SQL preview 模式

### Phase 3.6B2: SQL Execute
- C16: Playbook business_domain 列表 + `'ai_sql'`（2 文件更新）
- C17: AiSqlService.execute（内联构造 CollectorRun + business_context 标准化）+ CollectorService ai_sql dispatch
- C18: ai_sql_callback_service + callback 闭环（条件 UPDATE 状态转换 + business_context 解析）+ 幂等测试
- C19: /ai/sql/execute + /ai/sql/executions/{id} API（含 P0-3 修正的 7 步 Execute 检查）
- C20: 前端 AiSqlResultTable + running/timeout/error UI + 敏感列掩码展示
- C21: readonly_sql/auto 模式 + 重复点击防抖

### Phase 3.6C1: Inspection AI Analysis
- C22: DDL phase3_6c + rollback + Model + Schema（含两阶段发布 CHECK + review_comment + lease 字段）+ FOR UPDATE locking
- C23: inspection_ai_context_service + hash/cache/workflow_version
- C24: inspection_ai_service + 两阶段发布 + 整体报告 API + 版本历史 + pending 超时恢复
- C25: 单实例 API + review endpoint
- C26: 前端 AiAnalysisCard + ReportDetail/InstanceReport 更新

### Phase 3.6C2: DOCX AI
- C27: DOCX include_ai=true + analysis_id（404 代替 403）+ _write_ai_analysis（含免责声明）+ 审计元数据

### 收尾
- C28: 安全回归 + 日志脱敏 + 全量 ~105 测试
- C29: verify.sh 更新（`pytest -q # ~105 tests`）+ .env.example + docs
- C30: API Key 泄漏通用检查（`grep -RIlE` 只列文件名）+ 轮换提醒
- C31: DDL 幂等验证（ON_ERROR_STOP=1）+ 回滚安全检查（正向 4 + 回滚 4 = 8 文件）
- C32: 启动时 stale 清理（chat pending + analysis pending + snapshot running）

---

## 15. 环境启用顺序

```
Phase A:      AI_CHAT_ENABLED=true, 其他 false
+B0:         AI_SQL_PREVIEW_ENABLED=false (schema 准备中)
+B1 Preview:  AI_SQL_PREVIEW_ENABLED=true, AI_SQL_EXECUTION_ENABLED=false, sql_supported_db_types=["POSTGRESQL"]
+B2 Execute:  AI_SQL_EXECUTION_ENABLED=true (安全测试通过后)
+C1 Analysis: AI_REPORT_ANALYSIS_ENABLED=true
+C2 DOCX:     AI_REPORT_EXPORT_AI_ENABLED=true
```

---

## 16. 风险与回滚

| 风险 | 等级 | 缓解 | 回滚 |
|---|---|---|---|
| SQL 执行 | CRITICAL | 6层defense + AI_SQL_EXECUTION_ENABLED=false默认 | 关闭开关 |
| Dify 故障 | HIGH | AI_PROVIDER=mock 一键切换 | 切Mock，数据不丢 |
| Collector ai_sql 被拒 | HIGH | 修改playbook business_domain 白名单 | 回滚playbook |
| callback 无闭环 | HIGH | 新增 AiSqlCallbackService + collector_service dispatch | 移除dispatch |
| API Key 泄露 | HIGH | .env only + 日志脱敏 + bundle检查 | 轮换Key |
| Chat pending 永久锁死 | HIGH | 租约机制 + 启动清理 stale | 手动 UPDATE stale |
| 巡检分析丢失 current | HIGH | 两阶段发布（新 ready 后才切换） | 手动恢复旧 current |
| Schema 采集不完整 | HIGH | truncated 检查 + 独立 max_rows=20000 | 重新采集 |
| DOCX | MEDIUM | include_ai=false 默认 | 不传参数 |
| DDL | LOW | 按Phase拆分+独立回滚 | 逐表回滚 |

---

## 17. DDL 安全与回滚规范

- 所有正向 DDL 使用 `BEGIN; ... COMMIT;` 包裹
- 执行使用 `psql -v ON_ERROR_STOP=1 -f <file>`
- 回滚脚本标注 `❗Dangerous` 并列出影响行数检查 SQL
- 部署失败时不自动执行破坏性回滚 — 需先人工确认数据量
- 8 个 SQL 文件: 4 正向 + 4 回滚

---

## 18. 本轮不实现

RAG/SSE/文件上传/打字流/Dify KB管理/AI自动执行SQL/AI修改规则引擎/后台自动采集schema(手动触发)/多provider/AI审计独立页面/Oracle/SQL Server/MySQL Schema Snapshot（仅 PostgreSQL）

---

## 19. 关键状态机汇总（P0-4/P0-5/P0-6 修正后）

### Chat Message（P0-5 租约）
```
pending → completed
       ├→ failed
       └→ stale (processing_expires_at 过期)
```

### Schema Snapshot（P0-4 两阶段发布 + 超时恢复）
```
pending → running → success  (→ is_current=true, 旧 success → is_current=false)
                  ├→ failed  (is_current=false, 旧 current 保持不变)
                  ├→ unavailable (is_current=false)
                  └→ failed [timeout] (超过 AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS)
```

### SQL Audit Execution（P0-6 条件 UPDATE）
```
Preview: passed / rejected
Execution: not_requested → pending → running → success
                                            ├→ failed
                                            ├→ timeout
                                            └→ cancelled
```
状态转换由 `UPDATE ... WHERE execution_status IN (...)` 条件更新实现。
数据库 CHECK 只约束枚举值。

### Inspection AI Analysis（P0-4 两阶段发布）
```
pending → ready  (→ is_current=true, 旧 current → is_current=false, superseded_at=now())
       └→ failed (is_current=false, 旧 current 保持不变)
       └→ failed [timeout] (超过 DIFY_REPORT_TIMEOUT_SECONDS + 30)
ready → reviewed
```

---

## 20. 验证命令

```bash
cd backend && pytest -q                                   # ~105 tests
cd backend && pytest tests/test_sql_safety_service.py -q  # 28 安全用例
cd frontend && npm run type-check && npm run build         # 前端
bash scripts/ai/verify.sh                                  # 统一验证
```

**API Key 泄漏扫描**（只打印文件名，不打印匹配内容，避免二次泄露）:
```bash
# 排除 .env、.git、node_modules、__pycache__、测试快照
if grep -RIlE \
  --exclude='.env' \
  --exclude='*.log' \
  --exclude-dir='.git' \
  --exclude-dir='node_modules' \
  --exclude-dir='__pycache__' \
  --exclude-dir='.pytest_cache' \
  "app-[A-Za-z0-9_-]{20,}" \
  backend/ frontend/dist/ 2>/dev/null; then
    echo "ERROR: Possible Dify API Key leak detected in above files"
    exit 1
fi
echo "OK: No Dify API Key pattern detected in committed code"
```
