# Phase 3.6 AI Copilot — 完整实施计划（v5，2026-07-06 第四轮审查修正）

**Source**: `/home/lisiyang/aiplan/claude-code-plan-ai-phase3_6-complete.md`
**Date**: 2026-06-27（原始） / 2026-07-06（v5 修正）
**Branch**: feature/phase-3.6-ai-copilot
**Complexity**: LARGE（6 个 Phase × ~32 Commits × ~60 文件变更）
**Review**: 四轮审查 — v4 6 P0 + 15 P1 + v5 8 P0 + 7 P1 修正
**Status**: ✅ 可进入编码

---

## 0. 当前真实状态（2026-07-06）

### 0.0 已完成

| Phase | 内容 | 状态 |
|-------|------|------|
| C1-C5 | Chat MVP（DifyService + Chat DDL/Models/Schemas + Chat Service/API + Frontend 入口 + Chat UI） | ✅ 已 commit |
| C6-C10 | Schema Snapshot（DDL + SQL 模板 + Builder + Callback + API + ContextService） | ✅ 已 commit |
| C11 | sqlglot + SqlSafetyService.validate_with_ast + 10 规则 + 38 测试 | ✅ 已 commit |
| C12-C13 | SQL Preview（ai_sql_audit DDL + AiSqlPreviewService + API + Layer1 precheck + Frontend SqlPreview.vue） | ✅ 已 commit |
| C14 | SQL Execute（AiSqlExecuteService + AiSqlCallbackService + API + Frontend） | ✅ 已 commit |
| C15 | Chat 集成收尾（ChatMessageBubble sql_result 卡片 + SqlPreview audit 详情 + vitest + 收尾文档） | ✅ 已 commit |

### 0.1 当前剩余主线

```text
1. C16：实例绑定 Chat SQL Copilot E2E 收尾
   - Chat.vue(boundInstanceId) 主入口
   - SQL Preview 卡片
   - SQL Execute
   - AWX callback
   - sql_result 卡片
   - PostgreSQL / Oracle / SQL Server 三库 E2E 验证

2. Phase 3.6C：Inspection AI Analysis
   - 202 + BackgroundTasks
   - 版本历史
   - review
   - DOCX include_ai

3. 收尾
   - 安全回归
   - DDL 验证
   - API Key 泄漏扫描
   - docs / runbook / module-map 更新
```

> **注意**：SQL Execute 基础链路已完成（C14），本阶段重点是 Chat 绑定实例入口和 E2E 闭环。不再有"C17-C20 待开发"等旧描述。

---

## 0A. 真实仓库现状核对 + 关键代码证据

### 0A.1 数据库迁移方式
**纯 SQL 文件**在 `backend/db/`。无 Alembic。
→ **按 Phase 拆分 DDL**：共 8 个文件（4 正向 + 4 回滚）：

```text
dbops_phase3_6a_ai_chat.sql          / rollback_phase3_6a_ai_chat.sql
dbops_phase3_6b0_schema_snapshot.sql  / rollback_phase3_6b0_schema_snapshot.sql
dbops_phase3_6b_ai_sql.sql            / rollback_phase3_6b_ai_sql.sql
dbops_phase3_6c_inspection_ai.sql     / rollback_phase3_6c_inspection_ai.sql
```

### 0A.2 SQLAlchemy
**纯同步**（`database.py:12-21`）。`sessionmaker(autocommit=False, autoflush=False)`，`get_db()` 返回同步 `Session`。
→ DifyService 使用 `httpx.Client`（同步，连接池复用）。禁止混用同步/异步数据库会话。

### 0A.3 AI Router prefix
**无 AI Router**。现有路由 prefix=`/api/v1`（`main.py:67-75`）。
→ 新增 `app.include_router(ai.router, prefix="/api/v1", tags=["ai"])`。

### 0A.4 DB_READONLY_SQL_EXEC
**异步 callback**（`inspection_service.py:404-587`）：创建 CollectorRun → AWX launch → callback → handle_callback。
→ ai/sql/execute 复用此链路。callback 必须回写 `ai_sql_audit`。

### 0A.5 schema_context
**不存在**。无表/字段元数据。
→ **必须新增 Phase 3.6B0（Schema Snapshot + Schema Policy）**，否则 SQL Preview 大多数请求只能返回 `schema_context_unavailable`。

### 0A.6 SqlSafetyService
**已有正则实现**（`sql_safety_service.py`，241 行），不是 AST。
→ 引入 `sqlglot` 为权威 AST 校验，保留正则为 defense-in-depth。

### 0A.7 巡检报告/DOCX
已全部对照代码确认文件路径和行号正确。

### 0A.8 前端规范
已确认：路由延迟加载、菜单在 `Layout.vue:131-207` 内联、API 均在 `assets.ts` 的 `assetsApi` 对象中。

### 0A.9 关键代码证据（P0 审查新增）

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

## 3b. Dify 平台配置与 I/O 契约

### 3b.1 平台操作原则

```text
Dify 平台配置说明：

1. Dify 平台中的 workflow、prompt、Code 节点由人工手动更新和发布，不纳入代码实施步骤。
2. 后端代码只依赖 Dify inputs / outputs 契约。
3. inputs / outputs 字段名、workflow_version、错误处理规则必须写入 plan，并纳入自动化测试。
4. 后端不得依赖 Dify 页面上的节点名称，只依赖 API 返回字段。
5. Dify workflow 发布由人工完成，后端通过 workflow_version 判断当前输出契约。
```

### 3b.2 dbops-sql-generator I/O 契约

**Inputs**（后端 → Dify）:
```json
{
  "user_question": "查询最近 10 条订单",
  "db_type_code": "POSTGRESQL | ORACLE | MSSQL",
  "sql_dialect": "PostgreSQL | Oracle | SQL Server",
  "schema_context": "...",
  "allowed_tables": "[\"app.orders\", \"app.customers\"]",
  "allowed_columns_json": "{\"app.orders\":[\"id\",\"order_no\",\"status\",\"amount\",\"created_at\"]}",
  "denied_columns_json": "[\"password_hash\",\"secret_key\",\"token\",\"api_key\",\"credential\"]",
  "max_rows": "100",
  "instance_id": "123",
  "instance_name": "...",
  "target_database": "...",
  "target_ip": "...",
  "target_port": "..."
}
```

**Outputs**（Dify → 后端，固定字段名）:
```text
need_execute  boolean  — 是否生成 SQL
sql_text      string   — Dify 生成的候选 SQL
explain       string   — 自然语言解释
risk_level    string   — low / medium / high / rejected
reason        string   — 生成决策原因
```

### 3b.3 dbops-report-analyzer I/O 契约

**Inputs**（后端 → Dify）:
```json
{
  "analysis_scope": "overall | instance",
  "report_id": "123",
  "instance_report_id": "456",
  "report_code": "...",
  "health_level": "healthy | warning | critical | unknown",
  "health_score": "85",
  "summary_json": "{}",
  "abnormal_results_json": "[]",
  "failed_results_json": "[]",
  "top_risks_json": "[]",
  "target_snapshot_json": "{}",
  "locale": "zh-CN",
  "max_recommendations": "8",
  "generated_by": "dbops"
}
```

**Outputs**（Dify → 后端，固定字段名）:
```text
summary                string   — 分析摘要
root_causes_json        string   — 根因分析 JSON
recommendations_json   string   — 建议 JSON
risk_level             string   — low / medium / high / critical / unknown
confidence             number   — 置信度 0~1
need_manual_review     boolean  — 是否需要人工复核
manual_review_reason   string   — 复核原因
analysis_json          string   — 完整分析 JSON
```

### 3b.4 后端字段校验规则

**dbops-sql-generator**（非法输入一律 rejected，不收敛）:
```text
1. need_execute / sql_text / risk_level 字段缺失或类型错误 → preview rejected
2. risk_level 非 low / medium / high / rejected → preview rejected
3. rejected preview 仍写 ai_sql_audit（preview_safety_status='rejected'）
4. explain / reason 超长字段截断入库
```

**dbops-report-analyzer**（非法输入收敛为安全默认值）:
```text
1. Dify 返回字段缺失或类型错误 → 写 failed 记录，不直接 500
2. risk_level 非 low / medium / high / critical / unknown → 收敛为 unknown
3. confidence 不在 0~1 → 收敛为 0.5
4. need_manual_review 非 boolean → 收敛为 true
5. Dify 输出非法 JSON（root_causes_json / recommendations_json / analysis_json）→ 返回兜底分析，不直接 500
6. 超长字段截断入库，并记录 truncated=true / truncated_fields
```

### 3b.5 外部配置依赖

以下 Dify workflow 配置变更由人工在 Dify 平台完成，不进代码实施步骤：

```text
1. dbops-sql-generator workflow 必须支持：
   - allowed_columns_json
   - sql_dialect
   - instance_id
   - schema_context
   - max_rows 1~500
   - risk_level 非法 → rejected

2. dbops-report-analyzer workflow 必须支持：
   - health_level
   - failed_results_json
   - abnormal_results_json
   - top_risks_json
   - max_recommendations

3. Dify workflow 发布由人工完成。
4. 后端通过 workflow_version 判断当前输出契约。
```

### 3b.6 workflow_version 配置

```bash
DIFY_SQL_WORKFLOW_VERSION=2026-07-06-v1
DIFY_REPORT_WORKFLOW_VERSION=2026-07-06-v1
```

写入位置：
```text
sql_workflow_version  → ai_sql_audit.sql_workflow_version（每次 Preview 写入）
report workflow_version → inspection_ai_analysis.workflow_version（每次分析写入）
```

缓存规则：
```text
source_data_hash + workflow_version 共同决定 report analysis 缓存是否命中。
workflow_version 变化 → 视为 Dify prompt/逻辑已变更 → 强制重新分析。
```

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

**C16 同步支持 PostgreSQL + Oracle + SQL Server**。MySQL 放入后续 Phase。

**C7（修正后）**: 三种数据库的固定元数据 SQL 模板与完整性校验。

**PostgreSQL**:
```sql
SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
```

**Oracle** (`ALL_TAB_COLUMNS`):
```sql
SELECT owner AS table_schema, table_name, column_name, data_type, nullable, column_id AS ordinal_position
FROM all_tab_columns
WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'WMSYS', 'MDSYS', 'CTXSYS', 'ORDSYS', 'DBSNMP')
ORDER BY owner, table_name, column_id
```

**SQL Server** (`INFORMATION_SCHEMA.COLUMNS`):
```sql
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
```

**`_AiSchemaMetadataBuilder` 按 `db_type_code` 分发模板**（`check_item_builder_registry.py`）:
```python
# C16 修正：根据 db_type_code 选择 SQL 模板
_SCHEMA_SQL_TEMPLATES = {
    "POSTGRESQL": "SELECT table_schema, table_name, ... FROM information_schema.columns ...",
    "ORACLE": "SELECT owner AS table_schema, ... FROM all_tab_columns ...",
    "MSSQL": "SELECT TABLE_SCHEMA, ... FROM INFORMATION_SCHEMA.COLUMNS ...",
}
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

### 4.8 数据库支持范围 — C16 同步支持三种

- PostgreSQL: ✅ C16 支持
- Oracle: ✅ C16 支持
- SQL Server: ✅ C16 支持
- MySQL: ⏳ 后续 Phase

**capabilities 明确声明**:
```json
{
  "sql_supported_db_types": ["POSTGRESQL", "ORACLE", "MSSQL"]
}
```

> **2026-07-03 修正**：Oracle/SQL Server 从"⏳ 后续 Phase"提到 C16 同步支持。基础设施（Collector 链路、DB_READONLY_SQL_EXEC、AWX callback、sqlglot 方言映射）已全部就绪，增量只有 Schema Snapshot SQL 模板（Oracle `ALL_TAB_COLUMNS` / SQL Server `INFORMATION_SCHEMA.COLUMNS`）+ `_AiSchemaMetadataBuilder` 按 `db_type_code` 分发 + sqlglot 方言测试通过。

AST 方言映射：postgresql→postgres, mssql/sqlserver→tsql, oracle→oracle, mysql→mysql。C16 要求 PostgreSQL/Oracle/SQL Server 三种方言的 `validate_with_ast` 测试全部通过。

---

## 4A. Object Metadata Snapshot（Phase 3.6B0 C16-F3 增量）

> **设计文档**：`.claude/plans/abundant-beaming-hamster.md`（~1000 行完整设计）
> **实施 plan**：`.claude/plans/phase-3-6-progress-2026-07-06-c16-f3.md`
> **状态**：C16-F3 commit 1（DDL/Builder/Ansible `93499a1` + ansible-playbooks `000854e`）+ commit 2（运行时层 `6e071e9`）已完成并推送；commit 3（测试 + 文档 + 记忆 + 验证）待新会话执行。

### 4A.1 目标

在 Schema Snapshot（C6–C10）补 DDL 维度的元数据：让 AI SQL 生成上下文除了"列结构"外，还能拿到"对象 DDL（CREATE TABLE / VIEW / INDEX / FUNCTION / CONSTRAINT）"，从而让 Dify 生成更准确的引用、JOIN 条件、索引选择。

### 4A.2 与 C8 Schema Snapshot 的差异

| 维度 | Schema Snapshot (C8) | Object Metadata Snapshot (F3) |
|---|---|---|
| 概念 | column rows（columns 名/类型/约束） | object DDL（CREATE TABLE/VIEW/INDEX/FUNCTION 文本） |
| 数据量 | 数千行级 | 数十 MB 级（DDL 全文） |
| 落表 | `ai_schema_snapshot` | `ai_object_metadata_snapshot`（独立表） |
| 落库粒度 | 整个 schema | 单 schema_name（partial unique 加 schema_name 维度） |
| 截断策略 | 不截断（行级数据） | **1MB DDL 截断**（callback service 兜底，`error_code='TRUNCATED'`） |
| SHA-256 | `snapshot_hash` | `object_ddl_sha256` + `snapshot_hash` |
| Dify 注入 | 全量 | **8000 字符 preview**（避免 token 超限） |
| DB 方言 | PostgreSQL + Oracle + SQL Server（C16 三方言） | **PostgreSQL only**（首版；三方言合并 C16-F0） |
| Capability flag | `AI_SQL_PREVIEW_ENABLED` | 复用（不新增 flag） |
| Builder | `_AiSchemaMetadataBuilder` (check_code=`DB_SCHEMA_METADATA_COLLECTION`) | `_AiObjectMetadataBuilder` (check_code=`DB_OBJECT_METADATA`) |
| Callback 路径 | `business_domain='ai_schema'` | `business_domain='ai_object_metadata'` |
| Run type | `ai_schema` | `ai_object_metadata` |
| Ansible role | `db_schema_metadata_collect` | `db_object_metadata_collect`（镜像结构，hardcode `max_bytes=1048576`、`phase='3.6B0.F3'`） |

### 4A.3 SQL 模板结构（`pg_object_metadata.sql`）

5 段 UNION ALL：

1. **table** — `pg_catalog.pg_class` JOIN `pg_namespace` JOIN `pg_description`，过滤 `relkind IN ('r', 'p')`
2. **view** — `relkind = 'v'`
3. **materialized_view** — `relkind = 'm'`（首版跳过，C16-F0 时按需激活）
4. **index** — `relkind = 'i'` JOIN `pg_index`
5. **function / procedure** — `pg_proc` JOIN `pg_namespace`
6. **constraint** — `pg_constraint` JOIN `pg_class`

每段输出统一列：`object_type, schema_name, object_name, ddl_text, comment`。`ddl_text` 在 callback service 内做 1MB 截断。

### 4A.4 API 端点（4 个）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/ai/sql/object-metadata/{instance_id}/collect` | 触发采集（202 + collector_run_id） |
| GET | `/api/v1/ai/sql/object-metadata/{instance_id}` | 最新 snapshot（任意状态，UI 轮询用） |
| GET | `/api/v1/ai/sql/object-metadata/{instance_id}/history` | 历史列表（分页 limit=50 默认） |
| GET | `/api/v1/ai/sql/object-metadata/{instance_id}/context` | 已发布 snapshot（is_current + success + 未过期） |

异常映射（与 Schema Snapshot 同模式）：
- 404 → `InstanceNotFoundError`
- 409 → `AiObjectMetadataAlreadyRunning`
- 422 → `UnsupportedDbTypeError`（首版仅 PG）
- 502 → `AwxLaunchError`
- 503 → `FeatureDisabledError`（复用 `AI_SQL_PREVIEW_ENABLED` gate）

### 4A.5 Schema Context 集成

`AiSchemaContextService.build_schema_context` 返回 dict 加 `object_metadata` 字段（lazy import `AiObjectMetadataSnapshotService` + try/except 兜底）：

```python
"object_metadata": {
    "available": True/False,
    "object_ddl_text_preview": "<前 8000 字符>",
    "object_ddl_sha256": "<sha256 hex>",
    "table_count": int,
    "view_count": int,
    "index_count": int,
    "function_count": int,
    "total_object_count": int,
    "snapshot_id": int,
    "snapshot_hash": "<sha256 hex>",
    "published_at": isoformat,
}
```

`available=False` 时返回 `{"available": False, "reason": "no_snapshot"|"snapshot_not_current"|"snapshot_expired"|"snapshot_not_success"}`，Dify inputs 注入跳过该键。

### 4A.6 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 编号冲突 | docs §7 F-list 追加 F13 | F3 编号已被 "前端 sql_preview_link" 占用 |
| 提交方式 | 拆 3 commit（DDL/Builder + 运行时 + 测试/文档） | ~3000 行单一 commit 风险高 |
| Partial unique | 加 schema_name 维度 | DDL 概念上需 schema 粒度（与 C8 不同） |
| 1MB 截断 | callback service 兜底 | 避免 DDL 文本超 TOAST（PostgreSQL 单字段 ~1GB 但性能差） |
| 8000 字符 preview | context service 截断 | 避免 Dify sql-generator inputs 超 token |
| TTL | 24h（`AI_OBJECT_METADATA_TTL_HOURS`） | 与 C8 一致 |
| Cleanup | startup hook + 10 min 超时 | 与 C10 同模式；防 staging 永久卡住 |
| Status | 5 态机 `pending/running/success/failed/unavailable` | 与 C8 一致 |
| Publish | 两阶段（is_current=true + demote 旧） | 与 C8 一致 |

### 4A.7 Rollback（按 commit 倒序）

```bash
# commit 3 失败（仅 docs + tests）
git revert <commit-3-sha> --no-edit && git push

# commit 2 失败（业务逻辑）
git revert <commit-2-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -c \
  "UPDATE dbops.ai_object_metadata_snapshot SET status='failed' WHERE status IN ('pending','running');"

# commit 1 失败（DDL + Builder + Ansible）
git revert <commit-1-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -f \
  /home/lisiyang/dbops/backend/db/rollback_phase3_6b0_ai_object_metadata.sql
```

---

## 4B. Schema/Object Snapshot 三方言合并（Phase 3.6B0 C16-F0 增量）

> **设计动机**：C8 Schema Snapshot + C16-F3 Object Metadata Snapshot 首版均仅 PostgreSQL；C16-F0 任务要求扩展到 PostgreSQL + Oracle + SQL Server（MySQL 暂不实现，按 §4.8 范围）。
> **状态**：C16-F0 commit 1（DDL/Builder/运行时层）已完成并推送；commit 2（测试 + 文档 + 记忆 + 验证）待新会话执行。

### 4B.1 目标

将 Schema Snapshot（C8，4 端点）+ Object Metadata Snapshot（C16-F3，4 端点）的 SQL 模板从 PostgreSQL 扩展到 PG + Oracle + SQL Server 三方言支持，**DDL 不变**（CHECK 约束本就含 4 个方言），仅补 SQL 模板文件 + Builder 分发 + Ansible assertion。

### 4B.2 设计原则

| 原则 | 落地 | 理由 |
|---|---|---|
| 后端 Builder 派发 | `_AiSchemaMetadataBuilder` / `_AiObjectMetadataBuilder` 共用 `_SQL_TEMPLATE_MAP` + `_load_sql_template` 统一入口 | 单点维护；新增方言 = 加 SQL 模板文件 + 加 map 项 |
| SQL 模板内联 | 模板 `app/services/ai/sql_templates/<dialect>/<name>.sql` 物理文件 | 与 C8/C16-F3 一致；ansible-playbooks 端不重复存 SQL |
| Ansible 端不存 SQL | 模板只由 backend 加载并通过 `rule_config.sql_text` 透传到 EE | EE 端执行与 backend 验证字节一致 |
| DDL 不变 | `CHECK (db_type_code IN ('POSTGRESQL','ORACLE','MSSQL','MYSQL'))` 已就位 | 不需新迁移；db_type_code 在 builder 入口 normalize 为大写 |
| db_type_code 接受值 | lowercase：`postgresql`/`postgres`/`oracle`/`mssql`/`sqlserver` | 与 C8 一致（pg → POSTGRESQL） |
| 不支持的方言 | 422 `UNSUPPORTED_DB_TYPE`（mysql/redis/mongodb/...） | 业务层校验；与 C8/C16-F3 同模式 |
| 无凭证 | 422 `CREDENTIAL_MISSING` | 与 C8/C16-F3 同模式 |
| MySQL 暂不实现 | `_SQL_TEMPLATE_MAP` 不含 `mysql` 键 → 直接 422 | 按 plan §4.8 + capabilities `sql_supported_db_types` |
| Ansible assertion | 5 个 dialect 接受值列表 `['postgresql', 'postgres', 'oracle', 'mssql', 'sqlserver']` | EE 端 pre-flight 校验，fail msg 显式提示 C16-F0 三方言 |
| 测距目标 | 4 端点 × 3 方言 = 12 happy path，1MB/8000 字符截断边界，UNSUPPORTED_DB_TYPE 错误码 | 84 unit tests（builder 36+36 + 12 边界/parametrize） |

### 4B.3 SQL 模板结构（4 个新模板）

#### 4B.3.1 Oracle Schema Columns（`ora_schema_columns.sql`）

6 列 `table_schema, table_name, column_name, data_type, is_nullable, ordinal_position`，从 `all_tab_columns` 查（information_schema 风格 schema_name 字段名）。系统 schema 黑名单：`SYS/SYSTEM/XDB/CTXSYS/MDSYS/OLAPSYS/ORDDATA/WMSYS/APEX_*` / `FLOWS_*`。`is_nullable` 用 `CASE WHEN nullable='Y' THEN 'YES' ELSE 'NO' END` 转换。

#### 4B.3.2 Oracle Object Metadata（`ora_object_metadata.sql`）

5 列 `object_type, schema_name, object_name, ddl_text, comment` × 6 UNION ALL segment：
1. **table** — `all_tab_columns` + `XMLAGG` 重建 DDL（避免 `DBMS_METADATA.GET_DDL` 的 `SELECT_CATALOG_ROLE` 依赖）
2. **view** — `all_views.TEXT`（view DDL 全文）
3. **materialized_view** — `all_mviews` + `DBMS_METADATA.GET_DDL`（无 `SELECT_CATALOG_ROLE` 也可）
4. **index** — `all_indexes` + `all_ind_columns`
5. **function / procedure** — `all_objects` + `all_source.LINE`/`all_source.TEXT` 重构 PL/SQL
6. **constraint** — `all_constraints` + `all_cons_columns`

每 segment 各自带 `WHERE owner NOT IN (...)` 黑名单。

#### 4B.3.3 SQL Server Schema Columns（`mssql_schema_columns.sql`）

6 列同 PG 模板，从 `sys.columns` + `sys.objects`（type IN 'U','V'）+ `sys.types` 查。`is_nullable` 用 `CASE WHEN c.is_nullable=1 THEN 'YES' ELSE 'NO' END` 转换。schema 过滤：排除 `sys`、`INFORMATION_SCHEMA`、`guest` 三个系统 schema。

#### 4B.3.4 SQL Server Object Metadata（`mssql_object_metadata.sql`）

5 列同 PG 模板 × 9 UNION ALL segment：
1. **table** — `sys.columns` + `STRING_AGG` 重建 DDL（绕过 TEXT/IMAGE 限制）
2. **view** — `sys.views` + `OBJECT_DEFINITION()`
3. **index** — `sys.indexes` + `sys.index_columns`
4. **function** — `sys.objects` type='FN' + `OBJECT_DEFINITION()`
5. **procedure** — `sys.objects` type='P' + `OBJECT_DEFINITION()`
6-9. **4 类 constraint** — `sys.key_constraints` / `sys.foreign_keys` / `sys.check_constraints` / `sys.default_constraints` + `OBJECT_DEFINITION()`

6 处用 `OBJECT_DEFINITION()`，对加密对象（`WITH ENCRYPTION`）/ 无 `VIEW DEFINITION` 返回 NULL → 落 `object_ddl_text=NULL`（callback 标记）。

### 4B.4 Builder 重构（`check_item_builder_registry.py`）

#### 4B.4.1 共用接口

```python
class _AiSchemaMetadataBuilder / _AiObjectMetadataBuilder:
    _SUPPORTED_DB_TYPES = frozenset({
        "postgresql", "postgres", "oracle", "mssql", "sqlserver",
    })
    _SQL_TEMPLATE_MAP: dict[str, tuple[str, str]] = {
        "postgresql": ("postgresql", "pg_schema_columns.sql"),
        "postgres":   ("postgresql", "pg_schema_columns.sql"),
        "oracle":     ("oracle",     "ora_schema_columns.sql"),
        "mssql":      ("mssql",      "mssql_schema_columns.sql"),
        "sqlserver":  ("mssql",      "mssql_schema_columns.sql"),
    }

    @classmethod
    def _load_sql_template(cls, db_type_code: str) -> tuple[str, str]:
        """返回 (sql_text, source_tag) 供 builder 入口调用"""
        normalized = db_type_code.strip().lower()
        if normalized not in cls._SUPPORTED_DB_TYPES:
            raise UnsupportedDbTypeError(...)
        if normalized not in cls._SQL_TEMPLATE_MAP:
            raise UnsupportedDbTypeError(...)  # mysql 暂不实现
        dialect, filename = cls._SQL_TEMPLATE_MAP[normalized]
        sql_text = importlib.resources.files("app.services.ai.sql_templates") \
            .joinpath(dialect, filename).read_text(encoding="utf-8")
        return sql_text, f"dbops.ai.sql_templates.{dialect}.{filename[:-4]}"
```

#### 4B.4.2 Builder 入口（伪代码）

```python
def build(self, db_type_code: str, ...) -> dict:
    sql_text, source_tag = self._load_sql_template(db_type_code)
    return {
        "check_code": "DB_SCHEMA_METADATA_COLLECTION",  # 或 "DB_OBJECT_METADATA"
        "executor_type": "db_sql_readonly",
        "rule_config": {
            "sql_text": sql_text,
            "timeout_seconds": 60,
            "max_rows": 10000,
            "max_bytes": 10485760,  # 10MB schema / 1048576 1MB object
            "source": source_tag,
            "phase": "3.6B0.F0",  # 或 "3.6B0.F3"
        },
    }
```

### 4B.5 collector_service 注册修复（C16-F3 漏注册 bug）

`backend/app/services/collector_service.py` 修 C16-F3 漏注册 bug：

```python
# _check_definition_defaults（line 188-194）
_DEFAULT_TASK_TYPE_REGISTRY["DB_OBJECT_METADATA"] = TaskType.AI_OBJECT_METADATA

# reachability gating set（line 1671）
_REACHABILITY_GATED_CHECKS = frozenset({
    "DB_SCHEMA_METADATA_COLLECTION",
    "DB_OBJECT_METADATA",  # 修 C16-F3 漏注册
})
```

**影响**：C16-F3 commit 2 已合并，但 `_check_definition_defaults` 没注册 → `DB_OBJECT_METADATA` 会 fallthrough 到 `PORT_CHECK` 默认 → collector 跳过 instance-level reachability 检查。本次 commit 修。

### 4B.6 ansible-playbooks 端（2 个 role 同步）

```yaml
# ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml
# ansible-playbooks/playbooks/roles/db_object_metadata_collect/tasks/main.yml
- name: Validate ... item fields
  ansible.builtin.assert:
    that:
      ...
      - collector_item.db_type_code is defined
      - collector_item.db_type_code | lower in ['postgresql', 'postgres', 'oracle', 'mssql', 'sqlserver']
    fail_msg: "DB_OBJECT_METADATA item missing required fields or invalid values (Phase 3.6B0 §4B C16-F0: only postgresql/oracle/mssql supported)."
```

### 4B.7 API 端点（8 端点全支持新 3 方言）

| 端点 | 现有支持 | C16-F0 后 |
|---|---|---|
| `POST /ai/sql/schema-snapshots/{id}/collect` | PG only | PG + Oracle + MSSQL（`db_type_code` 决定派发） |
| `GET /ai/sql/schema-snapshots/{id}` | PG only | 同上 |
| `GET /ai/sql/schema-snapshots/{id}/history` | PG only | 同上 |
| `GET /ai/sql/schema-snapshots/{id}/context` | PG only | 同上 |
| `POST /ai/sql/object-metadata/{id}/collect` | PG only（C16-F3） | PG + Oracle + MSSQL |
| `GET /ai/sql/object-metadata/{id}` | PG only（C16-F3） | 同上 |
| `GET /ai/sql/object-metadata/{id}/history` | PG only（C16-F3） | 同上 |
| `GET /ai/sql/object-metadata/{id}/context` | PG only（C16-F3） | 同上 |

异常映射保持不变（与 C8/C16-F3 同模式）：404 / 409 / 422（`UNSUPPORTED_DB_TYPE` / `CREDENTIAL_MISSING`）/ 502 / 503 / 504。

### 4B.8 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 编号 | docs §7 F-list 追加 **F0**（放在 F13 之后） | F13 编号已被 Object Metadata 首版占用；F0 标记"三方言合并"专项 |
| 提交方式 | 拆 2 commit（DDL/Builder/Ansible/collector + 测试/文档/记忆） | 避免单 commit ~5000 行风险 |
| Oracle 系统 schema 黑名单 | `SYS/SYSTEM/XDB/CTXSYS/MDSYS/OLAPSYS/ORDDATA/WMSYS/APEX_*` / `FLOWS_*` | Oracle 12c+ 默认系统 schema；业务 schema 不混 |
| Oracle table DDL 重建 | `XMLAGG/XMLELEMENT` 而非 `DBMS_METADATA.GET_DDL` | 避免 `SELECT_CATALOG_ROLE` 依赖；app 账号可跑 |
| MSSQL OBJECT_DEFINITION 加密 NULL | 6 处用 `OBJECT_DEFINITION`；NULL 落 `object_ddl_text=NULL` | 与 PG/Oracle segment 内 NULL 一致；callback 不强制非 NULL |
| MSSQL schema 过滤 | 排除 `sys`/`INFORMATION_SCHEMA`/`guest` | SQL Server 系统 schema 必排除 |
| MySQL 暂不实现 | `_SQL_TEMPLATE_MAP` 不含 `mysql` 键 → 422 | 按 plan §4.8 + capabilities `sql_supported_db_types` 显式延后 |
| 测距 | 84 unit tests：builder 36+36 + 12 边界/parametrize | 覆盖 5 dialect × 2 builder × happy/sad/parametrize |
| live E2E | dev 库 PG `10.134.185.228` id=965 已就绪；Oracle/MSSQL 待 dev 库注册后跑 | 与 C16-F1 同一 dev 库 PG 实例就绪机制 |
| DDL 不变 | 不需新迁移 | CHECK 约束本就含 4 个方言 |

### 4B.9 需新增/修改的文件

| 类型 | 路径 | 状态 |
|---|---|---|
| NEW | `backend/app/services/ai/sql_templates/oracle/ora_schema_columns.sql` | ✅ |
| NEW | `backend/app/services/ai/sql_templates/oracle/ora_object_metadata.sql` | ✅ |
| NEW | `backend/app/services/ai/sql_templates/mssql/mssql_schema_columns.sql` | ✅ |
| NEW | `backend/app/services/ai/sql_templates/mssql/mssql_object_metadata.sql` | ✅ |
| MOD | `backend/app/services/check_item_builder_registry.py` | ✅（`_AiSchemaMetadataBuilder` + `_AiObjectMetadataBuilder` 重构） |
| MOD | `backend/app/services/collector_service.py` | ✅（修 C16-F3 漏注册：`DB_OBJECT_METADATA` 加 `_check_definition_defaults` + reachability gating set） |
| MOD | `backend/tests/test_ai_schema_metadata_builder.py` | ✅（36+ cases 覆盖 5 dialect） |
| MOD | `backend/tests/test_ai_object_metadata_builder.py` | ✅（36+ cases 覆盖 5 dialect） |
| MOD | `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml` | ✅（assertion 扩 5 dialect） |
| MOD | `ansible-playbooks/playbooks/roles/db_object_metadata_collect/tasks/main.yml` | ✅（assertion 扩 5 dialect） |
| MOD | `docs/40-tech-debt.md` §7 F-list 追加 F0 | ✅（已加 F0 行） |
| MOD | `docs/10-module-map.md` §2 追加 row | ✅（已加 C16-F0 row） |
| MOD | `docs/contracts/api-inventory.md` 追加 4 端点 oracle/mssql 支持声明 | ✅（已加三方言支持表 + 说明） |
| MOD | `docs/30-runbook.md` §8.2/§8.5 补 oracle/mssql 排障段 | ✅（已加 5+5 排障 rows） |
| MOD | `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §4B | ✅（本节） |
| NEW | `memory/phase-3-6-c16-f0-completed-2026-07-07.md` | ⏳（commit 3 闭环时写） |
| MOD | `memory/MEMORY.md` 索引 | ⏳（commit 3 闭环时加） |

### 4B.10 Rollback（按 commit 倒序）

```bash
# commit 2 失败（仅 docs + tests + memory）
git revert <commit-2-sha> --no-edit && git push

# commit 1 失败（DDL/Builder/Ansible/collector）
git revert <commit-1-sha> --no-edit && git push
# 不需 SQL 回滚（DDL 未变更；仅行为层回退到 PG-only）
# 但若已注册的 Oracle/MSSQL 实例 snapshot 数据保留（snapshot.db_type_code 仍
# 是新值，回退后 GET 仍能查；但前端 collect 入口会 422）
```

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

方言映射: postgresql→postgres, mssql/sqlserver→tsql, oracle→oracle, mysql→mysql。C16 要求 PostgreSQL/Oracle/SQL Server 三种方言的 `validate_with_ast` 测试全部通过。

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

## 5b. Dify Code 节点兜底校验

> **职责边界**：Dify Code 节点只做轻量兜底，**不是权威校验**。完整 SQL 授权、字段解析、CTE、alias、子查询、方言 limit 重写，全部以后端 `SqlSafetyService.validate_with_ast(sqlglot)` 为准。Execute 只能使用 `approved_sql`，不能使用 Dify `generated_sql`。

### 5b.1 dbops-sql-generator Code 节点轻量兜底（非权威校验）

Dify Code 节点只做以下轻量兜底：
1. 解析 LLM 输出 JSON。
2. 校验 `need_execute` / `sql_text` / `risk_level` 基本字段。
3. 拒绝明显危险 SQL：非 SELECT、分号、多语句、DML/DDL、高危函数、`SELECT *`。
4. 对表、字段、敏感列、limit 只做 best-effort warning，不作为最终拒绝依据。
5. 完整 SQL 授权、字段解析、CTE、alias、子查询、方言 limit 重写，全部以后端 `SqlSafetyService.validate_with_ast(sqlglot)` 为准。
6. Execute 只能使用 `approved_sql`，不能使用 Dify `generated_sql`。

**Hard Reject（Code 节点直接拒绝，13 条）**:
```text
1.  instance_id 为空 → rejected
2.  schema_context 为空 → rejected
3.  allowed_tables 非法 JSON 或为空 → rejected
4.  allowed_columns_json 非法 JSON 或为空 → rejected
5.  denied_columns_json 非法 JSON → rejected
6.  max_rows 非 1~500 → rejected
7.  LLM 输出不是合法 JSON → rejected
8.  risk_level 非 low/medium/high/rejected → rejected
9.  need_execute=true 但 sql_text 为空 → rejected
10. SQL 不是 SELECT / WITH → rejected
11. SQL 包含分号 → rejected
12. SQL 命中明显危险关键字（DROP/TRUNCATE/DELETE/INSERT/UPDATE/ALTER/CREATE/EXEC/EXECUTE/pg_sleep/dblink/OPENROWSET/OPENQUERY/INTO OUTFILE/INTO DUMPFILE）→ rejected
13. SQL 包含 SELECT * / table.* → rejected
```

**Best-Effort Warning（只记录到 reason，以后端 sqlglot AST 为最终裁决）**:
```text
W1. SQL 中 FROM/JOIN 表不在 allowed_tables → 记录提示，不拒绝
W2. SQL 命中 denied_columns_json → 记录提示，不拒绝
W3. SQL 未按目标数据库方言限制返回行数（无 LIMIT / TOP / FETCH）→ 记录提示，不拒绝
W4. 字段无法完整匹配 allowed_columns_json → 记录提示，不拒绝
```

### 5b.2 dbops-report-analyzer Code 节点强制规则（9 条）

```text
1. health_level=critical → risk_level 至少 high，need_manual_review=true
2. health_level=unknown → need_manual_review=true
3. failed_results_json 非空 → need_manual_review=true
4. failed_results_json 非空 → recommendations 必须包含复核网络、端口、凭证、权限或实例状态，并建议修复后重跑巡检
5. top_risks_json / abnormal_results_json 存在 critical → risk_level 至少 high，need_manual_review=true
6. confidence < 0.6 → need_manual_review=true
7. max_recommendations 范围 1~20，默认 8
8. root_causes 最多 6 条
9. Dify 输出非法 JSON 时返回兜底分析，不直接 500
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

## 8. 巡检分析 — 202 + BackgroundTasks + 版本历史

### 处理流程

```text
POST /inspection/reports/{id}/ai-analysis

处理流程：
1. 校验权限
2. 计算 source_data_hash（见 §8b）
3. 命中缓存且 force=false → 返回当前 ready/reviewed 分析
4. 未命中或 force=true → 创建 pending analysis
5. 立即返回 202 + analysis_id
6. BackgroundTasks 调用 Dify workflow
7. BackgroundTask 内重新创建 DB Session（禁止复用请求生命周期里的 DB Session）
8. 成功后两阶段发布：新 ready 设为 is_current=true，旧 current 设为 is_current=false, superseded_at=now()
9. 失败后新记录 failed，旧 current 保持不变
10. 前端每 3 秒轮询 GET /inspection/reports/{id}/ai-analysis
```

> **禁止在请求事务中同步等待 Dify 120 秒。禁止 BackgroundTask 复用请求生命周期里的 DB Session。**

### 重新分析流程（含事务锁 + 两阶段发布）

```text
POST /inspection/reports/{id}/ai-analysis {force: true}
  ↓
事务 1（SELECT ... FOR UPDATE）:
  1. 锁定 inspection_report 行（overall）或 inspection_instance_report 行（instance）
  2. 查询当前 is_current=true 记录
  3. 计算 source_data_hash（见 §8b）
  4. 缓存命中且 force=false → 返回 200 + 已有分析（不创建新记录）
  5. 【关键】不修改旧记录！旧 ready/reviewed 版本继续 is_current=true
  6. 插入新记录 version=old_version+1, is_current=false, status=pending
  7. COMMIT
  8. 返回 202 + analysis_id
  ↓
BackgroundTask（独立 DB Session）:
  9. 调用 Dify workflow
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

### source_data_hash 计算规则（canonical SHA-256）

```text
source_data_hash 计算规则：

1. 只包含影响 AI 分析结论的字段：
   - report_id
   - instance_report_id
   - analysis_scope
   - health_level
   - health_score
   - summary_json
   - abnormal_results_json
   - failed_results_json
   - top_risks_json
   - target_snapshot_json

2. 排除易变字段：
   - created_at
   - updated_at
   - generated_at
   - exported_at
   - collected_at
   - elapsed_ms
   - duration_ms

3. JSON canonical dumps：
   - sort_keys=true
   - separators=(',', ':')
   - ensure_ascii=false

4. 列表稳定排序：
   - abnormal_results 按 severity DESC, result_code ASC, target_id ASC
   - failed_results 按 result_code ASC, target_id ASC
   - top_risks 按 risk_level DESC, result_code ASC

5. hash 算法固定 SHA-256。
```

Python 实现：
```python
import hashlib
import json


def stable_hash(payload: dict) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
```

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

### review endpoint 规则

```text
1. 只允许 analysis_status='ready' 且 is_current=true 的记录标记 reviewed
2. reviewed 后仍保持 is_current=true
3. 非 current 历史版本 review 返回 409 analysis_not_current
4. failed / pending 不允许 review
5. reviewed 版本如果 source_data_hash 变化，旧 reviewed 保留历史，新分析重新生成 pending
```

### 缓存键
`source_data_hash + workflow_version`（`workflow_version` 从 `DIFY_REPORT_WORKFLOW_VERSION` 配置读取）。workflow_version 变化 → Dify prompt/逻辑已变更 → 强制重新分析。

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

### DOCX AI 章节写入规则

```text
1. 不渲染 HTML
2. 不解析 Markdown
3. 所有字段按纯文本写入
4. root_causes 最多 6 条
5. recommendations 最多 max_recommendations 条（默认 8）
6. 写入固定免责声明
7. 文档元数据记录 analysis_id、analysis_version、workflow_version
```

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
  "sql_preview_enabled": true,
  "sql_execution_enabled": true,
  "report_analysis_enabled": true,
  "report_export_ai_enabled": false,
  "stream_enabled": false,
  "sql_supported_db_types": ["POSTGRESQL", "ORACLE", "MSSQL"]
}
```

> **注意**：MySQL Schema Snapshot 本阶段不实现。`capabilities` 只声明后端已支持的 DB 类型。

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
POST collect 返回 202（不假装同步完成）、ai_schema callback 成功生成 Snapshot、callback 重复到达保持幂等、Snapshot 过期后 Preview 被拒绝、Snapshot 在 Preview 后变化 Execute 返回 409、C13 阶段仅完成 PostgreSQL Preview 基础验证（C16-F0 后扩展为三种 DB）、truncated=true 不允许 success、Snapshot running 超时→failed

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

### Dify Code 节点契约测试 — sql-generator (10)
instance_id 为空→rejected / schema_context 为空→rejected / allowed_tables 非法 JSON→rejected / allowed_columns_json 非法 JSON→rejected / max_rows=0→rejected / max_rows=501→rejected / risk_level=xxx→rejected / SQL 无 LIMIT/TOP/FETCH→rejected / SQL 访问未授权表→rejected / SQL 命中 denied_columns_json→rejected

### Dify Code 节点契约测试 — report-analyzer (8)
health_level=critical → risk_level 至少 high + need_manual_review=true / failed_results_json 非空→need_manual_review=true / confidence=0.5→need_manual_review=true / top_risks_json 存在 critical→risk_level 至少 high / max_recommendations=20 生效 / max_recommendations=100 被收敛为 20 / LLM 非法 JSON 返回兜底 analysis_json / health_level=unknown→need_manual_review=true

### 输入限制测试 (6)
user_question 超 2000 拒绝 / max_rows 超 500 拒绝 / explain 超 4000 截断 / generated_sql 超 20000 截断 / summary_json 超 200000 截断 / abnormal_results_json 超 500000 截断

**总计: ~140 用例**

---

## 14. Commit 顺序

### 已完成（C1-C15）

C1-C15 已全部 commit 到 `feature/phase-3.6-ai-copilot`，详见 memory 文件。

### 当前剩余 Commit 顺序

| # | Commit | 内容 |
|---|--------|------|
| 1 | C16-F1 | awx_job_id 回填 + callback 幂等 guard |
| 2 | C16-F0 | Oracle / SQL Server Schema Snapshot 模板 + Builder 分发 + sqlglot 三方言测试 |
| 3 | C16-F6 | 三种 DB dev/test 实例补齐 |
| 4 | C16-F2a | Chat session 绑定实例字段（chat_mode + bound_instance_id DDL）+ 不可变绑定规则 |
| 5 | C16-F2b | Preview API 改成 Chat 入口（session_id + client_request_id + 写 user message + preview message + audit） |
| 6 | C16-F2c | Chat SQL Preview Card 前端 |
| 7 | C16-F2d | Execute + Result Card + Result API + 轮询 |
| 8 | C22-C27 | Inspection AI Analysis（202 + BackgroundTasks）+ DOCX include_ai |
| 9 | C28-C32 | 安全回归、DDL 验证、文档、stale cleanup |

---

## 15. 环境启用顺序

```
Phase A:      AI_CHAT_ENABLED=true, 其他 false
+B0:         AI_SQL_PREVIEW_ENABLED=false (schema 准备中)
+B1 Preview:  AI_SQL_PREVIEW_ENABLED=true, AI_SQL_EXECUTION_ENABLED=false, sql_supported_db_types=["POSTGRESQL", "ORACLE", "MSSQL"]
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

RAG/SSE/文件上传/打字流/Dify KB管理/AI自动执行SQL/AI修改规则引擎/后台自动采集schema(手动触发)/多provider/AI审计独立页面/MySQL Schema Snapshot

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
cd backend && pytest -q                                   # ~140 tests
cd backend && pytest tests/test_sql_safety_service.py -q  # 28 安全用例 + 18 Dify 契约
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

---

## 21. C16 第二部分重构：实例绑定 Chat SQL Copilot（2026-07-03 决策）

### 21.0 决策背景

Phase 3.6A Chat 基础能力（C1-C5）+ Schema Snapshot（C6-C10）+ SQL Safety（C11）+ SQL Preview（C12-C13）+ SQL Execute（C14）+ Chat 集成收尾（C15）已完成。

原 plan §14 的 C16-C21 把 Chat、SqlPreview.vue、Execute、Callback 当成分散链路推进。实际业务目标是：

> 资产中心实例详情 → 「AI 查询」→ Chat 绑定实例 → 自然语言 → SQL Preview 卡片 → 执行 → 结果卡片

因此**第二部分从"SQL Preview / Execute 分散开发"调整为"实例绑定 Chat SQL Copilot 完整闭环"**。

第三部分巡检 AI 分析（C22-C27）保持不变。

### 21.1 当前状态判断

#### 已完成 / 保留

- Phase 3.6A Chat 基础能力已完成（C1-C5）
- Schema Snapshot 链路已完成（C6-C10）
- SQL Preview 基础能力已完成（C12-C13）：`AiSqlPreviewService` + `POST /api/v1/ai/sql/preview`
- SQL Execute 基础能力已完成（C14）：`AiSqlExecuteService` + `POST /api/v1/ai/sql/execute` + `AiSqlCallbackService`
- `DifyService.run_sql_workflow()` 已实现，调用 `POST /workflows/run`（`dbops-sql-generator`）
- `db_sql_readonly_collect` 已允许 `business_domain='ai_sql'`
- generic collector playbook 已有 `DB_READONLY_SQL_EXEC` 和 `DB_SCHEMA_METADATA_COLLECTION` 路由
- `ai_sql_audit.result_message_id` 和 `awx_job_id` 字段已存在于 DDL 和 Model

#### 需要调整

1. **入口变化**：目标入口应为 `Chat.vue(boundInstanceId)`，不是独立 SQL Preview 页优先
2. **职责混杂**：`dbops-general-chat` 和 `dbops-sql-generator` 需要拆清楚；绑定实例模式只走 `DifyService.run_sql_workflow()`
3. **Chat 绑定实例模式**必须成为第二部分主入口
4. **普通 Chat 和 SQL Copilot 必须分流**
5. **前端不允许自行拼 `schema_context`、`allowed_tables`**
6. **Dify 输出只作为候选 SQL**，最终执行 SQL 必须以后端 AST 校验后的 `approved_sql` 为准
7. **`SqlPreview.vue` 不再作为主入口**；保留为 audit 详情 / 调试 / 深链详情页
8. **E2E 阻塞点是目标实例**：需要 PostgreSQL + Oracle + SQL Server 三种测试实例，每种至少 1 条

### 21.2 新目标

#### C16-B 新定义

把原 C16-B "F2 result_message_id E2E" 调整为：

> **F2：实例绑定 Chat SQL Copilot E2E**
> 覆盖：preview → execute → callback → result_message_id → Chat 结果卡片

#### 最终用户路径

```text
InstanceDetail.vue
  点击「AI 查询」
    ↓
Chat.vue?boundInstanceId=<instance_id>
    ↓
用户输入自然语言
    ↓
POST /api/v1/ai/sql/preview  (带 session_id + instance_id)
    ↓
Chat 显示 SQL Preview Card
    ↓
用户点击执行
    ↓
POST /api/v1/ai/sql/execute  (带 audit_id)
    ↓
AWX callback → AiSqlCallbackService
    ↓
Chat 显示 SQL Result Card
```

### 21.3 C16 执行顺序（新）

#### C16-1：F1 awx_job_id 回填（保留，~30 min）

目标：补齐 `ai_sql_audit.awx_job_id` 回填，便于前端详情和排障。

后端修改：
- `backend/app/services/ai/ai_sql_execute_service.py` — 在 AWX launch 后 UPDATE `ai_sql_audit SET awx_job_id=:id WHERE id=:aid AND awx_job_id IS NULL`
- `backend/app/services/ai/ai_sql_callback_service.py` — callback 增加 guard：只允许 `execution_status IN ('pending', 'running')` 时回填终态；callback 重放不重复写 `sql_result`

测试：
```bash
pytest -q tests/test_ai_sql_execute_service.py tests/test_ai_sql_callback_service.py
```

---

#### C16-2：定义 Chat boundInstanceId 合同（NEW）

目标：`Chat.vue` 明确区分两种模式。

**模式一：普通 Chat**
```text
boundInstanceId 为空
→ 走 dbops-general-chat
→ DifyService.chat_message()
→ POST /api/v1/ai/chat/sessions/{id}/messages
```

**模式二：实例绑定 SQL Copilot**
```text
boundInstanceId 有值
→ 走 dbops-sql-generator
→ DifyService.run_sql_workflow()
→ POST /api/v1/ai/sql/preview
→ 只生成 SQL Preview，不直接执行
```

前端约定：
```ts
type ChatMode = 'general' | 'instance_sql'

interface ChatSessionContext {
  mode: ChatMode
  boundInstanceId?: number
  boundInstanceName?: string
}
```

**不可变绑定规则（P0-1）：**

```text
Chat SQL 模式 session 绑定规则：

1. ai_chat_session.chat_mode = 'instance_sql'
2. ai_chat_session.bound_instance_id 创建后不可变
3. SQL Preview 请求的 instance_id 必须等于 session.bound_instance_id
4. 不一致时返回 409 bound_instance_mismatch
5. chat_mode='general' 的 session 禁止调用 /ai/sql/preview
6. chat_mode='instance_sql' 的 session 禁止调用普通 /ai/chat/sessions/{id}/messages
```

**DDL（必须本次加字段，安全边界不建议只靠 JSONB）：**

```sql
-- ❗Dangerous：生产环境执行 ALTER TABLE 可能短暂锁表，需放在变更窗口执行。
-- 执行前先确认表数据量：
-- SELECT COUNT(*) FROM dbops.ai_chat_session;

ALTER TABLE dbops.ai_chat_session
ADD COLUMN IF NOT EXISTS chat_mode VARCHAR(30) NOT NULL DEFAULT 'general',
ADD COLUMN IF NOT EXISTS bound_instance_id BIGINT NULL;

ALTER TABLE dbops.ai_chat_session
DROP CONSTRAINT IF EXISTS chk_ai_chat_session_mode;

ALTER TABLE dbops.ai_chat_session
ADD CONSTRAINT chk_ai_chat_session_mode
CHECK (chat_mode IN ('general', 'instance_sql'));

ALTER TABLE dbops.ai_chat_session
DROP CONSTRAINT IF EXISTS chk_ai_chat_session_bound_instance;

ALTER TABLE dbops.ai_chat_session
ADD CONSTRAINT chk_ai_chat_session_bound_instance
CHECK (
    (chat_mode = 'general' AND bound_instance_id IS NULL)
    OR
    (chat_mode = 'instance_sql' AND bound_instance_id IS NOT NULL)
);

-- partial unique index：同一用户同一实例只复用一个 instance_sql session
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_session_user_instance_sql
ON dbops.ai_chat_session(user_id, bound_instance_id)
WHERE chat_mode = 'instance_sql' AND bound_instance_id IS NOT NULL;
```

> **设计决策**：`chat_mode` 和 `bound_instance_id` 作为实体字段而非 JSONB 内字段。原因：这是安全边界（SQL Preview 入口鉴权依赖此字段），不应只靠 JSONB 属性。`metadata_json` 仍可用于存 `bound_instance_name`、`source_page`、`context_version` 等非鉴权辅助信息。

**Session 创建/复用 API 契约（P0-2）：**

```http
POST /api/v1/ai/chat/sessions
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

请求：
```json
{
  "mode": "instance_sql",
  "bound_instance_id": 123,
  "source_page": "instance_detail"
}
```

规则：
```text
1. mode='general' 时创建普通 Chat session（chat_mode='general', bound_instance_id=NULL）。
2. mode='instance_sql' 时必须传 bound_instance_id。
3. bound_instance_id 必须是当前用户可访问的实例。
4. 已存在同 user_id + chat_mode + bound_instance_id 的未删除 session 时，优先复用。
5. session 创建后 chat_mode 和 bound_instance_id 不允许修改。
6. chat_mode='general' 的 session 不允许调用 /ai/sql/preview。
7. chat_mode='instance_sql' 的 session 不允许调用普通 /ai/chat/sessions/{id}/messages。
```

#### C16-2a 实施记录（2026-07-07 闭环）

- DDL: `backend/db/dbops_phase3_6b2_c16_f2a_chat_mode.sql`（idempotent，2 次幂等验证 OK）
  - `chat_mode VARCHAR(30) NOT NULL DEFAULT 'general'`（'general'/'instance_sql'）
  - `bound_instance_id BIGINT NULL` FK → `db_instance.id` ON DELETE CASCADE
  - 2 CHECK: `chk_ai_chat_session_mode` (枚举) + `chk_ai_chat_session_bound_instance` ((general↔NULL) OR (instance_sql↔NOT NULL))
  - partial unique `uq_ai_chat_session_user_instance_sql` (user_id, bound_instance_id) WHERE chat_mode='instance_sql' AND bound_instance_id IS NOT NULL
  - 辅助 idx `idx_ai_chat_session_bound_instance`
- ORM: `AiChatSession` 加 chat_mode + bound_instance_id + 2 CheckConstraint + 2 Index
- Schemas: `AiChatSessionCreateRequest` 加 mode + bound_instance_id + source_page；`AiChatSessionResponse` 暴露 chat_mode + bound_instance_id；`ChatMode = Literal['general', 'instance_sql']`
- Service: `AiChatService.create_session` 签名扩展，返回 `CreateSessionResult(session, reused)` dataclass
  - 校验链: mode 枚举 → mode/bound 一致 → DbInstance.status='active' → instance_sql 复用 → 新建
  - 3 新异常: `ChatModeInvalidError` / `ChatInstanceNotAccessibleError` / `ChatImmutableViolationError`
  - 复用: 仅 `mode='instance_sql'` 复用（general 用户可建多个独立会话；与 partial unique 设计一致）
  - **修正**：access check 用 `DbInstance.status` 字段（不是 `is_active` — DbInstance 无该字段；DbType 才有；status='active' 即视为可访问）
- API: `POST /api/v1/ai/chat/sessions` 透传 mode/bound_instance_id/source_page；422/404/409 异常映射
- Tests: `backend/tests/test_ai_chat_service_c16_f2a.py` 15 cases（14 passed / 1 skipped 因 dev 库只有 1 active user）；verify.sh 0 failed / 2 skipped（历史 C13 sqlglot）
- Docs: tech-debt F14 + module-map + api-inventory + runbook §8.6 (6 排障行)
- Commits: 3 个 (`cb0aed8` DDL+ORM+Schemas / `2fe07b0` Service+API / commit 3 测试+文档+memory)

**下轮起手 (C16-2b)**：重构 SQL Preview API 为 Chat 可调用入口（plan §21.3），消费 `session.chat_mode='instance_sql'` + `session.bound_instance_id` 鉴权 + 写 user/preview 双消息。

---

#### C16-3：重构 SQL Preview API 为 Chat 可调用入口（NEW）

目标：`Chat.vue(boundInstanceId)` 发送自然语言后，直接创建 Preview 卡片。

推荐请求：
```http
POST /api/v1/ai/sql/preview
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

```json
{
  "session_id": 1001,
  "instance_id": 123,
  "user_question": "查询最近 10 条订单",
  "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
  "max_rows": 100
}
```

推荐响应（统一 `{code: 0, data: ...}` 格式）：
```json
{
  "code": 0,
  "data": {
    "audit_id": 9001,
    "session_id": 1001,
    "user_message_id": 2001,
    "preview_message_id": 2002,
    "instance_id": 123,
    "preview_safety_status": "passed",
    "generated_sql": "SELECT ...",
    "approved_sql": "SELECT ... LIMIT 100",
    "explain": "查询最近 10 条订单",
    "risk_level": "low",
    "schema_snapshot_id": 3001,
    "schema_policy_hash": "sha256...",
    "execution_status": "not_requested"
  }
}
```

后端处理顺序：
```text
1. 校验 session_id 属于当前 user
2. 校验 session.chat_mode='instance_sql' 且 instance_id 与 session.bound_instance_id 一致（P0-1 不可变绑定）
3. 幂等检查（P0-2）：按 client_request_id 查已有 user message
   → 命中且 audit 存在：返回已有 audit_id/user_message_id/preview_message_id（不调 Dify）
   → 命中但 audit 不存在：旧 user message 标记 stale，返回 409 preview_incomplete_retry_required
   → 未命中：继续
4. 校验 DB 类型：PostgreSQL / Oracle / SQL Server（`sql_supported_db_types` 白名单，MySQL 不在范围内）
5. 调用 AiSchemaContextService.build_schema_context()
6. schema 不可用 → 409 schema_context_unavailable
7. 构造 Dify inputs
8. 调用 DifyService.run_sql_workflow()
9. 解析 Dify 输出 need_execute / sql_text / explain / risk_level / reason
10. 后端 SqlSafetyService AST 校验
11. 写 ai_sql_audit（P0-3：preview_safety_status='passed' 或 'rejected' 均写入，便于审计追溯）
12. 写 ai_chat_message:
    - user message：用户自然语言（写入 client_request_id，P0-2 幂等键）
    - assistant message：message_type='sql_preview_link'
13. 返回 preview card 数据
```

**Preview 幂等规则（P0-2）：**

```text
SQL Preview 幂等规则：

1. client_request_id 只写入 user message
2. 重复 client_request_id 命中已有 user message 时：
   - 不再调用 Dify
   - 不再创建 ai_sql_audit
   - 不再创建 preview message
   - 返回已有 user_message_id、preview_message_id、audit_id
3. 通过 ai_sql_audit.message_id = user_message.id 反查 audit
4. 如果 user message 存在但 audit 不存在，说明上次请求中断：
   - 将旧 user message 标记 stale 或 error
   - 返回 409 preview_incomplete_retry_required
```

幂等验收 SQL：
```sql
SELECT
    m.id AS user_message_id,
    m.client_request_id,
    a.id AS audit_id,
    a.message_id,
    a.result_message_id,
    a.execution_status
FROM dbops.ai_chat_message m
LEFT JOIN dbops.ai_sql_audit a
       ON a.message_id = m.id
WHERE m.session_id = <SESSION_ID>
  AND m.client_request_id = '<CLIENT_REQUEST_ID>';
```

**Rejected 也写 audit（P1-3）：**

```text
1. Dify need_execute=false → 写 ai_sql_audit，preview_safety_status='rejected'
2. AST 校验失败 → 写 ai_sql_audit，preview_safety_status='rejected'
3. rejected preview message 仍写入 Chat（message_type='sql_preview_link'）
4. rejected 卡片不显示执行按钮
```

Dify inputs 固定使用（`db_type_code` / `sql_dialect` 按实例类型自动选择；P0-4 增加列级约束以减少 Dify 生成被拒 SQL）：
```json
{
  "user_question": "...",
  "db_type_code": "POSTGRESQL | ORACLE | MSSQL",
  "sql_dialect": "PostgreSQL | Oracle | SQL Server",
  "schema_context": "...",
  "allowed_tables": "[\"app.orders\", \"app.customers\"]",
  "allowed_columns_json": "{\"app.orders\":[\"id\",\"order_no\",\"status\",\"amount\",\"created_at\"]}",
  "denied_columns_json": "[\"password_hash\",\"secret_key\",\"token\",\"api_key\",\"credential\"]",
  "max_rows": "100",
  "instance_id": "123",
  "instance_name": "...",
  "target_database": "...",
  "target_ip": "...",
  "target_port": "..."
}
```

**Dify I/O 契约（P0-3 — 后端与 Dify 的字段名是代码契约，必须进 plan）：**

后端只接受以下 Dify outputs：
```text
need_execute   — bool，是否生成 SQL
sql_text       — str，Dify 生成的候选 SQL
explain        — str，自然语言解释
risk_level     — str，low / medium / high
reason         — str，生成决策原因
```

> Dify 平台操作（登录/修改 prompt/发布）不进 plan，由人工手动更新。但后端 inputs/outputs 字段名是代码契约，必须保留在 plan 中。

**Preview 输入限制（P1-1）：**
```text
1. user_question 最大 2000 字符。
2. max_rows 范围 1~500，默认 100。
3. explain / reason 入库前最大 4000 字符。
4. generated_sql / approved_sql 最大 20000 字符。
5. Dify 返回字段缺失或类型错误时，写 rejected audit，不直接 500。
```

禁止事项：
- ❌ 前端传入 `schema_context`
- ❌ 前端传入 `allowed_tables`
- ❌ 前端传入 `approved_sql`
- ❌ Dify 输出绕过 AST 校验
- ❌ Preview 自动执行 SQL

---

##### C16-3 实施记录 — C16-F2b 已闭环（2026-07-07）

3 commit 闭环（dbops HEAD `c6e4e0c...` 后续 + `babe687` + `54b122d`）：

| Commit | 内容 | 影响 |
|---|---|---|
| `babe687` | Schemas + Service 鉴权链 + 异常类型 | `AiSqlPreviewRequest` 加 `session_id`(必填) + `client_request_id`(必填) 移除 `message_id`；`AiSqlPreviewResponse` 加 `session_id/user_message_id/preview_message_id/idempotent_replay`；preview() 签名加 `client_request_id`；`_auth_check_session_for_preview` 4 步鉴权链；5 类新异常（`ChatSessionNotFoundErrorPreview` / `ChatSessionForbiddenErrorPreview` / `ChatModeNotInstanceSqlError` / `ChatImmutableViolationErrorPreview` / `PreviewIncompleteRetryRequiredError`）；`AiChatService.get_session_for_user` helper |
| `54b122d` | API 端点映射 + Service 幂等分支 + 双消息写入事务 | step 2.5 幂等检查（client_request_id 命中已有 user_message → 返回原三元组 + `idempotent_replay=True`；audit 缺失 → 409）；`_finalize_preview_with_chat_messages` helper（user + preview sql_preview_link + audit 同事务 + session.message_count += 2）；`api/ai.py` 5 类异常 HTTP 映射（404/403/422/409）；`PreviewResult` 扩 4 字段；rejected 也写 preview_message 卡片（P1-3） |
| 后续 commit | 测试 + 文档 + memory 收尾 | `tests/test_ai_sql_preview_c16_f2b.py` 14 cases（5 鉴权链 / 3 幂等 / 4 双消息写入 / 1 响应字段 / 1 兜底）；4 docs 同步（`40-tech-debt.md` F15 / `10-module-map.md` §2 / `contracts/api-inventory.md` §2.16 / `30-runbook.md` §8.7 6 排障行）；memory + MEMORY.md 指针 |

**关键设计决策（实施中验证）**：

1. **session ownership 统一 404 隔离** — `_auth_check_session_for_preview` step 1.5 把 session 不存在 vs 不属于当前用户统一返回 `ChatSessionNotFoundErrorPreview` (404)，避免泄露「会话存在但属于他人」；`ChatSessionForbiddenErrorPreview` 类保留作为防御性兜底（当前不会抛）。
2. **5 类新异常不复用 chat service 同名异常** — preview service 与 chat service 保持低耦合；命名以 `Preview` 后缀明确区分。
3. **`PreviewResult` 数据类扩展 4 字段** — `session_id` / `user_message_id` / `preview_message_id` / `idempotent_replay`，向后兼容旧字段。
4. **幂等命中不重写 preview_message** — 直接返回原 `preview_message_id`；前端用 `idempotent_replay=true` 提示用户「已使用缓存结果」。
5. **rejected 也写双消息（P1-3 落地）** — preview_message.content 写 `{audit_id, status, reason}` JSON（无 approved_sql/execute 按钮）。
6. **双消息事务** — `db.flush() × 2` 取 id → 关联 audit.message_id + result_message_id → commit；与 C14 `AiSqlCallbackService` 同模式。
7. **`_dialect_for_safe` 私有映射** — 避免 preview service 依赖 `AiSchemaContextService` 私有方法。

**Live E2E 验收**（dev 库 PG 实例 id=965）：
- 创建 instance_sql session + 首次 Preview → audit + user + preview 三元组写入
- 同 `client_request_id` 重复 → 三元组一致 + `idempotent_replay=true`（不调 Dify）
- DB 直查验证（plan §21.3 幂等验收 SQL）：user_msg + preview_msg + audit_id 单行
- `instance_id=999` 越界 → 422 `chat_immutable_violation`
- general 模式 session → 422 `chat_mode_not_instance_sql`

**下轮起手**：C16-F2c `Chat.vue` boundInstanceId 模式分流 + `SqlPreview.vue` 重构（plan §21.3 C16-4）。

---

#### C16-4：Chat.vue boundInstanceId 前端重构（NEW）

目标：资产实例详情进入 Chat 后，用户只看到自然语言交互和 SQL 卡片，不需要跳转到独立预览页。

修改文件：
- `frontend/src/views/ai/Chat.vue`
- `frontend/src/components/ai/ChatMessageBubble.vue`
- `frontend/src/api/ai.ts`
- `frontend/src/types/ai.ts`
- `frontend/src/views/InstanceDetail.vue`

前端行为（P1-1 统一命名：route query 用 `boundInstanceId`，API body 用 `instance_id`）：
```text
InstanceDetail.vue
  点击「AI 查询」
  router.push({
    name: 'AiChat',
    query: { boundInstanceId: String(instance.id) }
  })
```

`Chat.vue` 初始化：
```text
1. 读取 route.query.boundInstanceId
2. boundInstanceId 存在 → mode='instance_sql'
3. 创建或复用绑定实例 session
4. 顶部显示实例上下文：
   - instance_name
   - db_type
   - host:port
   - schema snapshot 状态
5. 输入框 placeholder 改为：
   "请输入要查询的数据，例如：查询最近 10 条订单"
```

发送消息分流：
```text
mode='general'
  → POST /api/v1/ai/chat/sessions/{id}/messages

mode='instance_sql'
  → POST /api/v1/ai/sql/preview
```

Chat 卡片类型：
```text
chat                 普通文本
sql_preview_link     SQL 预览卡片
sql_result           SQL 执行结果卡片
error                错误卡片
```

Preview 卡片按钮：
```text
安全通过：
  - 查看 SQL
  - 执行
  - 复制 SQL

安全拒绝：
  - 展示拒绝原因
  - 不显示执行按钮
```

##### C16-4 实施记录 — C16-F2c 已闭环（2026-07-07）

起手 commits（按 plan §21.6 顺序 3 步拆分）：

1. **commit 1 `387ad97`** — Chat.vue boundInstanceId 模式分流 + F2b 遗留 bug 修复
   - 6 files / +404 −42
   - `backend/app/schemas/ai.py`：`AiChatMessageResponse.message_type` Literal 加 `'sql_preview_link'`（F2b 漏修）
   - `frontend/src/types/ai.ts`：`AiChatSessionCreateRequest` 3 字段（`mode?` / `bound_instance_id?` / `source_page?`）+ `AiChatSession` 2 字段（`chat_mode?` / `bound_instance_id?`）+ `AiSqlPreviewRequest` 必填 `session_id` + `client_request_id`（移除 `message_id`）+ `AiSqlPreviewResponse` 4 字段（`session_id` / `user_message_id` / `preview_message_id` / `idempotent_replay`）+ `AiSqlPreviewLinkMetadata.reason?`
   - `frontend/src/views/ai/Chat.vue`：`parseBoundInstanceId` + `loadBoundInstanceContext` + `createBoundSession` + `exitBoundMode` + `activeSessionIsInstanceSql` computed + `inputPlaceholder` computed + `describePreviewError` helper + onSend 分流（`aiApi.sqlPreview` 走 instance_sql；调用后 `loadMessages` 同步后端实际状态）+ onMounted `Promise.all([loadBoundInstanceContext, createBoundSession])` + 模板：bound 模式隐藏会话侧栏、显示实例上下文 header（`instance_name / db_type_code / server_ip:port`）、「返回通用 Chat」按钮、placeholder 切换
   - `frontend/src/views/InstanceDetail.vue`：`useRouter` + `gotoAiChat` + 「AI 查询」按钮（`auto_awesome` 图标 + `data-testid="instance-ai-chat-button"`）
   - `frontend/src/components/ai/ChatMessageBubble.vue`：重写 `previewLinkMeta` computed（合并 `metadata_json` audit_id/status + `content` JSON approved_sql/schema_policy_hash/reason）+ rejected 分支模板（红框 + 「SQL Preview 被拒绝（audit #N）」 + reason 显示 + 无执行按钮）
   - `frontend/src/api/ai.ts`：`createSession` 透传 `mode` / `bound_instance_id` / `source_page`

2. **commit 2 `209bff7`** — SqlPreview.vue boundInstanceId 重定向
   - 1 file / +21
   - `frontend/src/views/ai/SqlPreview.vue`：`parseBoundInstanceIdFromQuery` helper + onMounted 检测 `route.query.boundInstanceId` → `router.replace({name: 'AiChat', query: {boundInstanceId}})`（用户只看到自然语言交互和 SQL 卡片，不跳独立预览页）

3. **commit 3 (本次收尾)** — 测试 + 文档 + memory
   - 1 测试文件 `backend/tests/test_ai_chat_message_response_c16_f2c.py`（3 回归测试用例：接受 `sql_preview_link` / 5 枚举全过 / 拒绝 unknown）
   - 4 docs 同步：`docs/40-tech-debt.md` F16 row + `docs/10-module-map.md` AI Copilot - Chat 行扩展 + 新行 "AI Copilot - Chat 前端 boundInstanceId 模式分流（C16-F2c）" + `docs/contracts/api-inventory.md` §2.16.C 补 `message_type` 5 值 Literal + §2.16.D 新增（C16-F2c 模式分流规则 + 端点调用矩阵 + ChatMessageBubble.previewLinkMeta 合并规则） + `docs/30-runbook.md` §8.8 新增（8 行排障：按钮缺失 / header 不显示 / 退出无反应 / 500 bug / Preview 卡片不渲染 / reason 不显示 / 重定向失败 / onSend 调错端点）
   - 1 memory：`phase-3-6-c16-f2c-completed-2026-07-07.md` + MEMORY.md 指针

**验证**：
- `bash scripts/ai/verify.sh` → 0 failed（2 skipped 系历史 C13 sqlglot 环境问题，与本次无关）
- pytest：693 passed（含 3 新增 C16-F2c 回归测试；C8/C10/C14/F2a/F2b 全部回归无副作用）
- vue-tsc：0 错
- 现场 live E2E：dev 库 `POST /api/v1/ai/chat/sessions` + `POST /api/v1/ai/sql/preview` 走通 instance_sql 全链路（创建/复用 session + Preview 5 态机 + 双消息写入 + 执行结果回流 Chat）
- 3 步 commit 都已 push 到 `feature/phase-3-6-ai-copilot` 分支

**下轮起手**：F17 跨入口一致性回归（`/ai/sql/preview` form 模式 vs Chat 模式，前端 form 表单入口已 commit 1 改造 + commit 2 重定向，待补自动化测试覆盖双向一致性）/ Phase 3.7 下一阶段（Inspection AI 集成）。

---

#### C16-5：Execute 按钮和结果卡片闭环（NEW）

目标：用户点击 Preview 卡片上的"执行"后，异步等待 AWX callback，最终在 Chat 内出现结果卡片。

执行请求：
```http
POST /api/v1/ai/sql/execute
Content-Type: application/json
Authorization: Bearer <TOKEN>
```

```json
{
  "audit_id": 9001
}
```

后端执行校验（P0-4 修正状态机：not_requested → pending → running）：

```text
1. audit 存在
2. audit 属于当前 user / session
3. preview_safety_status='passed'
4. execution_status='not_requested'
5. schema_snapshot 仍为 success
6. schema_snapshot.is_current=true
7. schema_snapshot 未过期
8. schema_policy_hash 一致
9. approved_sql_hash 一致
10. AST 二次校验通过
11. audit.execution_status='pending'  ← P0-4 修正：先 pending
12. 创建 CollectorRun + CollectorRunItem
13. AWX launch 成功 → audit.execution_status='running' + 写入 awx_job_id ← P0-4
14. AWX launch 失败 → audit.execution_status='failed' + error_message
15. 返回 collector_run_id / awx_job_id / execution_status
```

执行状态机（P0-4 修正）：
```
not_requested → pending → running → success
                                 ├→ failed
                                 ├→ timeout
                                 └→ cancelled
```

> **修正理由**：原 plan 写 `创建 CollectorRun 后直接 running`。实际 AWX launch 可能失败（网络/配置/队列满），应先 `pending` 再 `running`，便于排障。

轮询接口：
```http
GET /api/v1/ai/sql/executions/{audit_id}
```

推荐响应（统一 `{code: 0, data: ...}` 格式）：
```json
{
  "code": 0,
  "data": {
    "audit_id": 9001,
    "execution_status": "success",
    "row_count": 10,
    "duration_ms": 325,
    "collector_run_id": 7001,
    "awx_job_id": 123456,
    "result_message_id": 2010,
    "error_message": null
  }
}
```

前端轮询策略：
```text
1. 点击执行后立即把卡片状态改为 running
2. 每 3 秒轮询 execution
3. 终态 success/failed/timeout/cancelled 停止轮询
4. result_message_id 有值后刷新当前 session messages
5. Chat 中展示 sql_result 卡片
```

callback 写入规则：
```text
AWX callback
  → CollectorService.handle_callback()
  → business_domain='ai_sql'
  → AiSqlCallbackService.save_execution_results()
  → 条件 UPDATE ai_sql_audit
  → INSERT ai_chat_message(message_type='sql_result')
  → UPDATE ai_sql_audit.result_message_id
```

幂等要求：
- 同一个 `audit_id` 只能生成一条 `sql_result`
- callback 重放不重复写 message
- execute 重复点击返回 409 `audit_already_running` 或返回当前状态

**sql_result 独立结果读取 API（P0-3）：**

Chat message 只保存摘要，完整 rows 从 `CollectorRunResult.raw_result` 读取。

```http
GET /api/v1/ai/sql/executions/{audit_id}/result?limit=100&offset=0
```

响应（统一 `{code: 0, data: ...}` 格式）：
```json
{
  "code": 0,
  "data": {
    "audit_id": 9001,
    "execution_status": "success",
    "columns": ["id", "order_no", "status", "amount", "created_at"],
    "rows": [
      [1, "ORD-1", "pending", "10.50", "2026-07-03T10:00:00+08:00"]
    ],
    "row_count": 10,
    "returned_rows": 10,
    "masked_columns": [],
    "truncated": false,
    "duration_ms": 325
  }
}
```

分页（P1-2）：
```text
limit 允许范围：1~200
offset 最小值：0
默认 limit：100
超过 AI_SQL_RESULT_MAX_ROWS 时返回 truncated=true
```

权限规则：
```text
1. audit_id 必须属于当前 user
2. audit.session_id 必须属于当前 user
3. audit.result_message_id 不为空才能读取结果
4. 只从 CollectorRunResult.raw_result 读取 rows
5. 返回前再次执行列数、行数、cell 长度、总字节数、敏感列掩码限制
```

---

#### C16-6：F6 三种 DB 测试实例补齐（NEW）

目标：给 E2E 提供 PostgreSQL + Oracle + SQL Server 目标实例。

**PostgreSQL**：复用已有 dev 环境 PG，在上面新建隔离测试库即可：
```bash
psql -h <PG_DEV_HOST> -p <PG_DEV_PORT> -U <PG_ADMIN_USER> -d postgres -c "CREATE DATABASE appdb_dev;"
psql -h <PG_DEV_HOST> -p <PG_DEV_PORT> -U <PG_ADMIN_USER> -d appdb_dev <<'SQL'
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.orders (
    id bigserial PRIMARY KEY, order_no varchar(64) NOT NULL UNIQUE,
    status varchar(32) NOT NULL, amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO app.orders(order_no, status, amount, created_at)
SELECT 'ORD-' || gs, CASE WHEN gs % 2 = 0 THEN 'paid' ELSE 'pending' END,
       gs * 10.50, now() - (gs || ' hours')::interval
FROM generate_series(1, 20) AS gs
ON CONFLICT (order_no) DO NOTHING;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbops_readonly') THEN
        CREATE ROLE dbops_readonly LOGIN PASSWORD '<PASSWORD>';
    ELSE ALTER ROLE dbops_readonly WITH PASSWORD '<PASSWORD>'; END IF;
END $$;
GRANT USAGE ON SCHEMA app TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO dbops_readonly;
SQL
```

**Oracle / SQL Server**：复用现有 dev 环境中的已有测试实例即可（无需新建）。只需要：
1. 在目标库上创建只读账号 + 测试表（参照 PostgreSQL 脚本，用对应 SQL 方言重写）
2. 在 DBOPS 资产中心注册这些实例
3. 绑定只读凭证 profile
4. 配置 `allowed_schemas`

> ❗Dangerous：禁止用生产实例做 C16 E2E。Oracle/SQL Server 只允许使用已有 dev/test 环境实例。

DBOPS 资产侧需补齐（每种 DB 至少 1 条）：
- `db_instance` 记录（host/port/database/credential profile）
- 配置 `allowed_schemas`
- AWX Instance Group 可访问该实例
- 采集 Schema Snapshot 验证元数据 SQL 模板在该 DB 上可正常执行

---

#### C16-7：测试矩阵（NEW）

后端测试：
```bash
cd backend
pytest -q \
  tests/test_ai_sql_preview_service.py \
  tests/test_ai_sql_execute_service.py \
  tests/test_ai_sql_callback_service.py \
  tests/test_ai_chat_service.py \
  tests/test_sql_safety_service.py          # 三种方言 validate_with_ast 全通过
```

前端测试：
```bash
cd frontend
npm run typecheck
npm run test -- --run
```

E2E 验证（live curl）：
```bash
# === 以下 E2E 验证需要在 PostgreSQL + Oracle + SQL Server 三种实例上各执行一次 ===

# 1. Schema Snapshot
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:60801/api/v1/ai/sql/schema-snapshots/<INSTANCE_ID>/collect

# 2. 查询 Snapshot 状态
curl -sS \
  -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:60801/api/v1/ai/sql/schema-snapshots/<INSTANCE_ID>

# 3. SQL Preview（POSTGRESQL / ORACLE / MSSQL 均需验证）
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "instance_id": <INSTANCE_ID>,
    "user_question": "查询最近 10 条订单",
    "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
    "max_rows": 100
  }' \
  http://127.0.0.1:60801/api/v1/ai/sql/preview

# 4. SQL Execute
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"audit_id": <AUDIT_ID>}' \
  http://127.0.0.1:60801/api/v1/ai/sql/execute

# 5. Execution 状态
curl -sS \
  -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:60801/api/v1/ai/sql/executions/<AUDIT_ID>

# 6. 结果读取
curl -sS \
  -H "Authorization: Bearer <TOKEN>" \
  "http://127.0.0.1:60801/api/v1/ai/sql/executions/<AUDIT_ID>/result?limit=100"
```

验收 SQL：
```sql
-- 验证 audit 完整链路
SELECT
    a.id, a.session_id, a.message_id, a.result_message_id,
    a.instance_id, a.preview_safety_status, a.execution_safety_status,
    a.execution_status, a.collector_run_id, a.collector_run_item_id,
    a.awx_job_id, a.row_count, a.duration_ms,
    a.error_message, a.executed_at, a.completed_at
FROM dbops.ai_sql_audit a
ORDER BY a.id DESC LIMIT 20;

-- 验证 Chat 消息链路
SELECT id, session_id, role, message_type, status, parent_message_id, metadata_json, created_at
FROM dbops.ai_chat_message
WHERE session_id = <SESSION_ID>
ORDER BY id;
```

### 21.4 通过标准

C16 第二部分完成必须同时满足：

1. `Chat.vue(boundInstanceId)` 是主入口
2. 自然语言问题能生成 SQL Preview 卡片
3. Preview 卡片安全通过后才能执行
4. Execute 走 AWX `DB_READONLY_SQL_EXEC`
5. callback 能更新 `ai_sql_audit`
6. callback 能写入唯一 `sql_result` message
7. `ai_sql_audit.awx_job_id` 和 `result_message_id` 均可见
8. 刷新 Chat 后结果卡片仍可恢复
9. **PostgreSQL + Oracle + SQL Server** 三种 DB 的 E2E 全部通过
10. Schema Snapshot SQL 模板在三种 DB 上均可正常执行
11. sqlglot `validate_with_ast` 在三种方言下测试全过
12. 第三部分巡检 AI 代码和计划不受影响

### 21.5 推荐开工顺序

```text
F1 awx_job_id 回填
  → F0 Oracle/SQL Server Schema Snapshot 模板（§4.4 新增 SQL 模板 + Builder 分发 + sqlglot 方言测试）
  → F6 三种 DB 测试实例补齐（PG + Oracle + SQL Server）
  → Chat boundInstanceId 合同（后端 session context + 前端 Chat mode 分流）
  → Preview API 重构为 Chat 入口（三种 DB 均通过 Preview + AST 校验）
  → Chat Preview Card 前端（boundInstanceId 模式发送 + 卡片渲染）
  → Execute/Result Card 闭环（三种 DB 均通过 E2E）
```

### 21.6 C16 新 Commit 顺序

| # | Commit | 内容 |
|---|--------|------|
| 1 | C16-F1 | awx_job_id 回填（backend: ai_sql_execute/callback）+ 幂等测试 + docs |
| 2 | C16-F0 | Oracle/SQL Server Schema Snapshot 支持（3 种 SQL 模板 + `_AiSchemaMetadataBuilder` 按 `db_type_code` 分发 + sqlglot 3 方言测试通过 + capabilities `sql_supported_db_types` 扩展） |
| 3 | C16-F6 | 三种 DB 测试实例补齐（PG `appdb_dev` + Oracle/SQL Server dev 实例 + DBOPS 资产注册 + Schema Snapshot 采集验证） |
| 4 | C16-F2a | Chat boundInstanceId 合同（backend: session context / request schema + frontend: Chat mode 分流基础） |
| 5 | C16-F2b | Preview API 重构为 Chat 入口（session_id + client_request_id + run_sql_workflow inputs 固化 + 写 user+preview 双消息 + 三种 DB 均支持） |
| 6 | C16-F2c | Chat Preview Card 前端（boundInstanceId 模式发送消息走 preview + SQL Preview Card 渲染 + rejected 状态展示） |
| 7 | C16-F2d | Execute + Result Card 闭环（execute 状态返回 result_message_id/awx_job_id + 3s polling + result card refresh + callback 幂等 + 三种 DB E2E） |

### 21.7 文件变更清单（C16 第二部分）

#### 后端

```text
backend/app/api/ai.py                          — preview/execute/executions 端点增强
backend/app/schemas/ai.py                      — ChatSqlPreviewRequest/ChatSqlPreviewResponse
backend/app/services/dify_service.py           — run_sql_workflow inputs 固化
backend/app/services/ai/ai_sql_preview_service.py  — 重构为 Chat 可调用入口
backend/app/services/ai/ai_sql_execute_service.py  — awx_job_id 回填 + 执行校验
backend/app/services/ai/ai_sql_callback_service.py — callback 幂等 guard
backend/app/services/ai/ai_schema_context_service.py — build_schema_context 增强
backend/app/services/ai_chat_service.py        — session boundInstanceId 支持
backend/app/models/ai.py                       — AiChatSession metadata_json 存 bound context
```

#### 前端

```text
frontend/src/views/ai/Chat.vue                 — boundInstanceId 模式 + 消息分流 + 轮询
frontend/src/views/ai/SqlPreview.vue           — 保留为 audit 详情/深链页（非主入口）
frontend/src/components/ai/ChatMessageBubble.vue — sql_preview_link/sql_result 卡片增强
frontend/src/api/ai.ts                         — 新增 preview/execute/executions 调用
frontend/src/types/ai.ts                       — ChatMode / ChatSessionContext 类型
frontend/src/views/InstanceDetail.vue          — 「AI 查询」入口按钮
```

#### Playbook（原则上 C16 不再重改，除非现场确认 callback 字段丢失）

```bash
grep -R "business_domain.*ai_sql\|DB_READONLY_SQL_EXEC\|business_context" -n ansible-playbooks
```

#### 文档

```text
docs/10-module-map.md
docs/30-runbook.md
docs/40-tech-debt.md
docs/db/schema-snapshot.md
docs/contracts/api-inventory.md
.claude/plans/phase-3-6-progress-2026-06-30-c16.md
```

### 21.8 风险提示

> ❗Dangerous：禁止在生产实例上测试 AI SQL Execute。只读 SQL 也可能造成大表扫描、慢查询、连接耗尽或审计风险。Oracle/SQL Server 只允许使用已有 dev/test 环境实例。
>
> ❗Dangerous：禁止把 Dify 输出 SQL 直接下发 AWX。必须执行后端 AST 二次校验，并且只使用 `approved_sql`。
>
> ❗Dangerous：禁止让前端提交 `schema_context`、`allowed_tables`、`approved_sql`。这些必须由后端从当前 Snapshot 和策略中生成。

### 21.9 第三部分 Inspection AI 补充优化

Phase 3.6C 巡检 AI 分析（C22-C32 收尾）主计划保持不变，以下为 P0 必须补入的优化项。

#### P0-5：Report AI Analysis 执行方式（202 + BackgroundTasks）

问题：原 plan `DIFY_REPORT_TIMEOUT_SECONDS=120`，API 同步等待 Dify，前端和网关容易超时。

推荐方案：
```text
Inspection AI Analysis 执行方式：

1. POST /inspection/reports/{id}/ai-analysis 只创建 pending analysis
2. 立即返回 202 + analysis_id
3. 后端使用 FastAPI BackgroundTasks 执行 Dify workflow
4. BackgroundTask 内必须重新创建 DB Session，禁止复用请求 session
5. 前端每 3 秒轮询 GET /inspection/reports/{id}/ai-analysis
6. 进程重启或任务丢失时，由启动 stale cleanup 将 pending 超时记录标记 failed
```

> 如果首版不引入 BackgroundTasks，则必须写明：首版采用 blocking 请求，前端请求超时必须大于 `DIFY_REPORT_TIMEOUT_SECONDS + 30`，生成期间按钮 loading，不做后台轮询。

#### P0-6：source_data_hash 规范化

问题：原 plan 写了 `source_data_hash + workflow_version` 但未定义 hash 规则。同一份报告可能因时间字段、排序不同导致缓存失效。

计算规则：
```text
source_data_hash 计算规则：

1. 只包含影响 AI 分析结论的字段
2. 排除 created_at、updated_at、generated_at、exported_at 等易变时间字段
3. JSON 使用 canonical dumps：
   - sort_keys=true
   - separators=(',', ':')
   - ensure_ascii=false
4. 列表按稳定键排序：
   - abnormal_results 按 severity DESC, result_code ASC, target_id ASC
   - failed_results 按 result_code ASC, target_id ASC
   - top_risks 按 risk_level DESC, result_code ASC
5. hash 算法固定 SHA-256
```

Python 实现：
```python
import hashlib
import json

def stable_hash(payload: dict) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
```

#### P1-5：Review 只允许 current ready 变更

```text
review endpoint 规则：

1. 只允许 status='ready' 且 is_current=true 的 analysis 标记 reviewed
2. reviewed 后仍保持 is_current=true
3. 非 current 历史版本不允许 review，返回 409 analysis_not_current
4. reviewed 版本如果 source_data_hash 变化，旧 reviewed 保留历史，新分析重新生成 pending
```

#### P1-6：DOCX AI 章节文本清洗

Dify 输出虽要求 JSON，但写入 DOCX 前仍建议做文本清洗：

```text
DOCX AI 章节写入规则：

1. 不渲染 HTML
2. 不解析 Markdown
3. 所有字段按纯文本写入
4. recommendations/root_causes 最多写入 plan 约定数量
5. analysis_id、analysis_version、workflow_version 写入文档元数据
```

### 21.10 P0 优化项汇总（8 项，已全部补入 plan）

| # | 优化项 | 位置 | 说明 |
|---|--------|------|------|
| P0-1 | 统一当前状态，删除旧"待实现 Execute"表述 | §0 | 新增 §0.0 已完成 + §0.1 剩余主线 |
| P0-2 | Dify I/O 契约写入 plan | §3b | 新增 §3b.1-3b.4：平台原则 + sql-generator outputs + report-analyzer outputs + 字段校验 |
| P0-3 | Dify Code 节点强校验写入 plan | §5b | 新增 §5b.1-5b.2：sql-generator 13 条 + report-analyzer 9 条 |
| P0-4 | Chat 绑定实例提升为实体字段 | §21.2 + §2.1 | chat_mode + bound_instance_id DDL；不再只靠 metadata_json |
| P0-5 | capabilities 统一三库支持 | §11 | sql_supported_db_types: ["POSTGRESQL", "ORACLE", "MSSQL"] |
| P0-6 | Inspection AI Analysis → 202 + BackgroundTasks | §8 | 禁止同步等待 Dify 120s；禁止复用请求 DB Session |
| P0-7 | source_data_hash 规范化 | §8 | canonical JSON + SHA-256 + 排除易变字段 + 列表稳定排序 + Python 代码 |
| P0-8 | SQL Result 独立 API 作为硬性验收 | §21.3 C16-5 | GET /executions/{audit_id}/result + 权限规则 + 分页规则 |

### 21.11 P1 优化项汇总（7 项，已全部补入 plan）

| # | 优化项 | 位置 | 说明 |
|---|--------|------|------|
| P1-1 | Commit 顺序改成当前真实顺序 | §14 | 压缩为 9 步剩余 commit，删旧 C16-C21 strikethrough |
| P1-2 | Dify YAML 变更放"外部配置依赖" | §3b.1 | Dify 平台手工发布不进 plan；后端只依赖 I/O 契约 |
| P1-3 | Preview rejected 也写 audit | §21.3 C16-3 | rejected 也写入 ai_sql_audit，便于审计追溯 |
| P1-4 | 输入字段长度限制补全 | §21.3 C16-3 | user_question≤2000, max_rows 1~500, explain≤4000, generated_sql≤20000, summary_json≤200000 等 |
| P1-5 | Review 只允许 current ready | §8 | 历史版本 review 返回 409 analysis_not_current |
| P1-6 | DOCX AI 纯文本写入 | §8b | 不渲染 HTML/Markdown，固定写入追溯元数据 |
| P1-7 | 测试矩阵补 Dify Code 节点契约用例 | §13 | sql-generator 10 条 + report-analyzer 8 条 + 输入限制 6 条
