"""
AI Copilot API（Phase 3.6）

C1 范围：GET /api/v1/ai/capabilities
C3 范围追加：Chat CRUD/Send/History（4 端点）
C10 范围追加：Schema Snapshot collect/status/history/context（4 端点）
C12 范围追加：SQL Preview（POST /ai/sql/preview）
后续 commit 追加：
- C19: SQL Execute/Executions
- C24-C25: Inspection AI Analysis
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
    AiSchemaContextResponse,
    AiSchemaSnapshotCollectRequest,
    AiSchemaSnapshotCollectResponse,
    AiSchemaSnapshotListResponse,
    AiSchemaSnapshotResponse,
    AiSqlAuditResponse,
    AiSqlPreviewRequest,
    AiSqlPreviewResponse,
)
from app.services.ai.ai_schema_context_service import AiSchemaContextService
from app.services.ai.ai_schema_snapshot_service import (
    AiSchemaSnapshotService,
    AwxLaunchError,
    FeatureDisabledError,
    InstanceNotFoundError,
    UnsupportedDbTypeError,
)
from app.services.ai.ai_sql_preview_service import (
    AiSqlPreviewService,
    DifyTimeoutError_,
    DifyUnavailableError,
    DifyWorkflowFailedError_,
    SnapshotUnavailableError,
    UnsupportedDbTypeError as SqlUnsupportedDbTypeError,
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


# -----------------------------------------------------------------------------
# C10: Schema Snapshot — Collect / Status / History / Context
# -----------------------------------------------------------------------------
@router.post(
    "/sql/schema-snapshots/{instance_id}/collect",
    response_model=AiSchemaSnapshotCollectResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_schema_snapshot_collection(
    instance_id: int,
    payload: AiSchemaSnapshotCollectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSchemaSnapshotCollectResponse:
    """触发 instance 的 schema metadata 采集（plan §4.1）。

    返回 202 Accepted + CollectorRun 元数据。Callback 通过
    ``business_domain='ai_schema'`` 路由到 ``AiSchemaSnapshotCallbackService``
    落库；前端拿到 collector_run_id 后通过 GET status 轮询。

    错误码（plan §11）：
    - 404 — instance 不存在
    - 422 — db_type 不在 capabilities 支持范围
    - 502 — AWX launch 失败
    - 503 — AI_SQL_PREVIEW_ENABLED=false
    """
    try:
        result = AiSchemaSnapshotService.trigger_collection(
            db,
            instance_id=instance_id,
            database_name=payload.database_name,
            requested_by=current_user.username,
            request_base_url=str(request.base_url),
        )
    except InstanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except UnsupportedDbTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AwxLaunchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return AiSchemaSnapshotCollectResponse(**result)


@router.get(
    "/sql/schema-snapshots/{instance_id}",
    response_model=AiSchemaSnapshotListResponse,
)
def get_schema_snapshot_status(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSchemaSnapshotListResponse:
    """返回该 instance 最新 snapshot（is_current 优先，否则最新任意状态）。

    返回 items 长度为 0 或 1：0 表示从未采集；1 表示有 snapshot（含
    pending/running/failed），前端根据 ``status`` 字段渲染不同 UI。
    """
    snapshot = AiSchemaSnapshotService.get_latest_any_status(
        db,
        instance_id=instance_id,
        database_name=database_name,
    )
    items = [AiSchemaSnapshotResponse.model_validate(snapshot)] if snapshot is not None else []
    return AiSchemaSnapshotListResponse(items=items, total=len(items))


@router.get(
    "/sql/schema-snapshots/{instance_id}/history",
    response_model=AiSchemaSnapshotListResponse,
)
def list_schema_snapshot_history(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSchemaSnapshotListResponse:
    """返回历史 snapshot 列表（created_at DESC）。

    包含 pending/running/failed/success；前端按需过滤。
    """
    items, total = AiSchemaSnapshotService.list_history(
        db,
        instance_id=instance_id,
        database_name=database_name,
        limit=limit,
    )
    return AiSchemaSnapshotListResponse(
        items=[AiSchemaSnapshotResponse.model_validate(o) for o in items],
        total=total,
    )


@router.get(
    "/sql/schema-snapshots/{instance_id}/context",
    response_model=AiSchemaContextResponse,
)
def get_schema_context(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSchemaContextResponse:
    """实时构建 Dify 用的 schema_context + schema_policy_hash (plan §4.6)。

    available=false 时仅 ``reason`` + ``instance_id`` + ``db_type_code`` 有意义。
    """
    result = AiSchemaContextService.build_schema_context(
        db,
        instance_id=instance_id,
        database_name=database_name,
    )
    return AiSchemaContextResponse(**result)


# -----------------------------------------------------------------------------
# C12: SQL Preview
# -----------------------------------------------------------------------------
@router.post(
    "/sql/preview",
    response_model=AiSqlPreviewResponse,
)
def preview_sql(
    payload: AiSqlPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSqlPreviewResponse:
    """SQL Preview（plan §5.2 + §5.3 + §6.5）。

    流程：
      1. 校验 instance + db_type capability
      2. 取 is_current snapshot 的 schema_policy
      3. 调 Dify sql-generator workflow → generated_sql
      4. 调 SqlSafetyService.validate_with_ast（sqlglot） → approved_sql
      5. 落 ai_sql_audit（passed / rejected 都落库）

    preview_safety_status='passed' 时返回 approved_sql + approved_sql_hash
    + schema_snapshot_id + schema_policy_hash — Execute 阶段（C17-C19）会
    校验这些字段一致。审计行 ``audit_id`` 在 passed/rejected 都返回，用于
    后续 Execute 引用。

    错误码（plan §11）：
    - 404 — instance 不存在
    - 409 — Schema snapshot 不可用（pending/running/failed/expired/no_snapshot）
    - 422 — db_type 不在 capabilities 支持范围
    - 502 — Dify 不可用 / 网络错误 / Workflow 失败
    - 503 — AI_SQL_PREVIEW_ENABLED=false
    - 504 — Dify 调用超时

    注意：本端点是**有状态**的，每次调用都落 audit 行；前端需自行去重（UI 防抖）。
    """
    try:
        result = AiSqlPreviewService.preview(
            db,
            instance_id=payload.instance_id,
            database_name=payload.database_name,
            user_question=payload.user_question,
            session_id=payload.session_id,
            message_id=payload.message_id,
            current_page=payload.current_page,
            requested_by=current_user,
        )
    except InstanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SqlUnsupportedDbTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SnapshotUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "snapshot_unavailable",
                "reason": exc.reason,
                "message": str(exc),
            },
        )
    except DifyTimeoutError_ as exc:
        raise HTTPException(status_code=504, detail=f"Dify timeout: {exc}")
    except (DifyUnavailableError, DifyWorkflowFailedError_) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except DifyError as exc:
        logger.warning("Dify SQL preview failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Dify error: {exc}")

    audit = result.audit
    # errors 是 list — Pydantic 直接接受
    errors_list = getattr(audit, "_preview_errors", []) or []
    warnings_list: list[str] = []
    # warnings 已序列化到 preview_safety_reason（不重复返回）

    return AiSqlPreviewResponse(
        audit_id=int(audit.id),
        preview_safety_status=audit.preview_safety_status,
        generated_sql=audit.generated_sql,
        generated_sql_hash=audit.generated_sql_hash,
        approved_sql=audit.approved_sql,
        approved_sql_hash=audit.approved_sql_hash,
        preview_safety_reason=audit.preview_safety_reason,
        errors=list(errors_list),
        warnings=list(warnings_list),
        schema_snapshot_id=audit.schema_snapshot_id,
        schema_policy_hash=audit.schema_policy_hash,
        db_type_code=audit.db_type_code,
        sql_dialect=AiSchemaContextService._dialect_for(audit.db_type_code),
        sql_workflow_version=audit.sql_workflow_version,
        safety_policy_version=audit.safety_policy_version,
        dify_workflow_run_id=audit.dify_workflow_run_id,
        previewed_at=audit.previewed_at,
    )
