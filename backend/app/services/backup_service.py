"""Phase 3.5: backup status snapshot collection service.

Public surface:
    * :func:`validate_sql` — pure safety check, no DB connection.
    * :func:`launch_collect` — build backup_status collector_items + AWX one-shot.
    * :func:`save_snapshot` — write a single backup_status snapshot per callback item.
    * :func:`list_latest` — query latest snapshot per (instance, backup_type) joined
      with asset tables.
    * :func:`list_history` — raw ``backup_status_snapshot`` rows for a given instance.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dbops_assets import (
    BackupStatusSnapshot,
    DbInstance,
    DbType,
    Server,
)
from app.services.awx_service import AwxService, AwxServiceError
from app.services.sql_safety_service import SqlSafetyService


def _now() -> datetime:
    """Naive local-time stamp consistent with other services."""
    return datetime.now()


# ---------------------------------------------------------------------------
# SQL safety
# ---------------------------------------------------------------------------


def validate_sql(*, db_type_code: str, sql_text: str) -> dict[str, Any]:
    """Pure readonly validation, no DB connection."""
    return SqlSafetyService.validate_sql_readonly(sql_text=sql_text, db_type_code=db_type_code)


# ---------------------------------------------------------------------------
# Launch collect
# ---------------------------------------------------------------------------


def launch_collect(
    db: Session,
    *,
    instance_ids: list[int],
    db_type_code: str,
    backup_type: Optional[str],
    sql_text: str,
    timeout_seconds: int,
    max_rows: int,
    requested_by: str,
) -> dict[str, Any]:
    """Build a ``business_domain=backup_status`` AWX run and launch it.

    Returns ``{collector_run_id, status, awx_job_id}``.
    """
    check = SqlSafetyService.validate_sql_readonly(sql_text=sql_text, db_type_code=db_type_code)
    if not check["valid"]:
        raise ValueError("SQL 安全校验未通过: " + "; ".join(check["errors"]))

    if not (1 <= int(timeout_seconds) <= 120):
        raise ValueError("timeout_seconds 必须在 1~120 之间")
    if not (1 <= int(max_rows) <= 1000):
        raise ValueError("max_rows 必须在 1~1000 之间")

    db_type_code_norm = (db_type_code or "").strip().lower()
    if not db_type_code_norm:
        raise ValueError("db_type_code 不能为空")

    rows = (
        db.query(DbInstance, Server, DbType)
        .join(Server, Server.id == DbInstance.server_id)
        .join(DbType, DbType.id == DbInstance.db_type_id)
        .filter(DbInstance.id.in_(instance_ids))
        .all()
    )
    if not rows:
        raise LookupError("未找到任何 instance")

    items: list[dict[str, Any]] = []
    for instance, server, db_type in rows:
        actual_db_type = (db_type.type_code or "").lower() if db_type else ""
        if actual_db_type != db_type_code_norm:
            raise ValueError(
                f"实例 {instance.id} 的 db_type={actual_db_type} 与请求 db_type_code={db_type_code_norm} 不一致"
            )
        if not server:
            raise LookupError(f"实例 {instance.id} 关联服务器缺失")
        if not instance.port or int(instance.port) < 1:
            raise ValueError(f"实例 {instance.id} 端口无效")

        item: dict[str, Any] = {
            "item_key": "",  # filled after run_id is known
            "check_code": "DB_READONLY_SQL_EXEC",
            "executor_type": "db_sql_readonly",
            "business_domain": "backup_status",
            "target_scope": "db_instance",
            "asset_id": int(instance.id),
            "target_host": str(server.ip_address),
            "target_port": int(instance.port),
            "db_type_code": db_type_code_norm,
            "database_name": instance.database_name or "master",
            "service_name": instance.service_name,
            "timeout_seconds": int(timeout_seconds),
            "rule_config": {
                "sql_text": sql_text,
                "timeout_seconds": int(timeout_seconds),
                "max_rows": int(max_rows),
                "severity": "warning",
            },
            "task_id": None,
            "inspection_item_id": None,
            "item_code": None,
            "policy_id": None,
            "backup_type": backup_type,
        }
        # Resolve credential the same way the inspection flow does — best
        # effort. The EE will surface AUTHENTICATION_FAILED on failure.
        try:
            from app.services.credential_resolver_service import CredentialResolverService

            credential = CredentialResolverService.resolve_for_item(
                db,
                target_scope="db_instance",
                asset={"id": int(instance.id), "server_id": int(instance.server_id)},
                check_code="DB_READONLY_SQL_EXEC",
            )
        except Exception:
            credential = None
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
        items.append(item)

    # Build the CollectorRun. run_id is shared across all items.
    run_id = f"backup-status-{secrets.token_hex(6)}"
    for item in items:
        item["item_key"] = (
            f"backup_status:{run_id}:{item.get('backup_type') or 'default'}:{item['asset_id']}"
        )

    from app.models.dbops_assets import CollectorRun  # local import to avoid cycle

    settings = get_settings()
    base = settings.DBOPS_CALLBACK_BASE_URL or settings.DBOPS_API_BASE_URL
    callback_url = f"{base.rstrip('/')}/api/v1/collector/callback/"

    first_instance, first_server, _ = rows[0]
    run = CollectorRun(
        run_id=run_id,
        db_instance_id=int(first_instance.id),
        server_id=int(first_server.id) if first_server else None,
        job_type="BACKUP_STATUS",
        target_scope="db_instance",
        target_host=str(first_server.ip_address) if first_server else "",
        target_port=int(first_instance.port) if first_instance.port else 0,
        request_payload={
            "run_type": "backup_status",
            "business_domain": "backup_status",
            "check_codes": ["DB_READONLY_SQL_EXEC"],
            "items": items,
            "sql_text": sql_text,
            "sql_hash": check["sql_hash"],
            "db_type_code": db_type_code_norm,
            "backup_type": backup_type,
            "instance_ids": [int(i) for i in instance_ids],
            "requested_by": requested_by,
        },
        extra_vars={"items": items},
        status="pending",
        created_at=_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        launch = AwxService.launch_job(
            extra_vars={
                "schema_version": 1,
                "run_id": run_id,
                "run_type": "backup_status",
                "callback_url": callback_url,
                "items": items,
            }
        )
        awx_job_id = launch.get("awx_job_id")
        run.awx_job_id = awx_job_id
        run.status = "launched"
        db.commit()
        return {
            "collector_run_id": int(run.id),
            "status": "launched",
            "awx_job_id": awx_job_id,
        }
    except AwxServiceError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        db.commit()
        return {
            "collector_run_id": int(run.id),
            "status": "failed",
            "awx_job_id": None,
        }


# ---------------------------------------------------------------------------
# Callback → snapshot row
# ---------------------------------------------------------------------------


# Case-insensitive column → field mapping. We do not require callers to
# return columns in a fixed case; the convention is just "have a column
# named like the key below" so the service is robust to dba.sql style.
_FIELD_ALIASES: dict[str, list[str]] = {
    "backup_type": ["backup_type", "BACKUP_TYPE"],
    "last_status": ["last_status", "LAST_STATUS", "status"],
    "last_success_at": ["last_success_at", "LAST_SUCCESS_AT", "end_time"],
    "last_failure_at": ["last_failure_at", "LAST_FAILURE_AT"],
    "recovery_point_at": ["recovery_point_at", "RECOVERY_POINT_AT"],
    "age_minutes": ["age_minutes", "AGE_MINUTES"],
    "duration_seconds": ["duration_seconds", "DURATION_SECONDS"],
    "backup_size_mb": ["backup_size_mb", "BACKUP_SIZE_MB"],
}


def _row_get(row: dict[str, Any], key: str) -> Any:
    for alias in _FIELD_ALIASES.get(key, [key]):
        if alias in row and row[alias] is not None:
            return row[alias]
    return None


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_status(value: Any) -> str:
    if value is None:
        return "unknown"
    s = str(value).strip().lower()
    if s in ("success", "ok", "succeeded"):
        return "success"
    if s in ("failed", "error", "failure"):
        return "failed"
    if s in ("warning", "warn"):
        return "warning"
    return "unknown"


def save_snapshot(
    db: Session,
    *,
    run,
    callback_items: list[Any],
) -> int:
    """Persist ``business_domain=backup_status`` callback items as snapshot rows.

    Returns the number of rows written. The function is defensive — a
    single bad item logs and continues so one bad row cannot drop the
    whole callback.
    """
    written = 0
    for cb in callback_items:
        business_domain = getattr(cb, "business_domain", None) or ""
        if business_domain != "backup_status":
            continue
        try:
            asset_id = int(getattr(cb, "asset_id", 0) or 0)
            if asset_id <= 0:
                continue
            raw = getattr(cb, "raw_result", None) or {}
            raw_dict = raw if hasattr(raw, "get") else {}
            rows = raw_dict.get("rows") if hasattr(raw_dict, "get") else None
            rows = rows or []
            columns = raw_dict.get("columns") if hasattr(raw_dict, "get") else None
            columns = columns or []

            row_dict: dict[str, Any] = {}
            if rows and columns:
                first = rows[0]
                if isinstance(first, dict):
                    row_dict = first
                elif isinstance(first, (list, tuple)) and len(first) == len(columns):
                    row_dict = {columns[i]: first[i] for i in range(len(columns))}

            status = _to_status(_row_get(row_dict, "last_status"))
            if not rows:
                # Empty result-set is also "unknown" — the SQL ran but
                # returned nothing. That usually means the DBA's query
                # was mis-scoped, not that the system is healthy.
                status = "unknown"

            backup_type = _row_get(row_dict, "backup_type") or getattr(cb, "backup_type", None)
            policy_id = getattr(cb, "policy_id", None)

            evidence = {
                "columns": columns,
                "rows": rows[:50],  # truncate, raw is in callback body
                "result_status": raw_dict.get("result_status") if hasattr(raw_dict, "get") else None,
                "duration_ms": raw_dict.get("duration_ms") if hasattr(raw_dict, "get") else None,
                "sql_hash": raw_dict.get("sql_hash") if hasattr(raw_dict, "get") else None,
                "connector": raw_dict.get("connector") if hasattr(raw_dict, "get") else None,
                "error_code": raw_dict.get("error_code") if hasattr(raw_dict, "get") else None,
                "stderr": (raw_dict.get("stderr") if hasattr(raw_dict, "get") else None) or "",
                "collector_run_item_id": getattr(cb, "id", None),
            }

            snap = BackupStatusSnapshot(
                instance_id=asset_id,
                policy_id=int(policy_id) if policy_id else None,
                collector_run_id=int(getattr(run, "id", 0) or 0) or None,
                collector_run_item_id=getattr(cb, "id", None),
                backup_type=backup_type,
                source_type="db_sql",
                last_status=status,
                last_success_at=_parse_ts(_row_get(row_dict, "last_success_at")),
                last_failure_at=_parse_ts(_row_get(row_dict, "last_failure_at")),
                recovery_point_at=_parse_ts(_row_get(row_dict, "recovery_point_at")),
                age_minutes=_to_int(_row_get(row_dict, "age_minutes")),
                duration_seconds=_to_int(_row_get(row_dict, "duration_seconds")),
                backup_size_mb=_to_float(_row_get(row_dict, "backup_size_mb")),
                message=(getattr(cb, "message", None) or "")[:4000] or None,
                evidence=evidence,
                collected_at=_now(),
                created_at=_now(),
            )
            db.add(snap)
            written += 1
        except Exception:
            # Never let a single bad item break the inspection callback.
            # Callers wrap this in a try/except anyway; we stay quiet here.
            continue
    if written:
        db.commit()
    return written


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


def list_latest(
    db: Session,
    *,
    db_type_code: Optional[str] = None,
    last_status: Optional[str] = None,
    backup_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Latest snapshot per (instance_id, backup_type) joined with asset info.

    P0 strategy: fetch ordered rows then de-dup by (instance, backup_type)
    in Python. Acceptable for P0 because the snapshot table is small.
    The ``v_backup_status_latest`` view exists as a forward-compatible
    upgrade path; this implementation trades some efficiency for SQL
    portability across PG versions.
    """
    rows = (
        db.query(BackupStatusSnapshot, DbInstance, DbType, Server)
        .join(DbInstance, DbInstance.id == BackupStatusSnapshot.instance_id)
        .join(DbType, DbType.id == DbInstance.db_type_id)
        .join(Server, Server.id == DbInstance.server_id)
        .order_by(
            BackupStatusSnapshot.instance_id.asc(),
            BackupStatusSnapshot.backup_type.asc().nulls_first(),
            BackupStatusSnapshot.collected_at.desc(),
        )
        .limit(limit * 4)
        .all()
    )

    seen: set[tuple[int, str]] = set()
    latest: list[dict[str, Any]] = []
    for snap, instance, db_type, server in rows:
        key = (int(snap.instance_id), snap.backup_type or "")
        if key in seen:
            continue
        seen.add(key)
        if db_type_code and (db_type.type_code or "").lower() != db_type_code.lower():
            continue
        if last_status and (snap.last_status or "").lower() != last_status.lower():
            continue
        if backup_type and (snap.backup_type or "") != backup_type:
            continue
        if keyword:
            kw = keyword.lower()
            blob = " ".join(
                [
                    instance.instance_name or "",
                    instance.instance_code or "",
                    server.hostname or "",
                    str(server.ip_address or ""),
                    snap.backup_type or "",
                    snap.message or "",
                ]
            ).lower()
            if kw not in blob:
                continue
        latest.append(
            {
                "id": int(snap.id),
                "instance_id": int(snap.instance_id),
                "instance_name": instance.instance_name,
                "db_type_code": db_type.type_code,
                "host": str(server.ip_address or ""),
                "port": int(instance.port or 0),
                "backup_type": snap.backup_type,
                "source_type": snap.source_type,
                "last_status": snap.last_status,
                "last_success_at": snap.last_success_at,
                "last_failure_at": snap.last_failure_at,
                "recovery_point_at": snap.recovery_point_at,
                "age_minutes": snap.age_minutes,
                "duration_seconds": snap.duration_seconds,
                "backup_size_mb": float(snap.backup_size_mb) if snap.backup_size_mb is not None else None,
                "message": snap.message,
                "collected_at": snap.collected_at,
                "collector_run_id": snap.collector_run_id,
                "collector_run_item_id": snap.collector_run_item_id,
            }
        )
        if len(latest) >= limit:
            break
    return latest


def list_history(
    db: Session,
    *,
    instance_id: Optional[int] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Raw backup_status_snapshot rows, optionally filtered by instance_id."""
    q = db.query(BackupStatusSnapshot)
    if instance_id is not None:
        q = q.filter(BackupStatusSnapshot.instance_id == int(instance_id))
    rows = q.order_by(BackupStatusSnapshot.collected_at.desc()).limit(limit).all()
    return [
        {
            "id": int(s.id),
            "instance_id": int(s.instance_id),
            "backup_type": s.backup_type,
            "source_type": s.source_type,
            "last_status": s.last_status,
            "last_success_at": s.last_success_at,
            "last_failure_at": s.last_failure_at,
            "recovery_point_at": s.recovery_point_at,
            "age_minutes": s.age_minutes,
            "duration_seconds": s.duration_seconds,
            "backup_size_mb": float(s.backup_size_mb) if s.backup_size_mb is not None else None,
            "message": s.message,
            "evidence": s.evidence or {},
            "collected_at": s.collected_at,
            "created_at": s.created_at,
        }
        for s in rows
    ]
