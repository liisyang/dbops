"""Phase 3.6B0 C16-F3 — AiObjectMetadataSnapshotCallbackService.

处理 ``business_domain == "ai_object_metadata"`` 的 callback items，把
``DB_OBJECT_METADATA`` 的采集结果（object DDL 行）幂等 upsert 到
``dbops.ai_object_metadata_snapshot`` 表。

设计要点（避免 C2 BE-bug1 复发 + 与 C9 schema callback 对齐）：
- 不使用 alias / metadata 字段（字段名 == JSON key 即可）
- 单条 item 异常 → 日志 + continue，绝不破坏主 callback 事务
- ``collector_run_id`` 维度去重（同一 run 多次回调覆盖，不重复落库）
- ``status == success`` 时触发两阶段发布（is_current=true / 旧切 false），DB
  层部分唯一索引 ``uq_ai_object_metadata_snapshot_current`` 兜底
- ``truncated=true`` 是硬错误（plan §4.4 P1）→ status=failed +
  error_code=RESULT_TRUNCATED
- object_ddl_sha256 = SHA-256 (64 hex) over utf-8 bytes of object_ddl_text
  —— ``chk_ai_object_metadata_snapshot_hash_len`` 兜底长度
- snapshot_hash = SHA-256 (64 hex) over canonical JSON of (columns, rows)
  —— ``chk_ai_object_metadata_snapshot_snapshot_hash_len`` 兜底长度
- 1MB 截断（plan §4.4 + §6）：object_ddl_text 超过 max_bytes 按 utf-8 字节
  数截断 + error_message='TRUNCATED' 标记
- 无 rows 但 status=success → failed (NO_OBJECTS)
- 5 类对象计数：按 object_type 字段聚合（table / view / materialized_view /
  index / function / procedure / primary_key / unique_constraint /
  foreign_key / check_constraint）
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
from app.models.ai import AiObjectMetadataSnapshot, AiObjectMetadataSnapshotStatus
from app.models.dbops_assets import DbInstance, DbType

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
    """Persist ``business_domain='ai_object_metadata'`` callback items.

    返回成功写入的 snapshot 行数（含更新 + 新建）。Caller 应在
    try/except 内调用本函数，单条 item 失败不会影响主事务。
    """
    written = 0
    for cb in callback_items:
        business_domain = getattr(cb, "business_domain", None) or ""
        check_code = getattr(cb, "check_code", None) or ""
        if business_domain != "ai_object_metadata":
            continue
        # Defensive: only DB_OBJECT_METADATA check_code drives ai_object_metadata.
        if check_code != "DB_OBJECT_METADATA":
            logger.debug(
                "ai_object_metadata callback skipped: check_code=%s not DB_OBJECT_METADATA",
                check_code,
            )
            continue
        try:
            _save_one(db, run=run, cb=cb)
            written += 1
        except Exception:
            # 严格对齐 C9 ai_schema 容错策略：单条 item 失败仅记录日志，
            # 不影响主 callback 事务。
            logger.exception(
                "ai_object_metadata snapshot save failed: run_id=%s item_key=%s",
                getattr(run, "run_id", "?"),
                getattr(cb, "item_key", "?"),
            )
            continue
    return written


# ---------------------------------------------------------------------------
# Per-item save
# ---------------------------------------------------------------------------

def _save_one(db: Session, *, run: Any, cb: Any) -> None:
    """Upsert a single ai_object_metadata snapshot."""
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
    # Normalize rows from list[list] (collector_client DbReadonlySqlOutput schema)
    # to list[dict] expected by _aggregate_ddl / _compute_snapshot_hash
    rows = _normalize_rows(rows, columns)
    sql_hash = (raw.get("sql_hash") if isinstance(raw.get("sql_hash"), str) else "") or ""
    source = (raw.get("source") if isinstance(raw.get("source"), str) else "") or ""
    phase = (raw.get("phase") if isinstance(raw.get("phase"), str) else "") or ""
    max_bytes = _to_int(raw.get("max_bytes")) or 1048576  # F3 default 1MB

    # ---- 决定 db_type_code ----
    db_type_code = _resolve_db_type_code(db, asset_id)

    # ---- 决定 status ----
    if truncated:
        status = AiObjectMetadataSnapshotStatus.FAILED
        snap_error_code = "RESULT_TRUNCATED"
        snap_error_message = (
            f"collector reported truncated=true (total_rows={total_rows} "
            f"returned_rows={returned_rows}); per plan §4.4 P1 snapshot must be failed"
        )[:4000]
    elif item_status in ("failed", "missing", "drifted") or item_status not in (
        "verified", "collected", "success"
    ):
        status = AiObjectMetadataSnapshotStatus.FAILED
        snap_error_code = error_code or _derive_error_code(item_status)
        snap_error_message = (
            message
            or (raw.get("stderr") if isinstance(raw.get("stderr"), str) else "")
            or "ai_object_metadata collection failed"
        )[:4000]
    elif not rows:
        # status=verified but no rows → 视为 failed (NO_OBJECTS)
        status = AiObjectMetadataSnapshotStatus.FAILED
        snap_error_code = "NO_OBJECTS"
        snap_error_message = (
            f"collector returned 0 rows (columns={len(columns)}, total_rows={total_rows})"
        )[:4000]
    else:
        status = AiObjectMetadataSnapshotStatus.SUCCESS
        snap_error_code = None
        snap_error_message = None

    # ---- 解析 database_name / schema_name（plan line 146 + F3 line 145）----
    database_name = _resolve_database_name(db, asset_id)
    schema_name = _resolve_schema_name_from_rows(rows) or _resolve_schema_name(db, asset_id)

    # ---- 聚合 DDL + 统计 ----
    if status == AiObjectMetadataSnapshotStatus.SUCCESS:
        ddl_text, counts = _aggregate_ddl(rows, max_bytes=max_bytes)
        object_ddl_sha256 = hashlib.sha256(ddl_text.encode("utf-8")).hexdigest()
        snapshot_hash = _compute_snapshot_hash(rows, columns)
        table_count = counts.get("table", 0)
        view_count = counts.get("view", 0) + counts.get("materialized_view", 0)
        index_count = counts.get("index", 0)
        function_count = counts.get("function", 0) + counts.get("procedure", 0)
        total_object_count = sum(counts.values())
        # 1MB 截断：标记 TRUNCATED 但不失败（截断本身不破坏 DDL 内容）
        if len(ddl_text.encode("utf-8")) >= max_bytes:
            snap_error_code = "TRUNCATED"
            snap_error_message = (
                f"object_ddl_text truncated to {max_bytes} bytes (1MB cap, plan §4.4)"
            )[:4000]
    else:
        ddl_text = None
        object_ddl_sha256 = None
        snapshot_hash = None
        table_count = 0
        view_count = 0
        index_count = 0
        function_count = 0
        total_object_count = 0

    # ---- expires_at（仅 success 时设置）----
    settings = get_settings()
    ttl_hours = int(getattr(settings, "AI_OBJECT_METADATA_TTL_HOURS", 24))
    now = _now()
    expires_at = (
        (now + timedelta(hours=ttl_hours)) if status == AiObjectMetadataSnapshotStatus.SUCCESS else None
    )

    # ---- 找已有 snapshot（instance + database + schema + collector_run_id 维度，幂等 upsert）----
    collector_run_id = int(getattr(run, "id", 0) or 0) or None
    existing = (
        db.query(AiObjectMetadataSnapshot)
        .filter(
            AiObjectMetadataSnapshot.instance_id == asset_id,
            AiObjectMetadataSnapshot.database_name == database_name,
            AiObjectMetadataSnapshot.schema_name == schema_name,
            AiObjectMetadataSnapshot.collector_run_id == collector_run_id,
        )
        .with_for_update()
        .first()
    )

    # 兼容旧逻辑：同一 instance+db+schema 但尚未绑定 collector_run 的 pending/running 行
    if existing is None:
        existing = (
            db.query(AiObjectMetadataSnapshot)
            .filter(
                AiObjectMetadataSnapshot.instance_id == asset_id,
                AiObjectMetadataSnapshot.database_name == database_name,
                AiObjectMetadataSnapshot.schema_name == schema_name,
                AiObjectMetadataSnapshot.status.in_(
                    (
                        AiObjectMetadataSnapshotStatus.PENDING,
                        AiObjectMetadataSnapshotStatus.RUNNING,
                    )
                ),
            )
            .order_by(AiObjectMetadataSnapshot.id.desc())
            .with_for_update()
            .first()
        )

    if existing is None:
        snap = AiObjectMetadataSnapshot(
            instance_id=asset_id,
            db_type_code=db_type_code,
            database_name=database_name,
            schema_name=schema_name,
            status=AiObjectMetadataSnapshotStatus.PENDING,
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
    existing.object_ddl_text = ddl_text
    existing.object_ddl_sha256 = object_ddl_sha256
    existing.snapshot_hash = snapshot_hash
    existing.table_count = table_count
    existing.view_count = view_count
    existing.index_count = index_count
    existing.function_count = function_count
    existing.total_object_count = total_object_count
    existing.collector_run_id = collector_run_id
    existing.expires_at = expires_at
    existing.error_code = snap_error_code
    existing.error_message = snap_error_message
    existing.collected_at = now if status == AiObjectMetadataSnapshotStatus.SUCCESS else None

    # ---- 两阶段发布：success 时把同 (instance, db, schema) 的旧 is_current 切 false ----
    if status == AiObjectMetadataSnapshotStatus.SUCCESS:
        existing.is_current = True
        db.execute(
            update(AiObjectMetadataSnapshot)
            .where(
                and_(
                    AiObjectMetadataSnapshot.instance_id == asset_id,
                    AiObjectMetadataSnapshot.database_name == database_name,
                    AiObjectMetadataSnapshot.schema_name == schema_name,
                    AiObjectMetadataSnapshot.is_current.is_(True),
                    AiObjectMetadataSnapshot.id != existing.id,
                )
            )
            .values(is_current=False)
        )
    else:
        # 失败/未完成时不允许成为 current；保留旧 current 仍可生效
        existing.is_current = False

    db.flush()
    logger.info(
        "ai_object_metadata snapshot upserted: run_id=%s item_key=%s instance_id=%s "
        "db=%s schema=%s status=%s is_current=%s total=%s object_ddl_sha256=%s",
        getattr(run, "run_id", "?"),
        getattr(cb, "item_key", "?"),
        asset_id,
        database_name,
        schema_name,
        status,
        existing.is_current,
        total_object_count,
        (object_ddl_sha256 or "")[:12],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 7 类 DDL 段拼接顺序（与 SQL 模板 5 段 UNION ALL 对齐 + 约束 4 段合并到末尾）
_DDL_SECTION_ORDER: tuple[str, ...] = (
    "table",
    "view",
    "materialized_view",
    "index",
    "function",
    "procedure",
    "constraint",
)

# constraint 5 子类合并为单一 'constraint' 段（CHECK 约束按 4 子类分别计数）
_CONSTRAINT_SUBTYPES: frozenset[str] = frozenset(
    {"primary_key", "unique_constraint", "foreign_key", "check_constraint"}
)


def _normalize_rows(rows: list[Any], columns: list[str]) -> list[dict[str, Any]]:
    """Convert list[list] rows (collector_client DbReadonlySqlOutput format)
    to list[dict] expected by _aggregate_ddl and _compute_snapshot_hash.

    If rows are already list[dict], return as-is.
    """
    if not rows:
        return []
    # Already dict-format — pass through
    if isinstance(rows[0], dict):
        return [r for r in rows if isinstance(r, dict)]
    # list-format — zip with column headers
    if not columns:
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            result.append(dict(zip(columns, row)))
        elif isinstance(row, dict):
            result.append(row)
    return result


def _aggregate_ddl(rows: list[Any], *, max_bytes: int) -> tuple[str, dict[str, int]]:
    """按 object_type 分段拼接 DDL，返回 (ddl_text, counts_by_type).

    拼接格式:
      -- table --
      CREATE TABLE ...;
      CREATE TABLE ...;
      -- view --
      CREATE VIEW ...;
      ...

    1MB 截断：按 utf-8 字节数切，超过 max_bytes 立即停止拼接（最后一段可能被截断）。
    """
    grouped: dict[str, list[str]] = {k: [] for k in _DDL_SECTION_ORDER}
    for row in rows:
        if not isinstance(row, dict):
            continue
        obj_type = row.get("object_type")
        ddl = row.get("ddl_text")
        if not isinstance(obj_type, str) or not obj_type:
            continue
        if not isinstance(ddl, str) or not ddl:
            continue
        # constraint 5 子类统一归并到 'constraint' 段
        if obj_type in _CONSTRAINT_SUBTYPES:
            grouped["constraint"].append(ddl)
        elif obj_type in grouped:
            grouped[obj_type].append(ddl)
        else:
            # 防御：未知 object_type → 单独段（避免 silently drop）
            grouped.setdefault(obj_type, []).append(ddl)

    counts: dict[str, int] = {}
    for obj_type, ddl_list in grouped.items():
        if ddl_list:
            counts[obj_type] = len(ddl_list)

    parts: list[str] = []
    # 严格按 _DDL_SECTION_ORDER 拼接
    for obj_type in _DDL_SECTION_ORDER:
        ddl_list = grouped.get(obj_type) or []
        if not ddl_list:
            continue
        parts.append(f"-- {obj_type} --")
        parts.extend(ddl_list)
    # 未知 object_type 段（防御性，正常不应出现）
    for obj_type, ddl_list in grouped.items():
        if obj_type in _DDL_SECTION_ORDER:
            continue
        if not ddl_list:
            continue
        parts.append(f"-- {obj_type} --")
        parts.extend(ddl_list)

    text = "\n".join(parts)
    # 1MB 截断（按 utf-8 字节数）
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return text, counts


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

    F3 builder 当前只放行 postgresql，因此即便 lookup 失败，fallback 到
    POSTGRESQL 也是安全的（避免 callback 落库硬失败）。
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
        # (db_type table uses 'SQLSERVER' but DDL CHECK expects 'MSSQL')
        if code_upper in ("SQLSERVER", "SQL SERVER"):
            return "MSSQL"
        return code_upper
    except Exception:
        logger.exception("db_type_code lookup failed for instance_id=%s", instance_id)
        return "POSTGRESQL"


def _resolve_database_name(db: Session, instance_id: int) -> str:
    """解析 database_name；F3 阶段无明确 database 输入，统一返回 '<default>'。

    后续可从 extra_attrs / rule_config 读取具体 database。
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
                candidate = extra.get("ai_object_metadata_database_name")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()[:200]
    except Exception:
        logger.exception("database_name lookup failed for instance_id=%s", instance_id)
    return "<default>"


def _resolve_schema_name_from_rows(rows: list[Any]) -> Optional[str]:
    """从 rows 第一条取 schema_name（plan §4 line 145 思路）。"""
    if not rows:
        return None
    first = rows[0]
    if not isinstance(first, dict):
        return None
    candidate = first.get("schema_name")
    if isinstance(candidate, str) and candidate:
        return candidate[:200]
    return None


def _resolve_schema_name(db: Session, instance_id: int) -> str:
    """Resolve schema_name; F3 阶段无明确 schema 输入时 fallback '<default>'."""
    try:
        inst = (
            db.query(DbInstance)
            .filter(DbInstance.id == instance_id)
            .first()
        )
        if inst is not None:
            extra = getattr(inst, "extra_attrs", None)
            if isinstance(extra, dict):
                candidate = extra.get("ai_object_metadata_schema_name")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()[:200]
    except Exception:
        logger.exception("schema_name lookup failed for instance_id=%s", instance_id)
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
