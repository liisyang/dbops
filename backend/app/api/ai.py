"""
AI Copilot API（Phase 3.6）

C1 范围：GET /api/v1/ai/capabilities
C3 范围追加：Chat CRUD/Send/History（4 端点）
C10 范围追加：Schema Snapshot collect/status/history/context（4 端点）
C12 范围追加：SQL Preview（POST /ai/sql/preview）
C14 范围追加：SQL Execute（POST /ai/sql/execute + GET /ai/sql/audit/{id}/execution）
C16-F3 范围追加：Object Metadata collect/status/history/context（4 端点）
后续 commit 追加：
- C16: Inspection AI Analysis
- C17: Report AI Export
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
    AiObjectMetadataCollectRequest,
    AiObjectMetadataCollectResponse,
    AiObjectMetadataContextResponse,
    AiObjectMetadataListResponse,
    AiObjectMetadataSnapshotItemResponse,
    AiSchemaContextResponse,
    AiSchemaSnapshotCollectRequest,
    AiSchemaSnapshotCollectResponse,
    AiSchemaSnapshotListResponse,
    AiSchemaSnapshotResponse,
    AiSqlAuditResponse,
    AiSqlExecuteRequest,
    AiSqlExecuteResponse,
    AiSqlExecutionStatusResponse,
    AiSqlPreviewRequest,
    AiSqlPreviewResponse,
)
from app.services.ai.ai_object_metadata_snapshot_service import (
    AiObjectMetadataSnapshotService,
    AwxLaunchError as ObjectMetadataAwxLaunchError,
    FeatureDisabledError as ObjectMetadataFeatureDisabledError,
    InstanceNotFoundError as ObjectMetadataInstanceNotFoundError,
    UnsupportedDbTypeError as ObjectMetadataUnsupportedDbTypeError,
)
from app.services.ai.ai_schema_context_service import AiSchemaContextService
from app.services.ai.ai_schema_snapshot_service import (
    AiSchemaSnapshotService,
    AwxLaunchError,
    FeatureDisabledError,
    InstanceNotFoundError,
    UnsupportedDbTypeError,
)
from app.services.ai.ai_sql_execute_service import (
    AiSqlExecuteService,
    AuditAlreadyRunningError,
    AuditNotFoundError,
    AuditNotPassedError,
    AuditUnsafeOnExecuteError,
    AwxLaunchError as AiSqlAwxLaunchError,
    FeatureDisabledError as AiSqlFeatureDisabledError,
    SnapshotPolicyMismatchError,
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
    # errors / warnings 是临时属性（不入库；preview 流程结束时设置）
    # C13 起：warnings 也单独返回前端（之前序列化在 preview_safety_reason）
    errors_list = getattr(audit, "_preview_errors", []) or []
    warnings_list = getattr(audit, "_preview_warnings", []) or []

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


# -----------------------------------------------------------------------------
# C14: SQL Execute（plan §6.1）
# -----------------------------------------------------------------------------
@router.post(
    "/sql/execute",
    response_model=AiSqlExecuteResponse,
)
def execute_sql(
    payload: AiSqlExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSqlExecuteResponse:
    """SQL Execute（plan §6.1）。

    引用 Preview 阶段已 passed 的 audit 行；通过 AWX collector 异步执行
    approved_sql。Callback 通过 ``business_domain='ai_sql'`` 路由到
    ``AiSqlCallbackService`` 落 ai_sql_audit + 写 ai_chat_message(sql_result)。

    错误码（plan §11）：
    - 404 — audit_id 不存在
    - 409 — audit.preview_safety_status != 'passed' / snapshot 不一致 /
      execution_status IN ('pending','running') 且未 force
    - 422 — approved_sql 在 Execute 时 AST 二次校验失败
    - 502 — AWX launch 失败
    - 503 — AI_SQL_EXECUTION_ENABLED=false
    """
    try:
        result = AiSqlExecuteService.execute(
            db,
            audit_id=payload.audit_id,
            force=payload.force,
            requested_by=current_user,
        )
    except AuditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SnapshotPolicyMismatchError as exc:
        # 409 + 结构化 code/reason（前端可分支渲染）
        raise HTTPException(
            status_code=409,
            detail={
                "code": "snapshot_policy_mismatch",
                "reason": exc.reason,
                "message": str(exc),
            },
        )
    except (AuditNotPassedError, AuditAlreadyRunningError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except AuditUnsafeOnExecuteError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "audit_unsafe_on_execute",
                "errors": exc.errors,
                "message": str(exc),
            },
        )
    except AiSqlFeatureDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except AiSqlAwxLaunchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    audit = result.audit
    return AiSqlExecuteResponse(
        audit_id=int(audit.id),
        execution_status=audit.execution_status,
        awx_job_id=getattr(audit, "awx_job_id", None),  # C16-F1: 回填后由 execute_service 写入
        awx_job_url=None,
        collector_run_id=audit.collector_run_id,
        collector_run_item_id=audit.collector_run_item_id,
        executed_at=audit.executed_at,
        error_message=audit.error_message,
    )


@router.get(
    "/sql/audit/{audit_id}/execution",
    response_model=AiSqlExecutionStatusResponse,
)
def get_execution_status(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSqlExecutionStatusResponse:
    """查询 audit 执行状态（plan §6.1 — 前端轮询用）。

    错误码：
    - 404 — audit_id 不存在
    """
    try:
        audit = AiSqlExecuteService.get_execution_status(db, audit_id=audit_id)
    except AuditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return AiSqlExecutionStatusResponse(
        audit_id=int(audit.id),
        execution_status=audit.execution_status,
        row_count=audit.row_count,
        duration_ms=audit.duration_ms,
        completed_at=audit.completed_at,
        error_message=audit.error_message,
        collector_run_id=audit.collector_run_id,
        awx_job_id=getattr(audit, "awx_job_id", None),  # C16-F1: launch 成功后由 execute_service 回填
        executed_at=audit.executed_at,
        result_message_id=audit.result_message_id,
        message_type="sql_result" if audit.result_message_id else None,
        created_at=audit.created_at,
    )


# -----------------------------------------------------------------------------
# C16-F3: Object Metadata — Collect / Status / History / Context
# -----------------------------------------------------------------------------
@router.post(
    "/sql/object-metadata/{instance_id}/collect",
    response_model=AiObjectMetadataCollectResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_object_metadata_collection(
    instance_id: int,
    payload: AiObjectMetadataCollectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiObjectMetadataCollectResponse:
    """触发 instance 的 object metadata (table/view/index/function DDL) 采集（F3 plan §4.1）。

    返回 202 Accepted + CollectorRun 元数据。Callback 通过
    ``business_domain='ai_object_metadata'`` 路由到
    ``AiObjectMetadataSnapshotCallbackService`` 落库；前端拿到 collector_run_id
    后通过 GET status 轮询。

    错误码（plan §11）：
    - 404 — instance 不存在
    - 422 — db_type 不在 capabilities 支持范围
    - 502 — AWX launch 失败
    - 503 — AI_SQL_PREVIEW_ENABLED=false
    """
    try:
        result = AiObjectMetadataSnapshotService.trigger_collection(
            db,
            instance_id=instance_id,
            database_name=payload.database_name,
            schema_name=payload.schema_name,
            requested_by=current_user.username,
            request_base_url=str(request.base_url),
        )
    except ObjectMetadataInstanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ObjectMetadataFeatureDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ObjectMetadataUnsupportedDbTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ObjectMetadataAwxLaunchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return AiObjectMetadataCollectResponse(**result)


@router.get(
    "/sql/object-metadata/{instance_id}",
    response_model=AiObjectMetadataListResponse,
)
def get_object_metadata_status(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    schema_name: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiObjectMetadataListResponse:
    """返回该 instance 最新 object metadata snapshot（is_current 优先，否则最新任意状态）。

    返回 items 长度为 0 或 1：0 表示从未采集；1 表示有 snapshot（含
    pending/running/failed），前端根据 ``status`` 字段渲染不同 UI。
    """
    snapshot = AiObjectMetadataSnapshotService.get_latest_any_status(
        db,
        instance_id=instance_id,
        database_name=database_name,
        schema_name=schema_name,
    )
    items = (
        [AiObjectMetadataSnapshotItemResponse.model_validate(snapshot)]
        if snapshot is not None
        else []
    )
    return AiObjectMetadataListResponse(items=items, total=len(items))


@router.get(
    "/sql/object-metadata/{instance_id}/history",
    response_model=AiObjectMetadataListResponse,
)
def list_object_metadata_history(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    schema_name: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiObjectMetadataListResponse:
    """返回历史 object metadata snapshot 列表（created_at DESC）。

    包含 pending/running/failed/success；前端按需过滤。
    """
    items, total = AiObjectMetadataSnapshotService.list_history(
        db,
        instance_id=instance_id,
        database_name=database_name,
        schema_name=schema_name,
        limit=limit,
    )
    return AiObjectMetadataListResponse(
        items=[AiObjectMetadataSnapshotItemResponse.model_validate(o) for o in items],
        total=total,
    )


@router.get(
    "/sql/object-metadata/{instance_id}/context",
    response_model=AiObjectMetadataContextResponse,
)
def get_object_metadata_context(
    instance_id: int,
    database_name: str | None = Query(default=None, max_length=200),
    schema_name: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiObjectMetadataContextResponse:
    """返回该 instance 已发布的 object metadata（is_current + success + 未过期）。

    available=false 时仅 ``reason`` + ``instance_id`` + ``database_name`` +
    ``schema_name`` 有意义，其余字段为 None。
    """
    snap = AiObjectMetadataSnapshotService.get_published_object_metadata(
        db,
        instance_id=instance_id,
        database_name=database_name,
        schema_name=schema_name,
    )

    db_name = AiObjectMetadataSnapshotService._normalize_database_name(database_name)
    sch_name = AiObjectMetadataSnapshotService._normalize_schema_name(schema_name)

    if snap is None:
        # Fallback：尝试查 latest any status，给前端展示进度
        latest = AiObjectMetadataSnapshotService.get_latest_any_status(
            db,
            instance_id=instance_id,
            database_name=database_name,
            schema_name=schema_name,
        )
        if latest is None:
            reason = "no_snapshot"
        elif latest.status == "success" and not latest.is_current:
            reason = "snapshot_not_current"
        elif latest.status == "success" and latest.expires_at is not None:
            from datetime import datetime, timezone

            if latest.expires_at <= datetime.now(tz=timezone.utc).replace(tzinfo=None):
                reason = "snapshot_expired"
            else:
                reason = "snapshot_not_current"
        else:
            reason = "snapshot_not_success"
        return AiObjectMetadataContextResponse(
            available=False,
            instance_id=instance_id,
            db_type_code=None,
            database_name=db_name,
            schema_name=sch_name,
            reason=reason,
        )

    return AiObjectMetadataContextResponse(
        available=True,
        instance_id=instance_id,
        db_type_code=snap.db_type_code,
        database_name=snap.database_name,
        schema_name=snap.schema_name,
        object_ddl_text=snap.object_ddl_text,
        object_ddl_sha256=snap.object_ddl_sha256,
        table_count=snap.table_count,
        view_count=snap.view_count,
        index_count=snap.index_count,
        function_count=snap.function_count,
        total_object_count=snap.total_object_count,
        snapshot_id=int(snap.id),
        snapshot_hash=snap.snapshot_hash,
        published_at=snap.collected_at,
        expires_at=snap.expires_at,
    )
