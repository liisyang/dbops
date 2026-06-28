"""Phase 3.6B1 C12 — AiSqlPreviewService.

SQL Preview 业务编排（plan §5.2 + §5.3 + §6.5）：

  事务 1（DB）：
    1. 校验 instance 存在 + db_type 在 capabilities
    2. 调 AiSchemaContextService.build_schema_context 取实时 snapshot 策略
    3. 若 available=false → 直接构造 rejected audit 返回
    4. 调 DifyService.run_sql_workflow（sql-generator app）取 generated_sql
       - Dify 失败 → 构造 rejected audit 落库，返回错误给前端
    5. 调 SqlSafetyService.validate_with_ast（6 层防御 Layer 3）取 approved_sql
    6. 落 ai_sql_audit：
       - passed  → approved_sql + approved_sql_hash + schema_snapshot_id +
                    schema_policy_hash + previewed_at + workflow_run_id
       - rejected → preview_safety_reason 记录 errors

  事务外：
    无（Dify 调用与 commit 必须严格分事务 — 避免 lock 持有过久）

设计要点：
- 复用 C10 AiSchemaContextService._compute_schema_policy_hash 计算 schema_policy_hash
  （同一个 hash 算法，preview/execute 校验才能对齐）
- SQL 安全 6 层防御：Layer 3（AST 权威）+ approved_sql 与 generated_sql 双轨
  + SHA-256 hash（plan §5 P0-4）
- 不直接复用 chat idempotency — SQL Preview 是无状态端点，前端无需 client_request_id
  （无并发约束，由前端 UI 防抖；plan §14 C12 不实现）
- 错误码映射（plan §11）：
  - 404 — instance 不存在
  - 422 — db_type 不在 capabilities（不支持）
  - 409 — schema snapshot 未就绪 / 不可用
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

from app.config import get_settings
from app.models.ai import (
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.models.dbops_assets import DbInstance, DbType
from app.services.ai.ai_schema_context_service import (
    AiSchemaContextService,
    ContextUnavailableReason,
)
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
# Service 返回类型
# =============================================================================
@dataclass
class PreviewResult:
    """preview() 内部返回（audit_id + preview safety payload）。"""

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
        session_id: Optional[int] = None,
        message_id: Optional[int] = None,
        current_page: Optional[str] = None,
        requested_by: Optional[Any] = None,
    ) -> PreviewResult:
        """触发 SQL Preview，生成 approved_sql 并落 ai_sql_audit。

        流程（plan §5.2 + §5.3）：
          1. 功能开关（503 FeatureDisabledError）
          2. instance 存在性 + db_type capability（404 / 422）
          3. Schema snapshot 可用性（409 SnapshotUnavailableError）
          4. 调 Dify sql-generator workflow 取 generated_sql
             - 失败 / 解析失败 → 构造 rejected audit 落库，返回 PreviewResult
          5. 调 SqlSafetyService.validate_with_ast 取 approved_sql
             - rejected → 构造 rejected audit 落库
          6. 落 ai_sql_audit（passed / rejected 都落库）

        Raises:
            InstanceNotFoundError: instance_id 不存在 → 404
            FeatureDisabledError: AI_SQL_PREVIEW_ENABLED=false → 503
            UnsupportedDbTypeError: db_type 不支持 → 422
            SnapshotUnavailableError: snapshot 不可用 → 409
            DifyUnavailableError: Dify 客户端未配置 → 502
            DifyTimeoutError_: Dify 超时 → 504
            DifyError: 其他 Dify 错误 → 502
        """
        settings = get_settings()

        # 1. 功能开关（按 plan §11 P1 解耦校验）
        if not settings.AI_SQL_PREVIEW_ENABLED:
            raise FeatureDisabledError("AI_SQL_PREVIEW_ENABLED=false")

        # 2. instance 校验 + db_type capability 校验
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
            generated_sql = cls._extract_generated_sql(dify_response)

            if not generated_sql:
                dify_workflow_failed_reason = (
                    "Dify workflow returned no generated_sql in response; "
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
            audit = cls._build_rejected_audit(
                instance_id=instance_id,
                db_type_code=db_type_code,
                user_question=user_question,
                session_id=session_id,
                message_id=message_id,
                user_id=getattr(requested_by, "id", None),
                schema_snapshot_id=schema_snapshot_id,
                schema_policy_hash=schema_policy_hash,
                dify_workflow_run_id=dify_run_id,
                reason=dify_workflow_failed_reason
                or "Dify did not produce a generated_sql",
                errors=[dify_workflow_failed_reason or "missing generated_sql"],
                warnings=[],
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
                message_id=message_id,
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
                warnings=warnings_list,
                sql_workflow_version=settings.DIFY_SQL_WORKFLOW_VERSION,
                safety_policy_version=cls.SAFETY_POLICY_VERSION,
                previewed_at=now,
            )
            db.add(audit)
            db.commit()
            db.refresh(audit)
            return PreviewResult(audit=audit)

        # 6c. AST 通过 → passed audit 落库
        audit = AiSqlAudit(
            session_id=session_id,
            message_id=message_id,
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
    def _extract_generated_sql(dify_response: dict[str, Any]) -> Optional[str]:
        """从 Dify Workflow 响应中提取 SQL 字符串。

        Dify Workflow 输出格式约定（plan §5.3 + Dify 端 schema）：
          outputs.generated_sql = "<SQL text>"
        或
          outputs.sql = "<SQL text>"
        或（chat 风格）answer 字段含 ```sql ... ``` 块。
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
            message_id=message_id,
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
        # errors 暂存到 audit 的临时属性（不入库；用完即丢）
        audit._preview_errors = errors  # type: ignore[attr-defined]
        return audit


def compute_sql_hash(sql_text: str) -> str:
    """Public re-export of SHA-256 hash (delegates to SqlSafetyService)."""
    return SqlSafetyService.compute_sql_hash(sql_text)


def canonical_json_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of payload (用于 audit 元数据 hash)。"""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()