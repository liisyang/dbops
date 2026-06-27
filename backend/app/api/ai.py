"""
AI Copilot API（Phase 3.6）

C1 范围：GET /api/v1/ai/capabilities
C3 范围追加：Chat CRUD/Send/History（4 端点）
后续 commit 追加：
- C10: Schema Snapshot collect/status
- C13: SQL Preview
- C19: SQL Execute/Executions
- C24-C25: Inspection AI Analysis
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.user import User
from app.schemas.ai import (
    AiChatMessageListResponse,
    AiChatMessageResponse,
    AiChatMessageSendRequest,
    AiChatSessionCreateRequest,
    AiChatSessionListResponse,
    AiChatSessionResponse,
    AiChatSendResponse,
)
from app.services.ai_chat_service import (
    AiChatService,
    ChatConcurrentPendingError,
    ChatDifyTimeoutError,
    ChatDifyUnavailableError,
    ChatFeatureDisabledError,
    ChatSessionNotFoundError,
)
from app.services.dify_service import DifyError

logger = logging.getLogger(__name__)


router = APIRouter()


# =============================================================================
# Capabilities 响应模型
# =============================================================================
class CapabilitiesResponse(BaseModel):
    """AI Copilot 能力声明（plan §11）。

    严禁返回 API Key、Dify URL、内部模型配置等敏感信息。
    前端根据能力隐藏/禁用对应 UI 元素。
    """

    chat_enabled: bool
    sql_preview_enabled: bool
    sql_execution_enabled: bool
    report_analysis_enabled: bool
    report_export_ai_enabled: bool
    stream_enabled: bool
    sql_supported_db_types: list[str]


# =============================================================================
# 端点
# =============================================================================
@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_ai_capabilities() -> CapabilitiesResponse:
    """返回 AI Copilot 当前可用能力。

    设计原则（plan §11）：
    - 任何用户（包括未登录）都可以查询 capabilities
    - 仅声明 ON/OFF 与支持的方言，不暴露内部配置
    - 前端启动时拉取一次，灰度菜单按钮
    """
    s = get_settings()
    return CapabilitiesResponse(
        chat_enabled=s.AI_CHAT_ENABLED,
        sql_preview_enabled=s.AI_SQL_PREVIEW_ENABLED,
        sql_execution_enabled=s.AI_SQL_EXECUTION_ENABLED,
        report_analysis_enabled=s.AI_REPORT_ANALYSIS_ENABLED,
        report_export_ai_enabled=s.AI_REPORT_EXPORT_AI_ENABLED,
        stream_enabled=False,  # 首版不实现 SSE/打字流
        sql_supported_db_types=s.sql_supported_db_types,
    )


# -----------------------------------------------------------------------------
# Chat — Session CRUD
# -----------------------------------------------------------------------------
@router.post(
    "/chat/sessions",
    response_model=AiChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(
    payload: AiChatSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatSessionResponse:
    """创建新会话（user 维度）。

    Returns:
        201 Created + 新会话响应

    Notes:
        - 不要求 AI_CHAT_ENABLED（先建会话，再尝试发送时再校验开关）
        - 但 Dify 未配置时仍允许建会话（plan §11: send_message 才报 502）
    """
    obj = AiChatService.create_session(db, user=current_user, title=payload.title)
    db.commit()
    db.refresh(obj)
    return AiChatSessionResponse.model_validate(obj)


@router.get(
    "/chat/sessions",
    response_model=AiChatSessionListResponse,
)
def list_chat_sessions(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatSessionListResponse:
    """列出当前用户的会话（最近优先）。"""
    items, total = AiChatService.list_sessions(db, user=current_user, limit=limit)
    return AiChatSessionListResponse(
        items=[AiChatSessionResponse.model_validate(o) for o in items],
        total=total,
    )


# -----------------------------------------------------------------------------
# Chat — Messages
# -----------------------------------------------------------------------------
@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=AiChatSendResponse,
)
def send_chat_message(
    session_id: int,
    payload: AiChatMessageSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatSendResponse:
    """发送消息（核心端点）。

    幂等性：相同 `client_request_id` 重复请求会返回首次结果（idempotent_replay=true）。

    错误码（plan §11）：
    - 404 — session 不存在或不属于当前用户
    - 409 — session 已有 assistant pending 在有效期内
    - 422 — 参数校验失败（由 Pydantic 处理）
    - 502 — Dify 不可用或返回错误
    - 503 — AI_CHAT_ENABLED=false
    - 504 — Dify 调用超时
    """
    try:
        result = AiChatService.send_message(
            db,
            session_id=session_id,
            user=current_user,
            payload=payload,
        )
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChatConcurrentPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ChatFeatureDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ChatDifyUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ChatDifyTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except DifyError as exc:
        # 其他 Dify 错误 → 502
        logger.warning("Dify chat call failed session=%s: %s", session_id, exc)
        raise HTTPException(status_code=502, detail=f"Dify error: {exc}")

    return AiChatSendResponse(
        user_message=AiChatMessageResponse.model_validate(result.user_message),
        assistant_message=AiChatMessageResponse.model_validate(result.assistant_message)
        if result.assistant_message is not None
        else None,
        idempotent_replay=result.idempotent_replay,
    )


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=AiChatMessageListResponse,
)
def list_chat_messages(
    session_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatMessageListResponse:
    """列出会话消息历史（按 created_at ASC）。

    错误码：
    - 404 — session 不存在或不属于当前用户
    """
    try:
        items, total = AiChatService.list_messages(
            db,
            session_id=session_id,
            user=current_user,
            limit=limit,
        )
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return AiChatMessageListResponse(
        items=[AiChatMessageResponse.model_validate(o) for o in items],
        total=total,
    )
