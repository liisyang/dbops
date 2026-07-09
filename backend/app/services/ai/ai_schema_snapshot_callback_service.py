"""Phase 3.6B0 C9 — AiSchemaSnapshotCallbackService.

处理 ``business_domain == "ai_schema"`` 的 callback items，把
``DB_SCHEMA_METADATA_COLLECTION`` 的采集结果幂等 upsert 到
``dbops.ai_sql_schema_snapshot`` 表（plan §4.2 + §4.3 + §4.4）。

设计要点（避免 C2 BE-bug1 复发）：
- 不使用 alias / metadata 字段（字段名 == JSON key 即可）
- 单条 item 异常 → 日志 + continue，绝不破坏主 callback 事务
- ``collector_run_id`` 维度去重（同一 run 多次回调覆盖，不重复落库）
- ``status == success`` 时触发两阶段发布（is_current=true / 旧切 false），DB
  层部分唯一索引 ``uq_ai_sql_schema_snapshot_current`` 兜底
- ``truncated=true`` 是硬错误（plan §4.4 P1）→ status=failed +
  error_code=RESULT_TRUNCATED
- snapshot_hash = SHA-256 (64 hex) over canonical JSON of rows —
  ``chk_ai_sql_schema_snapshot_hash_len`` 兜底长度
- 无 rows 但 status=success → failed (NO_ROWS)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.models.dbops_assets import DbInstance, DbType

# C16-F2d commit 2: system view policy force-include。
# 顶层 import 安全（policy service 只依赖 app.models.ai.AiSystemViewPolicy，
# 与本模块无循环依赖）。
from app.services.ai.ai_system_view_policy_service import (
    AiSystemViewPolicyService,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def save_snapshots(
    db: Session,
    *,
    run: Any,
    callback_items: Iterable[Any],
) -> int:
    """Persist ``business_domain='ai_schema'`` callback items to ``ai_sql_schema_snapshot``.

    返回成功写入的 snapshot 行数（含更新 + 新建）。Caller 应在
    try/except 内调用本函数，单条 item 失败不会影响主事务。
    """
    written = 0
    for cb in callback_items:
        business_domain = getattr(cb, "business_domain", None) or ""
        check_code = getattr(cb, "check_code", None) or ""
        if business_domain != "ai_schema":
            continue
        # Defensive: only DB_SCHEMA_METADATA_COLLECTION check_code drives ai_schema.
        if check_code != "DB_SCHEMA_METADATA_COLLECTION":
            logger.debug(
                "ai_schema callback skipped: check_code=%s not DB_SCHEMA_METADATA_COLLECTION",
                check_code,
            )
            continue
        try:
            _save_one(db, run=run, cb=cb)
            written += 1
        except Exception:
            # 严格对齐 backup_service.save_snapshot 的容错策略：单条 item 失败
            # 仅记录日志，不影响主 callback 事务（外层 caller 也包了 try/except，
            # 这里双重兜底）。
            logger.exception(
                "ai_schema snapshot save failed: run_id=%s item_key=%s",
                getattr(run, "run_id", "?"),
                getattr(cb, "item_key", "?"),
            )
            continue
    return written


# ---------------------------------------------------------------------------
# Per-item save
# ---------------------------------------------------------------------------

def _save_one(db: Session, *, run: Any, cb: Any) -> None:
    """Upsert a single ai_schema snapshot."""
    asset_id = int(getattr(cb, "asset_id", 0) or 0)
    if asset_id <= 0:
        raise ValueError("asset_id <= 0")

    raw = getattr(cb, "raw_result", None) or {}
    if not isinstance(raw, dict):
        raw = {}

    # ---- 解析基础字段 ----
    item_status = (getattr(cb, "status", "") or "").lower()
    message = (getattr(cb, "message", "") or "")[:4000]
    error_code = (raw.get("error_code") if isinstance(raw.get("error_code"), str) else "") or ""
    error_code = error_code[:100]  # VARCHAR(100) — truncate to avoid StringDataRightTruncation
    truncated = bool(raw.get("truncated"))
    total_rows = _to_int(raw.get("total_rows"))
    returned_rows = _to_int(raw.get("returned_rows"))
    rows = raw.get("rows") if isinstance(raw.get("rows"), list) else []
    columns = raw.get("columns") if isinstance(raw.get("columns"), list) else []
    sql_hash = (raw.get("sql_hash") if isinstance(raw.get("sql_hash"), str) else "") or ""
    source = (raw.get("source") if isinstance(raw.get("source"), str) else "") or ""
    phase = (raw.get("phase") if isinstance(raw.get("phase"), str) else "") or ""

    # ---- 决定 db_type_code ----
    db_type_code = _resolve_db_type_code(db, asset_id)

    # ---- 决定 status ----
    if truncated:
        status = AiSchemaSnapshotStatus.FAILED
        snap_error_code = "RESULT_TRUNCATED"
        snap_error_message = (
            f"collector reported truncated=true (total_rows={total_rows} "
            f"returned_rows={returned_rows}); per plan §4.4 P1 snapshot must be failed"
        )[:4000]
    elif item_status in ("failed", "missing", "drifted") or item_status not in (
        "verified", "collected", "success"
    ):
        status = AiSchemaSnapshotStatus.FAILED
        snap_error_code = error_code or _derive_error_code(item_status)
        snap_error_message = (
            message
            or (raw.get("stderr") if isinstance(raw.get("stderr"), str) else "")
            or "ai_schema collection failed"
        )[:4000]
    elif not rows:
        # status=verified but no rows → 视为 failed (NO_ROWS)
        status = AiSchemaSnapshotStatus.FAILED
        snap_error_code = "NO_ROWS"
        snap_error_message = (
            f"collector returned 0 rows (columns={len(columns)}, total_rows={total_rows})"
        )[:4000]
    else:
        status = AiSchemaSnapshotStatus.SUCCESS
        snap_error_code = None
        snap_error_message = None

    # ---- 解析 allowed_schemas / allowed_tables / allowed_columns ----
    # C16-5+ bug-fix: collector_client 返回 rows 为 list-of-lists 格式（非 dict），
    # 需要用 columns 名映射为 dict 再传给 _aggregate_whitelist。
    dict_rows = _rows_to_dicts(rows, columns)
    allowed_schemas, allowed_tables, allowed_columns = _aggregate_whitelist(dict_rows)

    # ---- C16-F2d commit 2: system view policy force-include ----
    # 若该 instance 启用了 AiSystemViewPolicy，则把 policy.allowlist 追加到
    # snapshot.allowed_tables，让 sqlglot AST 校验层把这些系统视图视为白名单内表。
    # 容错：policy 查询/合并失败不应阻塞 snapshot 主流程（C9 callback 已有的 P1 容错策略）。
    try:
        policy = AiSystemViewPolicyService.get_policy(db, instance_id=asset_id)
        if AiSystemViewPolicyService.is_active(policy):
            merged = AiSystemViewPolicyService.merged_allowlist(
                policy, allowed_tables,
            )
            added = len(merged) - len(allowed_tables)
            if added > 0:
                logger.info(
                    "ai_schema callback policy force-include: run_id=%s item_key=%s "
                    "instance_id=%s policy_version=%s base_size=%d merged_size=%d added=%d",
                    getattr(run, "run_id", "?"),
                    getattr(cb, "item_key", "?"),
                    asset_id,
                    AiSystemViewPolicyService.policy_version(policy),
                    len(allowed_tables),
                    len(merged),
                    added,
                )
            allowed_tables = merged
    except Exception:
        logger.exception(
            "ai_schema callback policy merge failed: run_id=%s instance_id=%s (non-fatal)",
            getattr(run, "run_id", "?"),
            asset_id,
        )

    # ---- 解析 schema_name ----
    schema_name: Optional[str] = None
    if dict_rows:
        first = dict_rows[0].get("table_schema")
        if isinstance(first, str) and first:
            schema_name = first[:200]

    # ---- 解析 database_name（plan line 146：无值时存 '<default>'）----
    database_name = _resolve_database_name(db, asset_id)

    # ---- 计算 snapshot_hash（仅 success 才需要）----
    if status == AiSchemaSnapshotStatus.SUCCESS:
        snapshot_hash = _compute_snapshot_hash(rows, columns)
    else:
        snapshot_hash = None

    total_tables = len(allowed_tables)
    total_columns = len(dict_rows)

    # ---- expires_at（仅 success 时设置）----
    settings = get_settings()
    ttl_hours = int(getattr(settings, "AI_SCHEMA_SNAPSHOT_TTL_HOURS", 24))
    now = _now()
    expires_at = (now + timedelta(hours=ttl_hours)) if status == AiSchemaSnapshotStatus.SUCCESS else None

    # ---- 找已有 snapshot（同 instance + database，幂等 upsert）----
    collector_run_id = int(getattr(run, "id", 0) or 0) or None
    existing = (
        db.query(AiSchemaSnapshot)
        .filter(
            AiSchemaSnapshot.instance_id == asset_id,
            AiSchemaSnapshot.database_name == database_name,
            AiSchemaSnapshot.collector_run_id == collector_run_id,
        )
        .with_for_update()
        .first()
    )

    # 兼容旧逻辑：同一 instance+db 但尚未绑定 collector_run 的 pending/running 行
    if existing is None:
        existing = (
            db.query(AiSchemaSnapshot)
            .filter(
                AiSchemaSnapshot.instance_id == asset_id,
                AiSchemaSnapshot.database_name == database_name,
                AiSchemaSnapshot.status.in_(
                    (AiSchemaSnapshotStatus.PENDING, AiSchemaSnapshotStatus.RUNNING)
                ),
            )
            .order_by(AiSchemaSnapshot.id.desc())
            .with_for_update()
            .first()
        )

    if existing is None:
        snap = AiSchemaSnapshot(
            instance_id=asset_id,
            db_type_code=db_type_code,
            database_name=database_name,
            schema_name=schema_name,
            status=AiSchemaSnapshotStatus.PENDING,
            allowed_schemas=[],
            allowed_tables=[],
            allowed_columns={},
            denied_columns=[],
            is_current=False,
            collector_run_id=collector_run_id,
        )
        db.add(snap)
        db.flush()  # populate snap.id without committing
        existing = snap

    # ---- 更新字段 ----
    existing.db_type_code = db_type_code
    existing.database_name = database_name
    existing.schema_name = schema_name
    existing.status = status
    existing.allowed_schemas = allowed_schemas
    existing.allowed_tables = allowed_tables
    existing.allowed_columns = allowed_columns
    existing.collector_run_id = collector_run_id
    existing.snapshot_hash = snapshot_hash
    existing.total_tables = total_tables if status == AiSchemaSnapshotStatus.SUCCESS else None
    existing.total_columns = total_columns if status == AiSchemaSnapshotStatus.SUCCESS else None
    existing.expires_at = expires_at
    existing.error_code = snap_error_code
    existing.error_message = snap_error_message
    existing.collected_at = now if status == AiSchemaSnapshotStatus.SUCCESS else None

    # ---- 两阶段发布：success 时把同 (instance, db) 的旧 is_current 切 false ----
    if status == AiSchemaSnapshotStatus.SUCCESS:
        existing.is_current = True
        db.execute(
            update(AiSchemaSnapshot)
            .where(
                and_(
                    AiSchemaSnapshot.instance_id == asset_id,
                    AiSchemaSnapshot.database_name == database_name,
                    AiSchemaSnapshot.is_current.is_(True),
                    AiSchemaSnapshot.id != existing.id,
                )
            )
            .values(is_current=False)
        )
    else:
        # 失败/未完成时不允许成为 current；保留旧 current 仍可生效
        existing.is_current = False

    db.flush()
    logger.info(
        "ai_schema snapshot upserted: run_id=%s item_key=%s instance_id=%s db=%s "
        "status=%s is_current=%s total_tables=%s snapshot_hash=%s",
        getattr(run, "run_id", "?"),
        getattr(cb, "item_key", "?"),
        asset_id,
        database_name,
        status,
        existing.is_current,
        existing.total_tables,
        (snapshot_hash or "")[:12],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows_to_dicts(rows: list[Any], columns: list[str]) -> list[dict[str, Any]]:
    """Convert list-of-lists rows to list-of-dicts using column names as keys.

    collector_client returns rows as ``[[val1, val2, ...], ...]``. The callback
    needs dict rows (keyed by column name) for ``_aggregate_whitelist``.
    """
    if not rows or not columns:
        return []
    # If rows are already dicts, pass through
    if isinstance(rows[0], dict):
        return rows
    result: list[dict[str, Any]] = []
    ncols = len(columns)
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        d: dict[str, Any] = {}
        for i, val in enumerate(row):
            if i < ncols:
                d[columns[i].lower()] = val
        result.append(d)
    return result


def _aggregate_whitelist(rows: list[Any]) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Group raw rows into allowed_schemas / allowed_tables / allowed_columns."""
    schemas: set[str] = set()
    tables: set[str] = set()
    columns_map: dict[str, list[str]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        schema = row.get("table_schema")
        table = row.get("table_name")
        col = row.get("column_name")
        if not isinstance(schema, str) or not isinstance(table, str):
            continue
        schemas.add(schema)
        qualified = f"{schema}.{table}"
        tables.add(qualified)
        if isinstance(col, str) and col:
            cols = columns_map.setdefault(qualified, [])
            if col not in cols:
                cols.append(col)

    return sorted(schemas), sorted(tables), columns_map


def _compute_snapshot_hash(rows: list[Any], columns: list[Any]) -> str:
    """SHA-256 over canonical JSON of (columns, rows).

    使用 sort_keys + 紧凑分隔符确保 server 端 / client 端 / 不同时刻计算结果稳定。
    """
    canonical = {
        "columns": list(columns) if isinstance(columns, list) else [],
        "rows": list(rows) if isinstance(rows, list) else [],
    }
    blob = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _resolve_db_type_code(db: Session, instance_id: int) -> str:
    """Map DbInstance → DbType.type_code（uppercase），fallback POSTGRESQL。

    C8-1 Builder 当前只放行 postgresql，因此即便 lookup 失败，
    fallback 到 POSTGRESQL 也是安全的（避免 callback 落库硬失败）。
    """
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
        code_upper = str(code).upper()
        # Normalize dialect variants to CHECK-compatible codes
        if code_upper in ("SQLSERVER", "SQL SERVER"):
            return "MSSQL"
        return code_upper
    except Exception:
        logger.exception("db_type_code lookup failed for instance_id=%s", instance_id)
        return "POSTGRESQL"


def _resolve_database_name(db: Session, instance_id: int) -> str:
    """解析 database_name；当前 C9 阶段无明确 database 输入，统一返回 '<default>'。

    后续 C10+ 可从 extra_attrs / rule_config 读取具体 database。
    """
    try:
        inst = (
            db.query(DbInstance)
            .filter(DbInstance.id == instance_id)
            .first()
        )
        if inst is not None:
            extra = getattr(inst, "extra_attrs", None)
            if isinstance(extra, dict):
                candidate = extra.get("ai_schema_database_name")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()[:200]
    except Exception:
        logger.exception("database_name lookup failed for instance_id=%s", instance_id)
    return "<default>"


def _derive_error_code(item_status: str) -> str:
    if item_status == "skipped":
        return "COLLECTION_SKIPPED"
    if item_status == "missing":
        return "INSTANCE_UNREACHABLE"
    if item_status == "drifted":
        return "ASSET_DRIFTED"
    return "COLLECTION_FAILED"


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _now() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)
