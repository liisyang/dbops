"""Phase 3.6B1 C14 — AiSqlExecuteService.

SQL Execute 业务编排（plan §6 + §10 + §4.5 + §19 P0-6）：

  事务 1（DB）：
    1. 功能开关 AI_SQL_EXECUTION_ENABLED (503)
    2. 校验 audit 存在 + preview_safety_status='passed' (404 / 409)
    3. 重新校验 schema snapshot is_current + schema_policy_hash 一致 (409)
    4. 重新跑 SqlSafetyService.validate_with_ast 对 approved_sql 做 execution
       safety 校验 (422)
    5. 条件 UPDATE audit (execution_status IN ('not_requested','failed',
       'timeout','cancelled')) → 'running' + collector_run_id/item_id +
       executed_at（plan §19 P0-6）

  事务外 / 事务 2：
    6. 内联构造 CollectorRun(business_domain='ai_sql', check_code=
       'DB_READONLY_SQL_EXEC', job_type='SQL_VERIFY', request_payload=
       {run_type='sql_verify', business_domain='ai_sql', items=[item]})
    7. 内联构造 CollectorRunItem (rule_config.sql_text=approved_sql,
       business_context=JSON({"audit_id","session_id"}), executor_type=
       'db_sql_readonly')
    8. AwxService.launch_job(extra_vars={...items}, credentials=
       [awx_credential_id])；凭证由 CredentialResolverService.resolve_for_item
       (check_code='DB_READONLY_SQL_EXEC') 解析
    9. 失败：UPDATE audit execution_status='failed' + error_message
   10. 成功：UPDATE audit execution_status='running' + awx_job_id + commit

设计要点：
- 复用 InspectionService.verify_sql 内联构造模板（业务逻辑可复用 ~80%）
- 不走 CheckItemBuilderRegistry（避免与 DB_READONLY_SQL_EXEC Builder 冲突；
  plan §6.1 P1 修正）
- business_context 标准化为 {"audit_id","session_id"} JSON（plan §6.2）
- 条件 UPDATE 防并发重复 launch（force=True 时覆盖 pending/running）
- callback 时只解析 business_context.audit_id 反查数据库（plan §6.5）

错误码映射（plan §11）：
  404 — AuditNotFoundError
  409 — AuditNotPassedError / SnapshotPolicyMismatchError / AuditAlreadyRunningError
  422 — AuditUnsafeOnExecuteError
  502 — AwxLaunchError
  503 — FeatureDisabledError
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import update as _sa_update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import (
    AiChatSession,
    AiSchemaSnapshot,
    AiSqlAudit,
    AiSqlAuditExecutionSafety,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.models.dbops_assets import (
    CollectorRun,
    CollectorRunItem,
    DbInstance,
    Server,
)
from app.services.awx_service import AwxService, AwxServiceError
from app.services.credential_resolver_service import CredentialResolverService
from app.services.sql_safety_service import SqlSafetyService

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常（与 C10 snapshot service / C3 chat service 命名对齐）
# =============================================================================
class AiSqlExecuteError(Exception):
    """SQL Execute 服务基类异常。"""


class AuditNotFoundError(AiSqlExecuteError):
    """audit_id 不存在 → 404。"""


class AuditNotPassedError(AiSqlExecuteError):
    """audit.preview_safety_status != 'passed' → 409。"""


class SnapshotPolicyMismatchError(AiSqlExecuteError):
    """schema snapshot 不再 is_current 或 policy_hash 不一致 → 409。"""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class AuditAlreadyRunningError(AiSqlExecuteError):
    """execution_status IN ('pending','running') 且未 force → 409。"""


class AuditUnsafeOnExecuteError(AiSqlExecuteError):
    """approved_sql 在 Execute 时再次 AST 校验失败 → 422。"""

    def __init__(self, message: str, *, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


class FeatureDisabledError(AiSqlExecuteError):
    """AI_SQL_EXECUTION_ENABLED=false → 503。"""


class AwxLaunchError(AiSqlExecuteError):
    """AWX launch 失败（audit 已标记 failed）→ 502。"""


class AuditOwnershipError(AiSqlExecuteError):
    """audit 不属于 requested_by → 403。

    检查两步（plan §21.3 C16-5 P0-4）：
    1. audit.user_id != requested_by.id
    2. audit.session.user_id != requested_by.id（当 session 存在时）

    任一不匹配都抛此异常；防止用户在错误上下文里触发别人 audit 的 Execute。
    """


# =============================================================================
# Service 返回类型
# =============================================================================
@dataclass
class ExecuteResult:
    """execute() 内部返回（audit_id + collector / awx 引用）。"""

    audit: AiSqlAudit


# =============================================================================
# AiSqlExecuteService
# =============================================================================
class AiSqlExecuteService:
    """SQL Execute 业务编排（plan §6 + §10 + §19 P0-6）。"""

    # 与 AiSqlPreviewService 一致（Execute 时复用 Preview 的安全策略版本）
    SAFETY_POLICY_VERSION = "2026-06-28-v1"

    # SQL Execute 超时（seconds）—— AWX collector 端 timeout_seconds
    DEFAULT_TIMEOUT_SECONDS = 60

    # SQL Execute max_rows（plan §10）
    DEFAULT_MAX_ROWS = 200

    # ------------------------------------------------------------------
    # execute — 核心端点
    # ------------------------------------------------------------------
    @classmethod
    def execute(
        cls,
        db: Session,
        *,
        audit_id: int,
        requested_by: Optional[Any] = None,
        force: bool = False,
    ) -> ExecuteResult:
        """Execute approved_sql via AWX collector。

        流程（plan §6 + §10 + §19 P0-6）：
          1. 功能开关 (503 FeatureDisabledError)
          2. 校验 audit 存在 + preview_safety_status='passed' (404/409)
          3. 重新校验 schema snapshot is_current + schema_policy_hash 一致 (409)
          4. AST 二次校验 approved_sql（防御 preview 后被人工修改）(422)
          5. 条件 UPDATE audit → 'running' + collector_run_id/item_id + executed_at
          6. 内联构造 CollectorRun + CollectorRunItem
          7. AwxService.launch_job（凭证注入）
          8. 失败回滚 audit execution_status='failed'
          9. 成功提交，audit 保留 running 状态等待 callback

        Raises:
            AuditNotFoundError: audit_id 不存在 → 404
            AuditOwnershipError: audit.user_id / session.user_id 与 requested_by 不匹配 → 403
            AuditNotPassedError: preview_safety_status != 'passed' → 409
            SnapshotPolicyMismatchError: snapshot 不一致 → 409
            AuditUnsafeOnExecuteError: AST 二次校验失败 → 422
            AuditAlreadyRunningError: execution_status pending/running 且未 force → 409
            FeatureDisabledError: AI_SQL_EXECUTION_ENABLED=false → 503
            AwxLaunchError: AWX launch 失败 → 502
        """
        settings = get_settings()

        # 1. 功能开关
        if not settings.AI_SQL_EXECUTION_ENABLED:
            raise FeatureDisabledError("AI_SQL_EXECUTION_ENABLED=false")

        # 2. 校验 audit
        audit = (
            db.query(AiSqlAudit)
            .filter(AiSqlAudit.id == int(audit_id))
            .with_for_update()
            .first()
        )
        if audit is None:
            raise AuditNotFoundError(f"ai_sql_audit id={audit_id} not found")

        # step 1.5 — ownership 校验（C16-5 P0-4，plan §21.3）
        # 防止用户在错误上下文里触发别人 audit 的 Execute；
        # 当 requested_by 为 None（内部调用）时跳过此校验。
        # 检查两层：audit.user_id 直接归属 + audit.session.user_id 间接归属
        # （session 与 audit 同源时可兜底）。
        if requested_by is not None:
            requester_id = getattr(requested_by, "id", None)
            audit_owner_id = getattr(audit, "user_id", None)
            if (
                audit_owner_id is not None
                and requester_id is not None
                and audit_owner_id != requester_id
            ):
                raise AuditOwnershipError(
                    f"audit {audit_id} user_id={audit_owner_id} != "
                    f"requester id={requester_id}"
                )
            if audit.session_id is not None:
                chat_session = (
                    db.query(AiChatSession)
                    .filter(AiChatSession.id == int(audit.session_id))
                    .first()
                )
                if chat_session is not None:
                    session_owner_id = getattr(chat_session, "user_id", None)
                    if (
                        session_owner_id is not None
                        and requester_id is not None
                        and session_owner_id != requester_id
                    ):
                        raise AuditOwnershipError(
                            f"audit {audit_id} session {audit.session_id} "
                            f"user_id={session_owner_id} != requester id={requester_id}"
                        )

        if audit.preview_safety_status != AiSqlAuditPreviewSafety.PASSED:
            raise AuditNotPassedError(
                f"audit {audit_id} preview_safety_status={audit.preview_safety_status!r}; "
                f"only 'passed' audits can be executed"
            )

        if audit.approved_sql is None or not str(audit.approved_sql).strip():
            raise AuditNotPassedError(
                f"audit {audit_id} has no approved_sql (preview passed but empty)"
            )

        # 5 预条件：execution_status 仅在 not_requested/failed/timeout/cancelled
        # 时才允许 launch；pending/running 时若未 force → 409
        current_exec_status = audit.execution_status or AiSqlAuditExecutionStatus.NOT_REQUESTED
        if current_exec_status in (
            AiSqlAuditExecutionStatus.PENDING,
            AiSqlAuditExecutionStatus.RUNNING,
        ):
            if not force:
                raise AuditAlreadyRunningError(
                    f"audit {audit_id} execution_status={current_exec_status!r}; "
                    f"already in flight (use force=true to re-run)"
                )

        # 3. Schema snapshot 强绑定校验
        if audit.schema_snapshot_id is None or not audit.schema_policy_hash:
            raise SnapshotPolicyMismatchError(
                f"audit {audit_id} missing schema_snapshot_id or schema_policy_hash",
                reason="audit_missing_schema_binding",
            )

        snap = (
            db.query(AiSchemaSnapshot)
            .filter(AiSchemaSnapshot.id == int(audit.schema_snapshot_id))
            .first()
        )
        if snap is None:
            raise SnapshotPolicyMismatchError(
                f"audit {audit_id} references missing snapshot {audit.schema_snapshot_id}",
                reason="snapshot_not_found",
            )
        if not snap.is_usable():
            raise SnapshotPolicyMismatchError(
                f"snapshot {snap.id} not usable "
                f"(status={snap.status}, is_current={snap.is_current}, "
                f"expires_at={snap.expires_at})",
                reason="snapshot_not_usable",
            )
        if snap.snapshot_hash and (
            str(audit.schema_policy_hash or "") != str(snap.snapshot_hash or "")
        ):
            raise SnapshotPolicyMismatchError(
                f"audit.schema_policy_hash ({audit.schema_policy_hash}) "
                f"!= snapshot.snapshot_hash ({snap.snapshot_hash}); "
                f"re-preview required",
                reason="policy_hash_mismatch",
            )

        # 4. AST 二次校验（防御 preview 后 audit 行被人工修改 / DB 触发器
        # 等场景；保证 Execute 时 SQL 仍满足只读约束）
        safety_check = SqlSafetyService.validate_with_ast(
            sql_text=str(audit.approved_sql),
            db_type_code=str(audit.db_type_code or "POSTGRESQL"),
            allowed_tables=list(snap.allowed_tables or []),
            allowed_columns=dict(snap.allowed_columns or {}),
            denied_columns=list(snap.denied_columns or []),
            max_rows=cls.DEFAULT_MAX_ROWS,
        )
        if not safety_check.get("valid"):
            errors_list = list(safety_check.get("errors") or [])
            audit.execution_safety_status = AiSqlAuditExecutionSafety.REJECTED
            audit.execution_safety_reason = (
                f"Execute-time AST rejected: {'; '.join(errors_list[:3])}"[:4000]
            )
            audit.error_message = audit.execution_safety_reason
            db.commit()
            raise AuditUnsafeOnExecuteError(
                f"approved_sql failed AST re-check at execute time: {errors_list}",
                errors=errors_list,
            )

        # approved_sql_hash 校验（防止 approved_sql 被改写后 hash 不匹配）
        recomputed_hash = SqlSafetyService.compute_sql_hash(str(audit.approved_sql))
        if audit.approved_sql_hash and audit.approved_sql_hash != recomputed_hash:
            audit.execution_safety_status = AiSqlAuditExecutionSafety.REJECTED
            audit.execution_safety_reason = (
                f"approved_sql_hash mismatch at execute time "
                f"(stored={audit.approved_sql_hash[:12]}, recomputed={recomputed_hash[:12]})"
            )
            audit.error_message = audit.execution_safety_reason
            db.commit()
            raise AuditUnsafeOnExecuteError(
                "approved_sql_hash mismatch; audit row tampered",
                errors=["approved_sql_hash_mismatch"],
            )

        audit.execution_safety_status = AiSqlAuditExecutionSafety.PASSED
        audit.execution_safety_reason = None

        # 6/7. 构造 CollectorRun + Item
        instance = db.query(DbInstance).filter(DbInstance.id == int(audit.instance_id)).first()
        if instance is None:
            raise AuditNotFoundError(
                f"audit {audit_id} references missing db_instance {audit.instance_id}"
            )
        server = db.query(Server).filter(Server.id == int(instance.server_id)).first()
        if server is None:
            raise AuditNotFoundError(
                f"instance {audit.instance_id} has missing server {instance.server_id}"
            )

        target_host = str(server.ip_address or "")
        target_port = int(instance.port or 0)
        if target_port < 1 or target_port > 65535:
            raise AuditUnsafeOnExecuteError(
                f"instance {audit.instance_id} port={target_port} invalid",
                errors=["invalid_target_port"],
            )

        # 凭证解析（不依赖 business_domain 字段）
        credential = CredentialResolverService.resolve_for_item(
            db,
            target_scope="db_instance",
            asset={"id": int(instance.id), "server_id": int(instance.server_id)},
            check_code="DB_READONLY_SQL_EXEC",
        )

        # 标准化 business_context（plan §6.2）
        business_context = {
            "business_domain": "ai_sql",
            "business_context": {
                "audit_id": int(audit.id),
                "session_id": int(audit.session_id) if audit.session_id else None,
            },
        }

        run_id = f"ai-sql-{secrets.token_hex(6)}"
        item_key = f"ai_sql:{audit.id}:{instance.id}"

        item: dict[str, Any] = {
            "item_key": item_key,
            "check_code": "DB_READONLY_SQL_EXEC",
            "executor_type": "db_sql_readonly",
            "business_domain": "ai_sql",
            "target_scope": "db_instance",
            "asset_id": int(instance.id),
            "target_host": target_host,
            "target_port": target_port,
            "db_type_code": str(audit.db_type_code or "POSTGRESQL").lower(),
            "database_name": getattr(instance, "database_name", None) or "<default>",
            "service_name": getattr(instance, "service_name", None),
            "timeout_seconds": int(cls.DEFAULT_TIMEOUT_SECONDS),
            "rule_config": {
                "sql_text": str(audit.approved_sql),
                "timeout_seconds": int(cls.DEFAULT_TIMEOUT_SECONDS),
                "max_rows": int(cls.DEFAULT_MAX_ROWS),
                "severity": "info",
            },
            "task_id": None,
            "inspection_item_id": None,
            "item_code": None,
        }
        # business_context 注入到 item（plan §6.4 — 确保 callback 能拿到 audit_id）
        item["business_context"] = business_context
        if credential:
            item.update(
                {
                    "credential_profile_id": credential["credential_profile_id"],
                    "credential_code": credential["profile_code"],
                    "awx_credential_id": credential["awx_credential_id"],
                    "credential_role": credential["binding_role"],
                    "credential_type": credential["credential_type"],
                }
            )

        run = CollectorRun(
            run_id=run_id,
            db_instance_id=int(instance.id),
            server_id=int(instance.server_id),
            job_type="SQL_VERIFY",
            target_scope="db_instance",
            target_host=target_host,
            target_port=target_port,
            request_payload={
                "run_type": "sql_verify",
                "business_domain": "ai_sql",
                "check_codes": ["DB_READONLY_SQL_EXEC"],
                "items": [item],
                "audit_id": int(audit.id),
                "session_id": int(audit.session_id) if audit.session_id else None,
                "approved_sql_hash": audit.approved_sql_hash,
                "schema_policy_hash": audit.schema_policy_hash,
            },
            extra_vars={"items": [item]},
            status="pending",
            created_at=cls._utcnow(),
        )
        db.add(run)
        db.flush()

        run_item = CollectorRunItem(
            collector_run_id=int(run.id),
            run_id=run_id,
            item_key=item_key,
            check_code="DB_READONLY_SQL_EXEC",
            target_scope="db_instance",
            server_id=int(instance.server_id),
            db_instance_id=int(instance.id),
            target_host=target_host,
            target_port=target_port,
            timeout_seconds=int(cls.DEFAULT_TIMEOUT_SECONDS),
            status="pending",
        )
        db.add(run_item)
        db.flush()

        # 5. 条件 UPDATE audit → 'pending'（C16-5 P0-4，plan §21.4 标准 #5）
        # PENDING 是 launch 之前的中间态：audit 行已绑定 collector_run，但
        # AWX 任务尚未启动（或正在启动中）。callback 端用
        # ``WHERE execution_status IN ('pending','running')`` 兜底匹配。
        now = cls._utcnow()
        audit.execution_status = AiSqlAuditExecutionStatus.PENDING
        audit.collector_run_id = int(run.id)
        audit.collector_run_item_id = int(run_item.id)
        audit.executed_at = now
        audit.error_message = None
        db.flush()

        # 8/9. AWX launch
        try:
            creds: list[int] = []
            if credential and credential.get("awx_credential_id"):
                creds.append(int(credential["awx_credential_id"]))
            prebound_str = (settings.AWX_PREBOUND_CREDENTIAL_IDS or "").strip()
            if prebound_str:
                for p in prebound_str.split(","):
                    try:
                        pid = int(p.strip())
                        if pid not in creds:
                            creds.append(pid)
                    except ValueError:
                        pass

            callback_base = settings.COLLECTOR_CALLBACK_URL or ""
            callback_url = callback_base.rstrip("/") + "/" if callback_base else ""

            launch = AwxService.launch_job(
                extra_vars={
                    "schema_version": 1,
                    "run_id": run_id,
                    "run_type": "sql_verify",
                    "business_domain": "ai_sql",
                    "callback_url": callback_url,
                    "items": [item],
                },
                credentials=creds if creds else None,
            )
            awx_job_id = launch.get("awx_job_id")
            run.awx_job_id = int(awx_job_id) if awx_job_id else None
            run.status = "launched"
            # C16-F1：回填 audit.awx_job_id。
            # 幂等：UPDATE WHERE id=:aid AND awx_job_id IS NULL ——
            # 避免覆盖 callback 重试或异常分支已写入的值。
            # ORM 侧同步条件：仅当 audit.awx_job_id 为 None 时刷新；
            # 若 ORM 已缓存非空值（DB 同样非空），保留原值。
            if awx_job_id:
                stmt = (
                    _sa_update(AiSqlAudit)
                    .where(AiSqlAudit.id == int(audit.id))
                    .where(AiSqlAudit.awx_job_id.is_(None))
                    .values(awx_job_id=int(awx_job_id))
                )
                db.execute(stmt)
                # ORM 缓存同步：仅在原值为 None 时刷新，避免覆盖 callback
                # 重试已写入的值（与 DB IS NULL guard 语义对齐）。
                if audit.awx_job_id is None:
                    audit.awx_job_id = int(awx_job_id)
            # C16-5 P0-4：launch 成功后升级 PENDING → RUNNING（plan §21.4 标准 #5）。
            # 在 db.commit() 前显式写回 ORM，确保落库状态为 RUNNING。
            audit.execution_status = AiSqlAuditExecutionStatus.RUNNING
            db.commit()
        except AwxServiceError as exc:
            logger.warning(
                "ai_sql execute: AWX launch failed audit_id=%s run_id=%s err=%s",
                audit.id, run_id, exc,
            )
            run.status = "failed"
            run.error_message = str(exc)[:4000]
            audit.execution_status = AiSqlAuditExecutionStatus.FAILED
            audit.error_message = f"AWX launch failed: {exc}"[:4000]
            db.commit()
            db.refresh(audit)
            raise AwxLaunchError(f"AWX launch failed: {exc}") from exc
        except Exception as exc:
            logger.exception(
                "ai_sql execute: unexpected AWX launch error audit_id=%s", audit.id
            )
            audit.execution_status = AiSqlAuditExecutionStatus.FAILED
            audit.error_message = f"unexpected launch error: {exc}"[:4000]
            db.commit()
            db.refresh(audit)
            raise AwxLaunchError(f"unexpected launch error: {exc}") from exc

        db.refresh(audit)
        logger.info(
            "ai_sql execute launched: audit_id=%s run_id=%s awx_job_id=%s "
            "instance_id=%s db_type=%s",
            audit.id, run_id, awx_job_id,
            instance.id, audit.db_type_code,
        )
        return ExecuteResult(audit=audit)

    # ------------------------------------------------------------------
    # get_execution_status — 状态查询（前端轮询用）
    # ------------------------------------------------------------------
    @classmethod
    def get_execution_status(
        cls,
        db: Session,
        *,
        audit_id: int,
    ) -> AiSqlAudit:
        """查询 audit 执行状态（plan §6.1 — callback 写库后的状态）。

        Returns:
            AiSqlAudit 实例

        Raises:
            AuditNotFoundError: audit_id 不存在 → 404
        """
        audit = (
            db.query(AiSqlAudit)
            .filter(AiSqlAudit.id == int(audit_id))
            .first()
        )
        if audit is None:
            raise AuditNotFoundError(f"ai_sql_audit id={audit_id} not found")
        return audit

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)


def canonical_json_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of payload (用于 business_context 一致性 hash)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()