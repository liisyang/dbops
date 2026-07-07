"""
AI Copilot Pydantic Schemas（Phase 3.6）

C2 范围：Chat 部分（ai_chat_session + ai_chat_message）
C6 范围：SQL Schema Snapshot
C10 范围：Schema Snapshot API（POST collect / GET status / GET history / GET context）
C12 范围：SQL Preview（POST /ai/sql/preview + Audit 响应）
C16-F3 范围：Object Metadata Snapshot API（POST collect / GET status / GET history / GET context）
后续 commit 追加：
- C19: SQL Execute
- C24-C25: Inspection AI Analysis
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Chat — Session
# =============================================================================
# C16-F2a：Chat 模式枚举（plan §21.2）
# - general:       普通多轮 Chat，调用 /ai/chat/sessions/{id}/messages
# - instance_sql:  实例绑定 SQL Copilot，调用 /ai/sql/preview
ChatMode = Literal["general", "instance_sql"]
ALL_CHAT_MODES = ("general", "instance_sql")


class AiChatSessionCreateRequest(BaseModel):
    """创建新会话的请求（前端在用户首次发消息时调用）。

    C16-F2a 新增字段（plan §21.2）：
    - mode:              'general'（普通多轮）或 'instance_sql'（实例绑定 SQL Copilot）
    - bound_instance_id: 当 mode='instance_sql' 时必填
                         当 mode='general' 时必须不传（传了 422）
    - source_page:       辅助信息（落 metadata_json），不影响行为

    互斥规则（service 层兜底）：
    1. mode='general'       → bound_instance_id 必须 NULL
    2. mode='instance_sql'  → bound_instance_id 必须 NOT NULL
    3. bound_instance_id 必须存在且 is_active=True
    4. 已存在同 user+mode+bound_instance_id 的未删除 session 时优先复用
    """

    title: Optional[str] = Field(default=None, max_length=200, description="可选会话标题")
    mode: ChatMode = Field(
        default="general",
        description="Chat 模式：general（普通多轮）/ instance_sql（实例绑定 SQL Copilot）",
    )
    bound_instance_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="实例 ID（mode='instance_sql' 时必填；mode='general' 时必须 NULL）",
    )
    source_page: Optional[str] = Field(
        default=None,
        max_length=100,
        description="来源页面（落 metadata_json；不影响行为）",
    )


class AiChatSessionResponse(BaseModel):
    """会话响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_code: str
    user_id: Optional[UUID] = None
    title: str
    dify_conversation_id: Optional[str] = None
    model_provider: str
    message_count: int
    last_message_at: Optional[datetime] = None
    # C16-F2a：返回 chat_mode + bound_instance_id 让前端可路由入口
    chat_mode: ChatMode = "general"
    bound_instance_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AiChatSessionListResponse(BaseModel):
    """会话列表响应。"""

    items: list[AiChatSessionResponse]
    total: int


# =============================================================================
# Chat — Message
# =============================================================================
class AiChatMessageSendRequest(BaseModel):
    """发送消息请求（前端调用的核心端点）。

    关键字段：
    - client_request_id: 前端生成的 UUID，用于幂等（同一 UUID 重复请求会返回已有结果）
    - current_page: 白名单内的页面标识（ai_chat / inspection_report / ...）
    """

    client_request_id: UUID = Field(description="前端生成的 UUID，用于幂等")
    query: str = Field(min_length=1, max_length=8000, description="用户消息文本")
    current_page: Optional[str] = Field(default="ai_chat", max_length=100, description="当前页面（白名单）")


class AiChatMessageResponse(BaseModel):
    """单条消息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    user_id: Optional[UUID] = None
    client_request_id: Optional[UUID] = None
    role: Literal["user", "assistant", "system"]
    message_type: Literal["chat", "sql_preview", "sql_result", "error"]
    status: Literal["pending", "completed", "failed", "stale"]
    content: Optional[str] = None
    parent_message_id: Optional[int] = None
    # 字段名 metadata_json 而非 metadata：避免与 SQLAlchemy Base.metadata 保留属性冲突
    # （ORM 中 Python 属性 metadata_json 映射到 DB 列 metadata — 见 app/models/ai.py:111）
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    dify_task_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    elapsed_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_expires_at: Optional[datetime] = None
    attempt_count: int
    created_at: datetime
    updated_at: datetime


class AiChatMessageListResponse(BaseModel):
    """消息历史响应。"""

    items: list[AiChatMessageResponse]
    total: int


class AiChatSendResponse(BaseModel):
    """发送消息响应（同时返回 user + assistant 两条消息）。

    assistant_message 在极端情况下为 None（同一 client_request_id 命中历史 user message
    但 assistant 消息未创建 — 例如事务 1 中途异常）。前端应判断后展示。
    """

    user_message: AiChatMessageResponse
    assistant_message: Optional[AiChatMessageResponse] = None
    idempotent_replay: bool = Field(default=False, description="是否幂等命中（client_request_id 已存在）")


# =============================================================================
# C6: SQL Schema Snapshot
# =============================================================================
class AiSchemaSnapshotResponse(BaseModel):
    """数据库结构快照响应（C10 端点会复用此 schema）。

    关键设计（避免 BE-bug1 复发）：
    - 不使用 Field alias：Python 属性名 == JSON key，Pydantic from_attributes=True
      默认按字段名取 ORM 属性，不触发 Base.metadata 保留属性冲突
    - 状态字段用 Literal 限定为五态机
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int
    db_type_code: str
    database_name: str
    schema_name: Optional[str] = None
    status: Literal["pending", "running", "success", "failed", "unavailable"]
    allowed_schemas: list[str] = Field(default_factory=list)
    allowed_tables: list[str] = Field(default_factory=list)
    allowed_columns: dict[str, list[str]] = Field(default_factory=dict)
    denied_columns: list[str] = Field(default_factory=list)
    is_current: bool
    collector_run_id: Optional[int] = None
    snapshot_hash: Optional[str] = None
    total_tables: Optional[int] = None
    total_columns: Optional[int] = None
    expires_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    collected_at: Optional[datetime] = None
    created_at: datetime


# =============================================================================
# C10: Schema Snapshot API
# =============================================================================
class AiSchemaSnapshotCollectRequest(BaseModel):
    """POST collect 请求。

    首版（plan §4.8 P1）只支持 PostgreSQL；前端无需传入 db_type_code，由后端
    根据 instance_id 派生。当前只允许指定数据库名（database_name），留空时
    fallback 到 '<default>'。
    """

    database_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="目标 database（留空时由 service 端 fallback 到 '<default>'）",
    )


class AiSchemaSnapshotCollectResponse(BaseModel):
    """POST collect 响应（plan §4.1）。

    返回 202 语义：collector_run 已创建，AWX 调度完成后通过 callback 落库。
    """

    detail: str
    collector_run_id: int
    run_id: str
    awx_job_id: Optional[int] = None
    awx_job_url: Optional[str] = None
    status: str
    item_count: int


class AiSchemaSnapshotListResponse(BaseModel):
    """GET status / GET history 列表响应。"""

    items: list[AiSchemaSnapshotResponse]
    total: int


class AiSchemaContextResponse(BaseModel):
    """GET context 响应（plan §4.6 build_schema_context）。

    available=false 时仅 ``reason`` + ``instance_id`` + ``db_type_code`` 有意义，
    其余字段为 None。前端据此展示「采集未完成 / 已过期 / 不支持」三种提示。
    """

    available: bool
    instance_id: int
    db_type_code: Optional[str] = None
    sql_dialect: Optional[str] = None
    schema_context: Optional[str] = None
    allowed_schemas: Optional[list[str]] = None
    allowed_tables: Optional[list[str]] = None
    allowed_columns: Optional[dict[str, list[str]]] = None
    denied_columns: Optional[list[str]] = None
    schema_snapshot_id: Optional[int] = None
    schema_policy_hash: Optional[str] = None
    snapshot_hash: Optional[str] = None
    collected_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    total_tables: Optional[int] = None
    total_columns: Optional[int] = None
    reason: Optional[str] = Field(default=None, description="available=false 时的原因码")


# =============================================================================
# C12: SQL Preview
# =============================================================================
class AiSqlPreviewRequest(BaseModel):
    """POST /ai/sql/preview 请求（plan §5.2 + §5.3）。

    关键字段：
    - instance_id: 目标实例；后端派生 db_type_code，前端不直接传
    - database_name: 可选；留空时 service fallback 到 '<default>'
    - user_question: 用户原始问题，传给 Dify sql-generator workflow
    - session_id / message_id: 可选；用于关联 ai_chat_session/message
      （直接调用 /ai/sql/preview 时可不带，由 Chat 集成时填充）
    - current_page: 白名单内的页面标识（ai_chat / instance_detail 等）
    """

    instance_id: int = Field(gt=0, description="目标 db_instance.id")
    database_name: Optional[str] = Field(
        default=None, max_length=200,
        description="目标 database（留空时由 service 端 fallback 到 '<default>'）",
    )
    user_question: str = Field(
        min_length=1, max_length=8000,
        description="用户原始问题，传给 Dify sql-generator workflow",
    )
    session_id: Optional[int] = Field(default=None, gt=0)
    message_id: Optional[int] = Field(default=None, gt=0)
    current_page: Optional[str] = Field(
        default="ai_chat", max_length=100,
        description="当前页面（白名单）；非法值降级为 ai_chat",
    )


class AiSqlPreviewResponse(BaseModel):
    """POST /ai/sql/preview 响应（plan §5.2 + §5.3 + §19 状态机）。

    preview_safety_status='passed' 时：
      - approved_sql + approved_sql_hash 必填（落 ai_sql_audit）
      - schema_snapshot_id + schema_policy_hash 必填（强绑定 snapshot）
      - audit_id 返回给前端供 Execute 阶段引用
    preview_safety_status='rejected' 时：
      - preview_safety_reason 必填（用户可见的错误描述）
      - errors 列表（AST 校验原始 error）
      - audit_id 仍可能返回（rejected 也落库用于审计）
    """

    # 核心结果
    audit_id: int = Field(description="ai_sql_audit.id，供后续 Execute 引用")
    preview_safety_status: Literal["passed", "rejected"]

    # 双轨 SQL
    generated_sql: Optional[str] = Field(
        default=None, description="Dify 生成的 SQL（审计追溯）"
    )
    generated_sql_hash: Optional[str] = Field(
        default=None, description="generated_sql 的 SHA-256"
    )
    approved_sql: Optional[str] = Field(
        default=None, description="AST 重写后的 SQL（Execute 权威）"
    )
    approved_sql_hash: Optional[str] = Field(
        default=None, description="approved_sql 的 SHA-256"
    )

    # 错误信息
    preview_safety_reason: Optional[str] = Field(
        default=None, description="rejected 时必填"
    )
    errors: list[str] = Field(
        default_factory=list, description="AST 校验 error 列表"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="AST 校验 warning 列表（如敏感列命中，由 Executor 在 fetch 时 mask）",
    )

    # Schema 强绑定
    schema_snapshot_id: Optional[int] = Field(
        default=None,
        description="preview 时绑定的 ai_sql_schema_snapshot.id（Execute 时校验 is_current）",
    )
    schema_policy_hash: Optional[str] = Field(
        default=None,
        description="preview 时绑定的策略 hash（Execute 时再次校验一致）",
    )

    # 元数据
    db_type_code: str = Field(description="目标 db 类型（POSTGRESQL 等）")
    sql_dialect: Optional[str] = Field(
        default=None, description="sqlglot 方言名（postgres / tsql / oracle / mysql）"
    )
    sql_workflow_version: Optional[str] = Field(
        default=None, description="DIFY_SQL_WORKFLOW_VERSION 配置值"
    )
    safety_policy_version: Optional[str] = Field(
        default=None, description="SQL 安全规则版本（plan §5）"
    )
    dify_workflow_run_id: Optional[str] = Field(
        default=None, description="Dify workflow_run_id（审计追溯）"
    )

    # 时间戳
    previewed_at: Optional[datetime] = None


class AiSqlAuditResponse(BaseModel):
    """ai_sql_audit 单行响应（GET /ai/sql/audits/{id} 用 — C17+ 实现）。

    当前 C12 不直接暴露 GET 端点；本 schema 供 service 层内部使用 + 后续
    commit 复用。设计原则（避免 BE-bug1 复发）：
    - 字段名 == JSON key，Pydantic from_attributes=True
    - 不使用 Field alias
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: Optional[int] = None
    message_id: Optional[int] = None
    result_message_id: Optional[int] = None
    user_id: Optional[UUID] = None

    instance_id: int
    db_type_code: str
    user_question: str

    generated_sql: Optional[str] = None
    generated_sql_hash: Optional[str] = None
    approved_sql: Optional[str] = None
    approved_sql_hash: Optional[str] = None

    preview_safety_status: Literal["passed", "rejected"]
    preview_safety_reason: Optional[str] = None

    execution_safety_status: Optional[Literal["passed", "rejected"]] = None
    execution_safety_reason: Optional[str] = None

    safety_policy_version: Optional[str] = None
    schema_snapshot_id: Optional[int] = None
    schema_policy_hash: Optional[str] = None

    dify_workflow_run_id: Optional[str] = None
    sql_workflow_version: Optional[str] = None

    previewed_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    execution_status: Literal[
        "not_requested", "pending", "running", "success",
        "failed", "timeout", "cancelled"
    ] = "not_requested"

    collector_run_id: Optional[int] = None
    collector_run_item_id: Optional[int] = None

    row_count: Optional[int] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


# =============================================================================
# C14: SQL Execute（plan §6 + §10）
# =============================================================================
class AiSqlExecuteRequest(BaseModel):
    """POST /v1/ai/sql/execute 请求（plan §6.1）。

    关键字段：
    - audit_id: 已 passed 状态的 audit 行 id（来自 Preview 阶段）
    - force: 强制重跑（pending/running 状态允许覆盖）。当前 C14 不区分角色，
      所有登录用户均可 force；后续 C15+ 可收紧到 admin only。
    """

    audit_id: int = Field(gt=0, description="已 passed 状态的 ai_sql_audit.id")
    force: bool = Field(
        default=False,
        description="强制重跑；仅当 audit.execution_status IN ('pending','running') 时生效",
    )


class AiSqlExecuteResponse(BaseModel):
    """POST /v1/ai/sql/execute 响应（plan §6.1）。

    返回 execution_status='running' 表示 AWX 已接单；'failed' 表示 launch
    失败（error_message 含 AWX 错误详情）。
    """

    audit_id: int
    execution_status: Literal[
        "not_requested", "pending", "running", "success",
        "failed", "timeout", "cancelled"
    ]
    awx_job_id: Optional[int] = Field(default=None, description="AWX job id（launch 成功才有）")
    awx_job_url: Optional[str] = Field(default=None, description="AWX 控制台链接")
    collector_run_id: Optional[int] = Field(default=None)
    collector_run_item_id: Optional[int] = Field(default=None)
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class AiSqlExecutionStatusResponse(BaseModel):
    """GET /v1/ai/sql/audit/{audit_id}/execution 响应（plan §6.1 — 前端轮询）。

    字段来自 ai_sql_audit（来自 ORM，Pydantic from_attributes=True）+ chat
    message_type='sql_result' 是否已落库。
    """

    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    execution_status: Literal[
        "not_requested", "pending", "running", "success",
        "failed", "timeout", "cancelled"
    ] = "not_requested"
    row_count: Optional[int] = None
    duration_ms: Optional[int] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    collector_run_id: Optional[int] = None
    awx_job_id: Optional[int] = None
    executed_at: Optional[datetime] = None
    # chat message 关联（callback 写库后才有）
    result_message_id: Optional[int] = None
    message_type: Optional[Literal["sql_result"]] = None

    created_at: datetime


# =============================================================================
# C16-F3: Object Metadata Snapshot API
# =============================================================================
class AiObjectMetadataCollectRequest(BaseModel):
    """POST collect 请求（F3 plan §4.1）。

    首版（plan §4.8 P1）只支持 PostgreSQL；前端无需传入 db_type_code，由后端
    根据 instance_id 派生。database_name / schema_name 留空时分别 fallback 到
    '<default>'。F3 与 C6 (Schema Snapshot) 区别：F3 多了 schema_name 维度
    （DDL 粒度比 column 级 schema 更细）。
    """

    database_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="目标 database（留空时由 service 端 fallback 到 '<default>'）",
    )
    schema_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="目标 schema（留空时由 service 端 fallback 到 '<default>'）",
    )


class AiObjectMetadataCollectResponse(BaseModel):
    """POST collect 响应（F3 plan §4.1）。

    返回 202 语义：collector_run 已创建，AWX 调度完成后通过 callback 落库。
    """

    detail: str
    collector_run_id: int
    run_id: str
    awx_job_id: Optional[int] = None
    awx_job_url: Optional[str] = None
    status: str
    item_count: int


class AiObjectMetadataSnapshotItemResponse(BaseModel):
    """单条 ai_object_metadata_snapshot 响应（C10 schema 风格复用）。

    关键设计（避免 BE-bug1 复发）：
    - 不使用 Field alias：Python 属性名 == JSON key
    - 状态字段用 Literal 限定为五态机
    - 数量统计字段（table_count / view_count / index_count / function_count /
      total_object_count）必填 — service 层写入时已 server_default='0'，即便
      failed 行也有值
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int
    db_type_code: str
    database_name: str
    schema_name: str
    status: Literal["pending", "running", "success", "failed", "unavailable"]
    is_current: bool
    table_count: int
    view_count: int
    index_count: int
    function_count: int
    total_object_count: int
    object_ddl_sha256: Optional[str] = None
    snapshot_hash: Optional[str] = None
    expires_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    collected_at: Optional[datetime] = None
    created_at: datetime


class AiObjectMetadataListResponse(BaseModel):
    """GET status / GET history 列表响应。"""

    items: list[AiObjectMetadataSnapshotItemResponse]
    total: int


class AiObjectMetadataContextResponse(BaseModel):
    """GET context 响应（F3 plan §4.6 — 实时构建 object_ddl_text）。

    字段说明：
    - available: 是否有已发布的 success snapshot
    - object_ddl_text: 完整 DDL 文本（可能 1MB 截断，前端按需展示）
    - counts: 各类对象数量（table / view / index / function）
    - reason: available=false 时的原因码（no_snapshot / snapshot_not_success /
      snapshot_expired / snapshot_not_current）

    available=false 时仅 ``reason`` + ``instance_id`` + ``database_name`` +
    ``schema_name`` 有意义，其余字段为 None。
    """

    available: bool
    instance_id: int
    db_type_code: Optional[str] = None
    database_name: str
    schema_name: str
    object_ddl_text: Optional[str] = None
    object_ddl_sha256: Optional[str] = None
    table_count: Optional[int] = None
    view_count: Optional[int] = None
    index_count: Optional[int] = None
    function_count: Optional[int] = None
    total_object_count: Optional[int] = None
    snapshot_id: Optional[int] = None
    snapshot_hash: Optional[str] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(default=None, description="available=false 时的原因码")

