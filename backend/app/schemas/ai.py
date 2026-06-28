"""
AI Copilot Pydantic Schemas（Phase 3.6）

C2 范围：Chat 部分（ai_chat_session + ai_chat_message）
C6 范围：SQL Schema Snapshot
C10 范围：Schema Snapshot API（POST collect / GET status / GET history / GET context）
后续 commit 追加：
- C13: SQL Preview
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
class AiChatSessionCreateRequest(BaseModel):
    """创建新会话的请求（前端在用户首次发消息时调用）。"""

    title: Optional[str] = Field(default=None, max_length=200, description="可选会话标题")


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
