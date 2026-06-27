"""
AI Copilot Pydantic Schemas（Phase 3.6）

C2 范围：Chat 部分（ai_chat_session + ai_chat_message）
后续 commit 追加：
- C6/C13: SQL Schema Snapshot + Preview
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
    metadata_json: dict[str, Any] = Field(default_factory=dict, alias="metadata")
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
    """发送消息响应（同时返回 user + assistant 两条消息）。"""

    user_message: AiChatMessageResponse
    assistant_message: AiChatMessageResponse
    idempotent_replay: bool = Field(default=False, description="是否幂等命中（client_request_id 已存在）")
