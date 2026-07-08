"""Phase 3.6B1 C14 — AiSqlCallbackService.

处理 ``business_domain == "ai_sql"`` 的 callback items（plan §6.5）。

输入：CollectorRun + callback_items（raw_result: {columns, rows,
result_status, duration_ms, error_code, ...} + business_context: {audit_id,
session_id}）。

输出：
1. 条件 UPDATE dbops.ai_sql_audit：
   - 仅当 execution_status IN ('pending','running') 时更新（幂等）
   - SET execution_status='success'/'failed'/'timeout'、row_count、
     duration_ms、completed_at、error_message
2. 幂等写 dbops.ai_chat_message(message_type='sql_result', role=
   'assistant', parent_message_id=audit.message_id)：
   - 幂等键：UNIQUE(metadata->>'audit_id') WHERE message_type='sql_result'
     （DDL: uq_ai_chat_message_sql_result_audit）

设计要点：
- 单条 item 异常 → log + continue（不破坏主 callback 事务）
- callback 只解析 business_context.audit_id 反查数据库；
  session_id 从 audit.session_id 反查（plan §6.2）
- 复用 AiSchemaSnapshotCallbackService 的 save_snapshots 模板
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ai import (
    AiChatMessage,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
)
from app.models.dbops_assets import DbInstance, DbType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def save_execution_results(
    db: Session,
    *,
    run: Any,
    callback_items: Iterable[Any],
) -> int:
    """Persist ``business_domain='ai_sql'`` callback items to ``ai_sql_audit``.

    Returns:
        成功更新的 audit 行数（含状态机推进 + chat_message 落库）
    """
    written = 0
    for cb in callback_items:
        business_domain = getattr(cb, "business_domain", None) or ""
        check_code = getattr(cb, "check_code", None) or ""
        if business_domain != "ai_sql":
            continue
        # Defensive: 只 DB_READONLY_SQL_EXEC 驱动 ai_sql 落库
        if check_code != "DB_READONLY_SQL_EXEC":
            logger.debug(
                "ai_sql callback skipped: check_code=%s not DB_READONLY_SQL_EXEC",
                check_code,
            )
            continue
        try:
            _save_one(db, run=run, cb=cb)
            written += 1
        except Exception:
            logger.exception(
                "ai_sql callback save failed: run_id=%s item_key=%s",
                getattr(run, "run_id", "?"),
                getattr(cb, "item_key", "?"),
            )
            continue
    return written


# ---------------------------------------------------------------------------
# Per-item save
# ---------------------------------------------------------------------------

def _save_one(db: Session, *, run: Any, cb: Any) -> None:
    """Update one ai_sql_audit row + write ai_chat_message(sql_result)."""
    # ---- 解析 business_context → audit_id ----
    business_context = _extract_business_context(cb)
    audit_id = business_context.get("audit_id")
    if not audit_id:
        raise ValueError(
            f"callback item missing business_context.audit_id "
            f"(item_key={getattr(cb, 'item_key', '?')})"
        )
    audit_id = int(audit_id)

    # ---- 解析 raw_result ----
    raw = getattr(cb, "raw_result", None) or {}
    if not isinstance(raw, dict):
        raw = {}

    columns = raw.get("columns") if isinstance(raw.get("columns"), list) else []
    rows = raw.get("rows") if isinstance(raw.get("rows"), list) else []
    result_status = (
        (getattr(cb, "result_status", None) or raw.get("result_status") or raw.get("rc") or "")
    ).lower()
    error_code = (raw.get("error_code") if isinstance(raw.get("error_code"), str) else "") or ""
    duration_ms = _to_int(raw.get("duration_ms"))
    if duration_ms == 0:
        cb_duration = _to_int(getattr(cb, "duration_ms", None))
        if cb_duration:
            duration_ms = cb_duration

    # ---- 决定 execution_status ----
    item_status = (getattr(cb, "status", "") or "").lower()
    error_message = (
        (getattr(cb, "message", "") or "")
        or (raw.get("stderr") if isinstance(raw.get("stderr"), str) else "")
        or error_code
    )[:4000]

    if result_status in ("ok", "success", "verified", "normal") and item_status in (
        "verified", "success", "collected", "ok"
    ):
        new_status = AiSqlAuditExecutionStatus.SUCCESS
        derived_error_code: Optional[str] = None
    elif item_status in ("timeout",):
        new_status = AiSqlAuditExecutionStatus.TIMEOUT
        derived_error_code = error_code or "EXECUTION_TIMEOUT"
    elif item_status in ("failed", "error", "missing") or result_status in (
        "error", "failed"
    ):
        new_status = AiSqlAuditExecutionStatus.FAILED
        derived_error_code = error_code or "EXECUTION_FAILED"
    else:
        # 未知 / 缺字段 → failed (NO_RESULT)
        new_status = AiSqlAuditExecutionStatus.FAILED
        derived_error_code = error_code or "NO_RESULT"
        if not error_message:
            error_message = (
                f"collector returned unknown result_status={result_status!r} "
                f"item_status={item_status!r}"
            )[:4000]

    row_count = len(rows) if isinstance(rows, list) else 0

    # ---- 找 audit 行（SELECT ... FOR UPDATE）----
    audit = (
        db.query(AiSqlAudit)
        .filter(AiSqlAudit.id == audit_id)
        .with_for_update()
        .first()
    )
    if audit is None:
        raise ValueError(f"audit_id={audit_id} not found for callback")

    # ---- 幂等 UPDATE：仅当原状态 IN ('pending','running') 时更新 ----
    now = _now()
    update_payload: dict[str, Any] = {
        "execution_status": new_status,
        "completed_at": now,
        "duration_ms": int(duration_ms) if duration_ms > 0 else audit.duration_ms,
        "row_count": int(row_count) if row_count > 0 else audit.row_count,
        "error_message": (
            error_message if new_status != AiSqlAuditExecutionStatus.SUCCESS
            else None
        ),
    }
    if derived_error_code:
        update_payload["error_message"] = (
            f"[{derived_error_code}] {error_message}"[:4000]
            if error_message else f"[{derived_error_code}]"
        )

    res = db.execute(
        update(AiSqlAudit)
        .where(
            AiSqlAudit.id == audit_id,
            AiSqlAudit.execution_status.in_(
                (AiSqlAuditExecutionStatus.PENDING, AiSqlAuditExecutionStatus.RUNNING)
            ),
        )
        .values(**update_payload)
    )

    if res.rowcount == 0:
        # 已是终态或被外部 force 改写，跳过（不写 chat_message 避免冲掉旧 callback）
        logger.info(
            "ai_sql callback idempotent skip: audit_id=%s already terminal "
            "(current_status=%s)",
            audit_id, audit.execution_status,
        )
        return

    # ---- 写 ai_chat_message(message_type='sql_result') ----
    if audit.message_id and audit.session_id:
        _write_sql_result_chat_message(
            db,
            audit=audit,
            columns=columns,
            rows=rows,
            row_count=row_count,
            duration_ms=duration_ms,
            status=new_status,
            error_message=error_message if new_status != AiSqlAuditExecutionStatus.SUCCESS else None,
        )

    logger.info(
        "ai_sql callback saved: audit_id=%s status=%s row_count=%d duration_ms=%d "
        "item_status=%s result_status=%s",
        audit_id, new_status, row_count, duration_ms,
        item_status, result_status,
    )


def _write_sql_result_chat_message(
    db: Session,
    *,
    audit: AiSqlAudit,
    columns: list[Any],
    rows: list[Any],
    row_count: int,
    duration_ms: int,
    status: str,
    error_message: Optional[str],
) -> None:
    """幂等写 ai_chat_message(message_type='sql_result')。

    幂等键：UNIQUE(metadata->>'audit_id') WHERE message_type='sql_result'
    （DDL: uq_ai_chat_message_sql_result_audit）。
    """
    if audit.session_id is None or audit.message_id is None:
        return

    payload = {
        "columns": list(columns) if isinstance(columns, list) else [],
        "rows": list(rows) if isinstance(rows, list) else [],
        "row_count": int(row_count),
        "duration_ms": int(duration_ms),
        "status": status,
        "error_message": error_message,
        "executed_at": _now().isoformat(),
    }

    chat_msg = AiChatMessage(
        session_id=int(audit.session_id),
        user_id=audit.user_id,
        client_request_id=None,
        role="assistant",
        message_type="sql_result",
        status="completed",
        content=json.dumps(payload, ensure_ascii=False, default=str),
        parent_message_id=int(audit.message_id),
        metadata_json={
            "audit_id": int(audit.id),
            "execution_status": status,
            "row_count": int(row_count),
            "duration_ms": int(duration_ms),
        },
        attempt_count=0,
    )
    db.add(chat_msg)
    try:
        db.flush()
        audit.result_message_id = int(chat_msg.id)
    except IntegrityError:
        db.rollback()
        logger.info(
            "ai_sql chat_message sql_result already exists for audit_id=%s "
            "(uq_ai_chat_message_sql_result_audit)",
            audit.id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_business_context(cb: Any) -> dict[str, Any]:
    """从 callback item 的 business_context 字段解 audit_id / session_id。

    解析优先级（C16-F2 闭环）：
    1. ``cb.business_context`` 字段（dispatch 时由 dbops 注入，AWX 回传）
    2. ``cb.item_key`` 解析：``ai_sql:{audit_id}:{instance_id}`` 格式
       （item_key 是 ai_sql_execute_service 创建时拼出，是 fallback 兜底）
    """
    bc = getattr(cb, "business_context", None)
    parsed: dict[str, Any] = {}
    if bc is not None:
        if isinstance(bc, str):
            try:
                bc = json.loads(bc)
            except (json.JSONDecodeError, ValueError):
                bc = None
        if isinstance(bc, dict):
            nested = bc.get("business_context")
            if isinstance(nested, dict):
                parsed = dict(nested)
            else:
                parsed = dict(bc)

    # ---- 兜底：item_key 解析（AWX 没透传 business_context 时的最后保险）----
    if "audit_id" not in parsed:
        item_key = getattr(cb, "item_key", None) or ""
        if isinstance(item_key, str) and item_key.startswith("ai_sql:"):
            parts = item_key.split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                parsed["audit_id"] = int(parts[1])
    return parsed


def _resolve_db_type_code(db: Session, instance_id: int) -> str:
    """Map DbInstance → DbType.type_code（uppercase），fallback POSTGRESQL。"""
    try:
        inst = (
            db.query(DbInstance)
            .filter(DbInstance.id == instance_id)
            .first()
        )
        if inst is None:
            return "POSTGRESQL"
        db_type_id = getattr(inst, "db_type_id", None)
        if db_type_id is None:
            return "POSTGRESQL"
        db_type = (
            db.query(DbType)
            .filter(DbType.id == db_type_id)
            .first()
        )
        if db_type is None:
            return "POSTGRESQL"
        code = getattr(db_type, "type_code", None)
        if not code:
            return "POSTGRESQL"
        return str(code).upper()
    except Exception:
        logger.exception("db_type_code lookup failed for instance_id=%s", instance_id)
        return "POSTGRESQL"


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _now() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)