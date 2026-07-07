"""Phase 3.6B1 C12 + Phase 3.6B2 C16-F2b — AiSqlPreviewService.

SQL Preview 业务编排（plan §5.2 + §5.3 + §6.5 + §21.3 C16-3）：

  C16-F2b 鉴权链（plan §21.3）：
    1. session ownership（session.user_id == current_user.id）
    2. session.chat_mode == 'instance_sql'
    3. session.bound_instance_id == request.instance_id（P0-1 不可变绑定）
    4. DbInstance.status == 'active'（复用 C16-F2a ChatInstanceNotAccessibleError）

  C16-F2b 幂等分支：
    - SELECT ai_chat_message WHERE session_id=? AND client_request_id=?
      AND role='user'
    - 命中 + 已关联 audit（ai_sql_audit.message_id = m.id 存在）
      → 返回已有 (audit_id, user_message_id, preview_message_id)，idempotent_replay=True
    - 命中但 audit 不存在 → PreviewIncompleteRetryRequiredError 409（事务 1 中途中断）

  事务 1（DB）：
    1-4. 鉴权链（C16-F2b）
    5. 幂等检查
    6. 校验 instance 存在 + db_type 在 capabilities
    7. 调 AiSchemaContextService.build_schema_context 取实时 snapshot 策略
    8. 若 available=false → 直接构造 rejected audit 返回
    9. Layer 1 正则预检（C13）→ 命中 → rejected audit + preview_message 卡片
    10. 调 DifyService.run_sql_workflow → generated_sql（C13 Code 节点解析）
    11. 调 SqlSafetyService.validate_with_ast → approved_sql
    12. 写 ai_chat_message × 2（事务内 — C16-F2b）：
        - user message (role='user', message_type='chat', client_request_id=...)
        - preview message (role='assistant', message_type='sql_preview_link')
        - 更新 audit.message_id + audit.result_message_id
    13. 落 ai_sql_audit（passed/rejected 都落 — C16-F2b P1-3）

  事务外：
    无（Dify 调用与 commit 必须严格分事务 — 避免 lock 持有过久）

设计要点：
- 复用 C10 AiSchemaContextService._compute_schema_policy_hash 计算 schema_policy_hash
- SQL 安全 6 层防御：Layer 3（AST 权威）+ approved_sql 与 generated_sql 双轨
  + SHA-256 hash（plan §5 P0-4）
- 错误码映射（plan §11 + C16-F2b）：
  - 403 — session 存在但不属于当前用户（理论上不可达，统一 404 隔离）
  - 404 — instance 不存在 / session 不存在 / DbInstance.status != 'active'
  - 409 — PreviewIncompleteRetryRequiredError（client_request_id 命中但 audit 缺失）
  - 422 — db_type 不在 capabilities / chat_mode != 'instance_sql' / bound_instance_id 不一致
  - 502 — Dify 不可用或网络错误
  - 503 — AI_SQL_PREVIEW_ENABLED=false
  - 504 — Dify 调用超时
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from uuid import UUID

from app.config import get_settings
from app.models.ai import (
    AiChatSession,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.models.dbops_assets import DbInstance, DbType
from app.services.ai.ai_schema_context_service import (
    AiSchemaContextService,
    ContextUnavailableReason,
)
from app.services.ai_chat_service import ChatInstanceNotAccessibleError
from app.services.dify_service import (
    DifyConfigurationError,
    DifyConnectionError,
    DifyError,
    DifyHttpError,
    DifyResponseFormatError,
    DifyService,
    DifyTimeoutError,
    DifyWorkflowFailedError,
)
from app.services.sql_safety_service import SqlSafetyService

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常（与 C10 snapshot service / C3 chat service 命名对齐）
# =============================================================================
class AiSqlPreviewError(Exception):
    """SQL Preview 服务基类异常。"""


class InstanceNotFoundError(AiSqlPreviewError):
    """instance_id 不存在 → 404。"""


class FeatureDisabledError(AiSqlPreviewError):
    """AI_SQL_PREVIEW_ENABLED=false → 503。"""


class UnsupportedDbTypeError(AiSqlPreviewError):
    """db_type 不在 capabilities 支持列表 → 422。"""


class SnapshotUnavailableError(AiSqlPreviewError):
    """Schema snapshot 未就绪 / 不可用 → 409。

    reason 字段说明具体原因：
    - no_snapshot        — 该 instance 尚未采集
    - snapshot_not_success — 当前 snapshot 是 pending/running/failed/unavailable
    - snapshot_not_current — 旧 success 但不是 is_current
    - snapshot_expired   — success 但 expires_at 已过
    """

    def __init__(self, message: str, *, reason: str, snapshot_status: Optional[str] = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.snapshot_status = snapshot_status


class DifyUnavailableError(AiSqlPreviewError):
    """Dify 客户端未初始化或不可用 → 502。"""


class DifyTimeoutError_(AiSqlPreviewError):
    """Dify 调用超时 → 504（避免与 DifyTimeoutError 同名，加尾部下划线）。"""


class DifyWorkflowFailedError_(AiSqlPreviewError):
    """Dify Workflow 自身执行失败 → 502（避免与 DifyWorkflowFailedError 同名）。"""


# =============================================================================
# C16-F2b — SQL Preview 在 Chat 流内的鉴权链异常
# =============================================================================
# 设计原则（plan §21.3 C16-3）：
# - 不复用 ai_chat_service 的同名异常，避免 AiSqlPreviewService 与 AiChatService
#   互相依赖（保持 service 层低耦合）
# - 命名以 Preview 为后缀，与 chat service 异常明确区分
class ChatSessionNotFoundErrorPreview(AiSqlPreviewError):
    """session_id 不存在 → 404（C16-F2b P0-1）。

    注：当前设计统一返回 404 隔离（不区分 session 不存在 vs 不属于当前用户），
    与 ai_chat_service.get_session 行为一致。Forbidden 用 ChatSessionForbiddenErrorPreview。
    """


class ChatSessionForbiddenErrorPreview(AiSqlPreviewError):
    """session 存在但不属于 current_user → 403（C16-F2b P0-1）。

    注：当前 AiChatService.get_session_for_user 仍统一返回 404 隔离以避免泄露；
    本异常类保留作为防御性兜底（service 层未来可选择性 raise，由 API 层映射 403）。
    """


class ChatModeNotInstanceSqlError(AiSqlPreviewError):
    """session.chat_mode != 'instance_sql' → 422（C16-F2b P0-1）。

    普通 general session 不能调用 /ai/sql/preview；前端应改用 /ai/chat/sessions/{id}/messages。
    """


class ChatImmutableViolationErrorPreview(AiSqlPreviewError):
    """session.bound_instance_id != request.instance_id → 422（C16-F2b P0-1 不可变绑定）。

    一旦 session 创建，bound_instance_id 不可变；前端调用 /ai/sql/preview 时必须
    用 session 创建时绑定的 instance_id，否则报本异常。
    """


class PreviewIncompleteRetryRequiredError(AiSqlPreviewError):
    """client_request_id 命中已有 user message 但未关联 audit → 409（C16-F2b P0-2）。

    场景：上一次 preview 请求在事务 1/2 中途中断（如 process killed），导致 user
    message 已落库但 ai_sql_audit 行未创建。partial unique 兜底阻止创建新 user message，
    但旧 user message 没有 audit，状态不一致。

    缓解：前端提示用户「上一次请求未完成，请重试或换 client_request_id」，service
    层暂不自动重试（避免无穷递归）。
    """

    def __init__(self, message: str, *, user_message_id: int) -> None:
        super().__init__(message)
        self.user_message_id = user_message_id


# =============================================================================
# Service 返回类型
# =============================================================================
@dataclass
class PreviewResult:
    """preview() 内部返回（audit_id + preview safety payload）。

    C16-F2b commit 2 扩展计划（plan §21.3 C16-3）：
    - session_id:          与 request.session_id 一致
    - user_message_id:     ai_chat_message.id（role='user'）
    - preview_message_id:  ai_chat_message.id（role='assistant'，message_type='sql_preview_link'）
    - idempotent_replay:   True 表示命中已有 user_message，未调 Dify、未创建新 audit

    commit 1 仅添加鉴权链；PreviewResult 扩展字段在 commit 2 补齐。
    """

    audit: AiSqlAudit


# =============================================================================
# AiSqlPreviewService
# =============================================================================
class AiSqlPreviewService:
    """SQL Preview 业务编排（plan §5.2 + §5.3 + §6.5）。"""

    # SQL 安全规则版本 — 写入 ai_sql_audit.safety_policy_version
    # 与 schema_policy_version（AiSchemaContextService.POLICY_VERSION）独立：
    #   safety_policy_version → SQL 安全规则 + AST 校验的版本
    #   schema_policy_hash    → Schema Policy 内容的 SHA-256
    SAFETY_POLICY_VERSION = "2026-06-28-v1"

    # SQL Preview 时 max_rows 默认值（plan §5 + §10 — Executor 仍由 Collector EE 强制）
    DEFAULT_MAX_ROWS = 200

    # Layer 1 正则预检开关（plan §5 Layer 1）
    # - True：调 Dify 之前先用 SqlSafetyService.layer1_precheck_question 拦截
    #         命中 → 构造 rejected audit 返回（节省 Dify token + 配额）
    # - False：跳过预检，直接调 Dify（保留给将来 A/B test 或 escape hatch）
    LAYER1_PRECHECK_ENABLED = True

    # ------------------------------------------------------------------
    # preview — 核心端点
    # ------------------------------------------------------------------
    @classmethod
    def preview(
        cls,
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str],
        user_question: str,
        session_id: int,
        client_request_id: UUID,
        current_page: Optional[str] = None,
        requested_by: Optional[Any] = None,
    ) -> PreviewResult:
        """触发 SQL Preview，生成 approved_sql 并落 ai_sql_audit。

        C16-F2b 起 session_id + client_request_id 必填（plan §21.3 C16-3）；
        message_id 由 service 内部生成 user_message 后回填 audit，不再由调用方传入。

        流程（plan §5.2 + §5.3 + C13 Layer 1 + C16-F2b 鉴权链）：
          1.  功能开关（503 FeatureDisabledError）
          2.  session ownership + chat_mode='instance_sql' + bound_instance_id 一致
              + DbInstance.status='active'（C16-F2b 鉴权链；404/422/403）
          3.  instance 存在性 + db_type capability（404 / 422）
          4.  Schema snapshot 可用性（409 SnapshotUnavailableError）
          4.5. Layer 1 正则预检 user_question（C13 NEW；命中 → rejected audit）
          5.  调 Dify sql-generator workflow 取 generated_sql
              - 解析 Code 节点结构化 JSON（C13 NEW）
              - 失败 / 解析失败 → 构造 rejected audit 落库
          6.  调 SqlSafetyService.validate_with_ast 取 approved_sql
              - rejected → 构造 rejected audit 落库
          7.  落 ai_sql_audit（passed / rejected 都落库）
          8.  C16-F2b commit 2 追加：写 ai_chat_message × 2（user + preview）+ 幂等分支

        Raises:
            ChatSessionNotFoundErrorPreview:    session 不存在 → 404
            ChatSessionForbiddenErrorPreview:   session 不属于 current_user → 403（保留接口）
            ChatModeNotInstanceSqlError:        session.chat_mode != 'instance_sql' → 422
            ChatImmutableViolationErrorPreview: instance_id 与 bound_instance_id 不一致 → 422
            ChatInstanceNotAccessibleError:     DbInstance.status != 'active' → 404（复用 C16-F2a）
            InstanceNotFoundError:              instance_id 不存在 → 404
            FeatureDisabledError:               AI_SQL_PREVIEW_ENABLED=false → 503
            UnsupportedDbTypeError:             db_type 不支持 → 422
            SnapshotUnavailableError:           snapshot 不可用 → 409
            DifyUnavailableError:               Dify 客户端未配置 → 502
            DifyTimeoutError_:                  Dify 超时 → 504
            DifyError:                          其他 Dify 错误 → 502
        """
        settings = get_settings()

        # 1. 功能开关（按 plan §11 P1 解耦校验）
        if not settings.AI_SQL_PREVIEW_ENABLED:
            raise FeatureDisabledError("AI_SQL_PREVIEW_ENABLED=false")

        # 2. C16-F2b 鉴权链 — session ownership + chat_mode + bound_instance_id + status
        session_obj = cls._auth_check_session_for_preview(
            db, session_id=session_id, instance_id=instance_id, user=requested_by,
        )

        # 3. instance 校验 + db_type capability 校验
        instance, db_type_code = cls._resolve_instance(db, instance_id)

        if db_type_code.upper() not in settings.sql_supported_db_types:
            raise UnsupportedDbTypeError(
                f"db_type '{db_type_code}' not in capabilities "
                f"({settings.sql_supported_db_types}); "
                f"see GET /api/v1/ai/capabilities"
            )

        # 3. Schema snapshot 可用性
        ctx = AiSchemaContextService.build_schema_context(
            db, instance_id=instance_id, database_name=database_name,
        )
        if not ctx.get("available"):
            raise SnapshotUnavailableError(
                f"schema snapshot unavailable for instance {instance_id}: "
                f"reason={ctx.get('reason')}",
                reason=str(ctx.get("reason") or ContextUnavailableReason.NO_SNAPSHOT),
                snapshot_status=None,
            )

        # 提取策略字段（已通过 is_current + TTL 校验）
        schema_snapshot_id = int(ctx["schema_snapshot_id"])
        schema_policy_hash = str(ctx["schema_policy_hash"])
        allowed_tables = list(ctx.get("allowed_tables") or [])
        allowed_columns = dict(ctx.get("allowed_columns") or {})
        denied_columns = list(ctx.get("denied_columns") or [])
        schema_context_text = ctx.get("schema_context") or ""
        sql_dialect = ctx.get("sql_dialect")

        # 3.5. Layer 1 正则预检（C13 NEW — plan §5 Layer 1）
        # 在调 Dify 之前用 SqlSafetyService.layer1_precheck_question 快速拦截
        # 明显的非只读问题（中英文 DROP/DELETE/删除/插入 等）。命中 →
        # 构造 rejected audit 落库（**不**调 Dify），节省 token + 配额。
        if cls.LAYER1_PRECHECK_ENABLED:
            precheck = SqlSafetyService.layer1_precheck_question(user_question)
            if not precheck.get("allowed"):
                logger.info(
                    "ai_sql preview Layer 1 precheck rejected instance_id=%s "
                    "matched=%s pattern=%s reason=%s",
                    instance_id,
                    precheck.get("matched_keyword"),
                    precheck.get("matched_pattern"),
                    precheck.get("reason"),
                )
                now_l1 = cls._utcnow()
                audit = cls._build_rejected_audit(
                    instance_id=instance_id,
                    db_type_code=db_type_code,
                    user_question=user_question,
                    session_id=session_id,
                    message_id=None,  # C16-F2b commit 1: 暂不写 user_message，commit 2 补齐
                    user_id=getattr(requested_by, "id", None),
                    schema_snapshot_id=schema_snapshot_id,
                    schema_policy_hash=schema_policy_hash,
                    dify_workflow_run_id=None,
                    reason=str(precheck.get("reason") or "Layer 1 precheck rejected"),
                    errors=[str(precheck.get("error_code") or "LAYER1_DANGEROUS_KEYWORD")],
                    warnings=[],
                    sql_workflow_version=settings.DIFY_SQL_WORKFLOW_VERSION,
                    safety_policy_version=cls.SAFETY_POLICY_VERSION,
                    previewed_at=now_l1,
                )
                # 标记 layer1 命中（前端可据此显示"非只读查询"提示而非 AST 错误）
                audit._preview_layer1_blocked = True  # type: ignore[attr-defined]
                audit._preview_layer1_keyword = precheck.get("matched_keyword")  # type: ignore[attr-defined]
                db.add(audit)
                db.commit()
                db.refresh(audit)
                return PreviewResult(audit=audit)

        # 4. 调 Dify sql-generator workflow
        dify_run_id: Optional[str] = None
        generated_sql: Optional[str] = None
        dify_workflow_failed_reason: Optional[str] = None

        if not DifyService.is_configured():
            raise DifyUnavailableError("Dify client not initialized")

        dify_user = "dbops:anonymous"
        if requested_by is not None:
            # 沿用 chat service 的命名约定
            user_id_attr = getattr(requested_by, "id", None)
            if user_id_attr is not None:
                dify_user = f"dbops:{user_id_attr}"

        # Dify inputs（plan §7 安全约束）：
        #   user            → 不可被前端覆盖
        #   role/locale     → 来自 user 对象（不由前端传）
        #   current_page    → 白名单校验
        #   schema_context  → 实时计算，禁止存 DB（plan §4.6）
        inputs: dict[str, Any] = {
            "db_type_code": db_type_code.upper(),
            "sql_dialect": sql_dialect or "",
            "schema_context": schema_context_text,
            "allowed_schemas": list(ctx.get("allowed_schemas") or []),
            "allowed_tables": allowed_tables,
            "allowed_columns": allowed_columns,
            "denied_columns": denied_columns,
            "current_page": cls._normalize_current_page(current_page),
        }

        # 5. 调 DifyWorkflow（捕获异常 → rejected audit 落库）
        try:
            dify_response = DifyService.run_sql_workflow(
                inputs=inputs,
                user=dify_user,
            )
            dify_run_id = dify_response.get("workflow_run_id")

            # C13: 解析 Code 节点结构化 JSON（C12 仅 plain text 提取）
            code_payload = cls._parse_code_node_payload(dify_response)
            generated_sql = code_payload.get("generated_sql")
            code_node_warnings = list(code_payload.get("warnings") or [])
            code_node_parse_mode = code_payload.get("parse_mode")

            logger.info(
                "ai_sql preview Dify response parsed instance_id=%s run_id=%s "
                "parse_mode=%s warnings=%d table_refs=%d",
                instance_id, dify_run_id, code_node_parse_mode,
                len(code_node_warnings),
                len(code_payload.get("table_refs") or []),
            )

            if not generated_sql:
                dify_workflow_failed_reason = (
                    "Dify workflow returned no generated_sql in response; "
                    f"parse_mode={code_node_parse_mode} "
                    f"keys={list(dify_response.keys())[:5]}"
                )
                logger.warning(
                    "ai_sql preview Dify response missing generated_sql: "
                    "instance_id=%s run_id=%s keys=%s",
                    instance_id, dify_run_id, list(dify_response.keys())[:5],
                )
        except DifyTimeoutError as exc:
            # 504 — 单独映射到 HTTP 504
            raise DifyTimeoutError_(f"Dify sql-generator timeout: {exc}") from exc
        except (DifyConfigurationError, DifyConnectionError) as exc:
            raise DifyUnavailableError(f"Dify unavailable: {exc}") from exc
        except (DifyHttpError, DifyResponseFormatError) as exc:
            raise DifyUnavailableError(f"Dify error: {exc}") from exc
        except DifyWorkflowFailedError as exc:
            # Workflow 自身 failed → 502（与 plan §11 一致）
            raise DifyWorkflowFailedError_(f"Dify workflow failed: {exc}") from exc
        except DifyError as exc:
            raise DifyUnavailableError(f"Dify error: {exc}") from exc

        # 6. 调 AST 权威校验（Layer 3 — sqlglot）
        now = cls._utcnow()

        if not generated_sql:
            # Dify 没有有效 SQL → 构造 rejected audit 落库
            # C13: 把 Dify Code 节点的 warnings 也合并到 audit warnings 中
            merged_warnings = list(code_node_warnings or [])
            audit = cls._build_rejected_audit(
                instance_id=instance_id,
                db_type_code=db_type_code,
                user_question=user_question,
                session_id=session_id,
                message_id=None,  # C16-F2b commit 1: 暂不写 user_message，commit 2 补齐
                user_id=getattr(requested_by, "id", None),
                schema_snapshot_id=schema_snapshot_id,
                schema_policy_hash=schema_policy_hash,
                dify_workflow_run_id=dify_run_id,
                reason=dify_workflow_failed_reason
                or "Dify did not produce a generated_sql",
                errors=[dify_workflow_failed_reason or "missing generated_sql"],
                warnings=merged_warnings,
                sql_workflow_version=settings.DIFY_SQL_WORKFLOW_VERSION,
                safety_policy_version=cls.SAFETY_POLICY_VERSION,
                previewed_at=now,
            )
            db.add(audit)
            db.commit()
            db.refresh(audit)
            return PreviewResult(audit=audit)

        # 6a. 双轨 SQL hash（Dify 原始）
        generated_sql_stripped = generated_sql.strip()
        generated_sql_hash = SqlSafetyService.compute_sql_hash(generated_sql_stripped)

        # 6b. AST 校验
        ast_result = SqlSafetyService.validate_with_ast(
            sql_text=generated_sql_stripped,
            db_type_code=db_type_code,
            allowed_tables=allowed_tables,
            allowed_columns=allowed_columns,
            denied_columns=denied_columns,
            max_rows=cls.DEFAULT_MAX_ROWS,
        )

        if not ast_result.get("valid"):
            # AST 拒绝 → rejected audit 落库
            errors_list = list(ast_result.get("errors") or [])
            warnings_list = list(ast_result.get("warnings") or [])
            # C13: 合并 Dify Code 节点 warnings + AST warnings（去重保序）
            merged_warnings = list(code_node_warnings or [])
            for w in warnings_list:
                if w not in merged_warnings:
                    merged_warnings.append(w)
            reason = (
                f"AST validation rejected: {'; '.join(errors_list[:3])}"
                if errors_list
                else "AST validation rejected"
            )
            audit = cls._build_rejected_audit(
                instance_id=instance_id,
                db_type_code=db_type_code,
                user_question=user_question,
                session_id=session_id,
                message_id=None,  # C16-F2b commit 1: 暂不写 user_message，commit 2 补齐
                user_id=getattr(requested_by, "id", None),
                schema_snapshot_id=schema_snapshot_id,
                schema_policy_hash=schema_policy_hash,
                dify_workflow_run_id=dify_run_id,
                generated_sql=generated_sql_stripped,
                generated_sql_hash=generated_sql_hash,
                approved_sql=str(ast_result.get("approved_sql") or ""),
                approved_sql_hash=str(ast_result.get("approved_sql_hash") or ""),
                reason=reason,
                errors=errors_list,
                warnings=merged_warnings,
                sql_workflow_version=settings.DIFY_SQL_WORKFLOW_VERSION,
                safety_policy_version=cls.SAFETY_POLICY_VERSION,
                previewed_at=now,
            )
            db.add(audit)
            db.commit()
            db.refresh(audit)
            return PreviewResult(audit=audit)

        # 6c. AST 通过 → passed audit 落库
        # C13: passed 也合并 code_node_warnings + AST warnings 到 _preview_warnings
        # （preview_safety_reason 保持 NULL — passed 不污染 reason）
        merged_passed_warnings = list(code_node_warnings or [])
        for w in (ast_result.get("warnings") or []):
            if w not in merged_passed_warnings:
                merged_passed_warnings.append(w)

        audit = AiSqlAudit(
            session_id=session_id,
            message_id=None,  # C16-F2b commit 1: 暂不写 user_message，commit 2 补齐
            user_id=getattr(requested_by, "id", None),
            instance_id=instance_id,
            db_type_code=db_type_code.upper(),
            user_question=user_question.strip(),
            generated_sql=generated_sql_stripped,
            generated_sql_hash=generated_sql_hash,
            approved_sql=str(ast_result.get("approved_sql") or ""),
            approved_sql_hash=str(ast_result.get("approved_sql_hash") or ""),
            preview_safety_status=AiSqlAuditPreviewSafety.PASSED,
            preview_safety_reason=None,
            safety_policy_version=cls.SAFETY_POLICY_VERSION,
            schema_snapshot_id=schema_snapshot_id,
            schema_policy_hash=schema_policy_hash,
            dify_workflow_run_id=dify_run_id,
            sql_workflow_version=settings.DIFY_SQL_WORKFLOW_VERSION,
            previewed_at=now,
            execution_status=AiSqlAuditExecutionStatus.NOT_REQUESTED,
        )
        audit._preview_warnings = merged_passed_warnings  # type: ignore[attr-defined]
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return PreviewResult(audit=audit)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_instance(db: Session, instance_id: int) -> tuple[DbInstance, str]:
        """返回 (instance, db_type_code)；instance 不存在 → LookupError。"""
        instance = db.query(DbInstance).filter(DbInstance.id == int(instance_id)).first()
        if instance is None:
            raise InstanceNotFoundError(f"db_instance id={instance_id} not found")

        db_type_code = "POSTGRESQL"
        try:
            db_type_id = getattr(instance, "db_type_id", None)
            if db_type_id is not None:
                db_type = db.query(DbType).filter(DbType.id == db_type_id).first()
                if db_type is not None and getattr(db_type, "type_code", None):
                    db_type_code = str(db_type.type_code).upper()
        except Exception:
            logger.exception("db_type_code lookup failed for instance_id=%s", instance_id)
            db_type_code = "POSTGRESQL"

        return instance, db_type_code

    @staticmethod
    def _auth_check_session_for_preview(
        db: Session,
        *,
        session_id: int,
        instance_id: int,
        user: Optional[Any],
    ) -> AiChatSession:
        """C16-F2b 鉴权链 — session ownership + chat_mode + bound_instance_id + status（4 步）。

        Args:
            db:          SQLAlchemy Session
            session_id:  ai_chat_session.id（必填）
            instance_id: request.instance_id（与 session.bound_instance_id 比对）
            user:        current_user（与 session.user_id 比对）

        Returns:
            AiChatSession（鉴权通过）

        Raises:
            ChatSessionNotFoundErrorPreview:    session 不存在 → 404
            ChatSessionForbiddenErrorPreview:   session 不属于 current_user → 403（保留）
            ChatModeNotInstanceSqlError:        session.chat_mode != 'instance_sql' → 422
            ChatImmutableViolationErrorPreview: instance_id 与 bound_instance_id 不一致 → 422
            ChatInstanceNotAccessibleError:     DbInstance.status != 'active' → 404（复用 C16-F2a）

        Notes:
            - 不复用 ai_chat_service.get_session_for_user：preview service 需对 4 步
              做精细化异常映射（404/403/422），chat service 只做 ownership 一项。
            - ChatSessionNotFoundErrorPreview 与 ChatSessionForbiddenErrorPreview
              都在 chat_service 中存在对应类型（ChatSessionNotFoundError / ChatSessionForbiddenError），
              但此处不复用以避免 preview ↔ chat service 互相依赖。
        """
        # 步骤 1：session 存在性（统一 404 隔离存在性，避免泄露）
        session_obj = (
            db.query(AiChatSession)
            .filter(AiChatSession.id == session_id)
            .first()
        )
        if session_obj is None:
            raise ChatSessionNotFoundErrorPreview(
                f"Chat session {session_id} not found"
            )

        # 步骤 1.5：session ownership（统一 404 隔离避免泄露「会话存在但属于他人」）
        if user is not None and session_obj.user_id is not None:
            if session_obj.user_id != getattr(user, "id", None):
                logger.warning(
                    "AiSqlPreviewService._auth_check forbidden: session_id=%s "
                    "requested_by=%s actual_owner=%s instance_id=%s",
                    session_id,
                    getattr(user, "id", None),
                    session_obj.user_id,
                    instance_id,
                )
                raise ChatSessionForbiddenErrorPreview(
                    f"Chat session {session_id} not owned by user"
                )

        # 步骤 2：chat_mode 必须是 'instance_sql'
        if session_obj.chat_mode != "instance_sql":
            raise ChatModeNotInstanceSqlError(
                f"Chat session {session_id} has chat_mode={session_obj.chat_mode!r}; "
                "only 'instance_sql' sessions can call /ai/sql/preview"
            )

        # 步骤 3：bound_instance_id 必须 == instance_id（P0-1 不可变绑定）
        if session_obj.bound_instance_id != int(instance_id):
            raise ChatImmutableViolationErrorPreview(
                f"Chat session {session_id} bound_instance_id="
                f"{session_obj.bound_instance_id} != request.instance_id={instance_id}; "
                "bound_instance_id is immutable per plan §21.2 P0-1"
            )

        # 步骤 4：DbInstance.status == 'active'（复用 C16-F2a 校验）
        # 注：DbInstance 已通过 _resolve_instance 验证存在；此处只检查 status
        # 但 _resolve_instance 在 commit 1 中尚未调用（顺序：先鉴权再 _resolve_instance），
        # 因此这里需要直接查一次 DbInstance
        instance = (
            db.query(DbInstance)
            .filter(DbInstance.id == int(instance_id))
            .first()
        )
        if instance is None:
            # 理论上 chat session.bound_instance_id FK 已保证 instance 存在；
            # 但 instance 可能被级联删除（如 ON DELETE CASCADE）— 兜底 404
            raise ChatInstanceNotAccessibleError(
                f"db_instance id={instance_id} not found (bound from session {session_id})"
            )
        instance_status = getattr(instance, "status", None) or "active"
        if instance_status != "active":
            raise ChatInstanceNotAccessibleError(
                f"db_instance id={instance_id} is not accessible "
                f"(status={instance_status!r}; bound from session {session_id})"
            )

        return session_obj

    @staticmethod
    def _extract_generated_sql(dify_response: dict[str, Any]) -> Optional[str]:
        """从 Dify Workflow 响应中提取 SQL 字符串（C12 旧接口，保留兼容）。

        Dify Workflow 输出格式约定（plan §5.3 + Dify 端 schema）：
          outputs.generated_sql = "<SQL text>"
        或
          outputs.sql = "<SQL text>"
        或（chat 风格）answer 字段含 ```sql ... ``` 块。

        C13 起推荐使用 :meth:`_parse_code_node_payload`，可同时拿 SQL +
        warnings + table_refs + confidence + explanation。
        """
        if not isinstance(dify_response, dict):
            return None

        # Workflow outputs 优先
        outputs = dify_response.get("outputs") or {}
        if isinstance(outputs, dict):
            for key in ("generated_sql", "sql", "sql_text"):
                val = outputs.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

        # Chat App 风格（保守兼容）
        for key in ("answer", "sql", "generated_sql", "sql_text"):
            val = dify_response.get(key)
            if isinstance(val, str) and val.strip():
                # chat answer 经常包含解释文字 — 只取 ```sql ... ``` 块
                stripped = val.strip()
                if "```" in stripped:
                    sql_block = AiSqlPreviewService._extract_sql_block(stripped)
                    if sql_block:
                        return sql_block
                # 否则返回整段 answer（可能是纯 SQL）
                return stripped

        return None

    # ------------------------------------------------------------------
    # C13 — Dify Code 节点结构化 JSON 解析
    # ------------------------------------------------------------------
    #
    # Dify Workflow 的 Code 节点可以输出结构化 JSON，包含：
    #   {
    #     "generated_sql": "<SQL>",
    #     "warnings":     ["敏感字段命中: email", ...],
    #     "confidence":   0.85,
    #     "table_refs":   ["public.users", ...],
    #     "explanation":  "查询用户ID和邮箱"
    #   }
    # outputs 字段也可能是字符串化的 JSON（取决于 Dify Code 节点配置）。
    #
    # 本方法稳健地解析上述结构，字段缺失时降级：
    #   - 缺 warnings → []
    #   - 缺 confidence → None
    #   - 缺 table_refs → []
    #   - 缺 explanation → None
    # 并在所有结构化字段都不可用时降级到 _extract_generated_sql（plain text）。

    @staticmethod
    def _parse_code_node_payload(
        dify_response: dict[str, Any],
    ) -> dict[str, Any]:
        """解析 Dify Code 节点输出的结构化 JSON（C13 — plan §5 Layer 1 (b)）。

        Returns:
            dict:
              - generated_sql (str|None) — 提取出的 SQL；无则 None
              - warnings (list[str])     — Dify Code 节点提示的软警告
              - confidence (float|None)  — 0.0~1.0；Dify 未返回则 None
              - table_refs (list[str])   — SQL 引用的物理表列表（best-effort）
              - explanation (str|None)   — 人类可读解释；供前端展示
              - parse_mode (str)         — "structured" | "fallback_plain_text" |
                                            "missing"
              - raw_outputs (Any)        — 原始 outputs（debug 用；不写库）

        设计：
        - ``outputs`` 是 dict → 直接取字段
        - ``outputs`` 是 str → 尝试 json.loads
        - ``outputs.generated_sql`` 是 str → 用之
        - ``outputs.generated_sql`` 是 dict → 递归解析（防御性，正常不应出现）
        - 全部结构化字段缺失 → 退回 _extract_generated_sql（plain text）
        """
        result: dict[str, Any] = {
            "generated_sql": None,
            "warnings": [],
            "confidence": None,
            "table_refs": [],
            "explanation": None,
            "parse_mode": "missing",
            "raw_outputs": None,
        }

        if not isinstance(dify_response, dict):
            return result

        outputs_raw = dify_response.get("outputs")
        result["raw_outputs"] = outputs_raw

        # 1. outputs 是 str → 尝试 json.loads（仅当形如 JSON 对象）
        if isinstance(outputs_raw, str):
            stripped = outputs_raw.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    outputs_raw = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    outputs_raw = None
            elif "```sql" in stripped or "```SQL" in stripped:
                # Code 节点把 SQL 直接放在 markdown 块里 — 提取 SQL
                sql_block = AiSqlPreviewService._extract_sql_block(stripped)
                if sql_block:
                    result["generated_sql"] = sql_block
                    result["parse_mode"] = "fallback_plain_text"
                    return result
                outputs_raw = None

        # 2. outputs 是 dict → 取结构化字段
        if isinstance(outputs_raw, dict):
            # generated_sql
            sql_val = outputs_raw.get("generated_sql")
            if isinstance(sql_val, str) and sql_val.strip():
                result["generated_sql"] = sql_val.strip()
            elif isinstance(sql_val, dict):
                # 防御：极少数 Code 节点嵌套输出
                nested = sql_val.get("sql") or sql_val.get("text")
                if isinstance(nested, str) and nested.strip():
                    result["generated_sql"] = nested.strip()

            # warnings
            warnings_val = outputs_raw.get("warnings")
            if isinstance(warnings_val, list):
                result["warnings"] = [str(w) for w in warnings_val if w is not None]
            elif isinstance(warnings_val, str) and warnings_val.strip():
                result["warnings"] = [warnings_val.strip()]

            # confidence
            conf_val = outputs_raw.get("confidence")
            if isinstance(conf_val, (int, float)):
                result["confidence"] = float(conf_val)

            # table_refs
            refs_val = outputs_raw.get("table_refs")
            if isinstance(refs_val, list):
                result["table_refs"] = [str(t) for t in refs_val if t is not None]

            # explanation
            expl_val = outputs_raw.get("explanation")
            if isinstance(expl_val, str) and expl_val.strip():
                result["explanation"] = expl_val.strip()

            if result["generated_sql"]:
                result["parse_mode"] = "structured"
                return result

        # 3. 降级到旧 plain text 提取
        fallback_sql = AiSqlPreviewService._extract_generated_sql(dify_response)
        if fallback_sql:
            result["generated_sql"] = fallback_sql
            result["parse_mode"] = "fallback_plain_text"
            return result

        return result

    @staticmethod
    def _extract_sql_block(text: str) -> Optional[str]:
        """从 markdown ```` ```sql ... ``` ```` 块提取 SQL。"""
        if "```sql" not in text and "```SQL" not in text:
            return None
        # 找 ```sql 与下一个 ``` 之间的内容
        lower = text.lower()
        start = lower.find("```sql")
        if start < 0:
            return None
        start += len("```sql")
        end = text.find("```", start)
        if end < 0:
            return text[start:].strip()
        return text[start:end].strip()

    @staticmethod
    def _normalize_current_page(value: Optional[str]) -> str:
        """与 AiChatService 同款白名单校验（plan §7）。"""
        allowlist = frozenset({
            "ai_chat",
            "inspection_report",
            "instance_report",
            "instance_detail",
        })
        if not value:
            return "ai_chat"
        if value in allowlist:
            return value
        logger.warning(
            "AiSqlPreviewService rejected unknown current_page=%r; "
            "falling back to ai_chat",
            value,
        )
        return "ai_chat"

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _build_rejected_audit(
        *,
        instance_id: int,
        db_type_code: str,
        user_question: str,
        session_id: Optional[int],
        message_id: Optional[int],
        user_id: Optional[Any],
        schema_snapshot_id: int,
        schema_policy_hash: str,
        dify_workflow_run_id: Optional[str],
        reason: str,
        errors: list[str],
        warnings: list[str],
        sql_workflow_version: str,
        safety_policy_version: str,
        previewed_at: datetime,
        generated_sql: Optional[str] = None,
        generated_sql_hash: Optional[str] = None,
        approved_sql: Optional[str] = None,
        approved_sql_hash: Optional[str] = None,
    ) -> AiSqlAudit:
        """构造 rejected audit 行（统一字段填充 + payload CHECK 约束满足）。

        关键：rejected 时 payload CHECK 要求 preview_safety_reason NOT NULL。
        approved_sql/approved_sql_hash/schema_snapshot_id/schema_policy_hash
        在 rejected 时按 SQL CHECK 允许为 NULL（payload CHECK 的 passed 分支
        才要求这些字段）。但我们仍然把 schema 信息落库，便于审计追溯 —
        仅 preview_safety_status='rejected' 即可。
        """
        full_reason = reason
        if warnings:
            full_reason = f"{reason} [warnings: {'; '.join(warnings[:3])}]"

        audit = AiSqlAudit(
            session_id=session_id,
            message_id=None,  # C16-F2b commit 1: 暂不写 user_message，commit 2 补齐
            user_id=user_id,
            instance_id=instance_id,
            db_type_code=db_type_code.upper(),
            user_question=user_question.strip(),
            generated_sql=generated_sql,
            generated_sql_hash=generated_sql_hash,
            approved_sql=approved_sql if approved_sql else None,
            approved_sql_hash=approved_sql_hash if approved_sql_hash else None,
            preview_safety_status=AiSqlAuditPreviewSafety.REJECTED,
            preview_safety_reason=full_reason[:4000],
            safety_policy_version=safety_policy_version,
            schema_snapshot_id=schema_snapshot_id,
            schema_policy_hash=schema_policy_hash,
            dify_workflow_run_id=dify_workflow_run_id,
            sql_workflow_version=sql_workflow_version,
            previewed_at=previewed_at,
            execution_status=AiSqlAuditExecutionStatus.NOT_REQUESTED,
        )
        # errors / warnings 暂存到 audit 的临时属性（不入库；用完即丢）
        # API 层读取后回填到 AiSqlPreviewResponse
        audit._preview_errors = errors  # type: ignore[attr-defined]
        audit._preview_warnings = list(warnings or [])  # type: ignore[attr-defined]
        return audit


def compute_sql_hash(sql_text: str) -> str:
    """Public re-export of SHA-256 hash (delegates to SqlSafetyService)."""
    return SqlSafetyService.compute_sql_hash(sql_text)


def canonical_json_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of payload (用于 audit 元数据 hash)。"""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()