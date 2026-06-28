"""Phase 3.6B0 C10 — AiSchemaContextService.

实时生成给 LLM 看的 ``schema_context`` 文本 + 安全策略 hash (plan §4.6)。

设计要点:
- DB **不保存** schema_context 展示文本 (plan §2.2 line 115) — 仅保存结构化
  JSON (allowed_schemas/tables/columns + denied_columns)。``schema_context``
  文本在每次调用 Dify 前**实时构建**，并纳入 ``schema_policy_hash`` 计算 —
  安全策略只有一个事实源。
- ``schema_policy_hash`` 基于**规范化策略内容**计算 (plan §4.5 P0-3)：
  canonical JSON of {snapshot_hash, allowed_schemas, allowed_tables,
  allowed_columns, denied_columns, policy_version}。**不**仅 hash 展示文本。
- 字符上限由 ``AI_SCHEMA_CONTEXT_MAX_CHARS`` 控制 (默认 30000)，超出截断 +
  追加截断标记。
- TTL 由 ``AI_SCHEMA_SNAPSHOT_TTL_HOURS`` 控制；过期返回 available=false。

调用方:
- ``api/ai.py`` GET /ai/sql/schema-snapshots/{instance_id}/context
- 后续 C13 AiSqlService.preview / Dify 调用方 — Dify inputs 中
  ``schema_context`` 字段直接用本服务的输出
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import get_settings
from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.services.ai.ai_schema_snapshot_service import AiSchemaSnapshotService

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常
# =============================================================================
class AiSchemaContextError(Exception):
    """Schema Context 服务基类异常。"""


class ContextUnavailableReason:
    """available=false 时的原因码常量。"""

    NO_SNAPSHOT = "no_snapshot"               # 该 instance 尚未采集
    SNAPSHOT_NOT_SUCCESS = "snapshot_not_success"  # 当前 snapshot 是 pending/running/failed
    SNAPSHOT_EXPIRED = "snapshot_expired"     # success 但 expires_at 已过
    SNAPSHOT_NOT_CURRENT = "snapshot_not_current"  # 旧 success 但不是 is_current


# =============================================================================
# AiSchemaContextService
# =============================================================================
class AiSchemaContextService:
    """实时构建 Dify inputs 中的 schema_context 文本 + 安全策略 hash。"""

    # Dify SQL workflow 中用到的 policy 版本号；写入 schema_policy_hash 影响
    # 所有依赖此 hash 的下游（plan §4.5 Execute 阶段 8 步校验）。
    POLICY_VERSION = "2026-06-28-v1"

    # SQL 方言映射（plan §4.8 — 首版仅 PostgreSQL，框架保留）
    _DIALECT_MAP = {
        "POSTGRESQL": "postgres",
        "MYSQL": "mysql",
        "ORACLE": "oracle",
        "MSSQL": "tsql",
    }

    # ------------------------------------------------------------------
    # build_schema_context
    # ------------------------------------------------------------------
    @classmethod
    def build_schema_context(
        cls,
        db,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """从最新 is_current snapshot 实时构建 Dify inputs。

        Returns:
            dict 字段与 ``AiSchemaContextResponse`` 一致：
            - available=True:  全部字段填充
            - available=False: 仅 instance_id + db_type_code + reason 有意义

        关键不变量:
        - ``schema_policy_hash`` 仅基于策略 JSON 计算，与展示文本格式无关
        - 字符截断标记 "…(truncated)" 不进入 hash
        - available=False 时 **不要** 返回 schema_policy_hash（前端无意义）
        """
        snapshot = AiSchemaSnapshotService.get_snapshot_status(
            db,
            instance_id=instance_id,
            database_name=database_name,
        )

        # 无任何 snapshot
        if snapshot is None:
            # 退化：返回 latest any status 给前端展示进度
            latest = AiSchemaSnapshotService.get_latest_any_status(
                db,
                instance_id=instance_id,
                database_name=database_name,
            )
            db_type_code = cls._infer_db_type_code(db, instance_id)
            return cls._build_unavailable(
                instance_id=instance_id,
                db_type_code=db_type_code,
                reason=ContextUnavailableReason.NO_SNAPSHOT,
                snapshot=latest,
            )

        # status 校验
        if snapshot.status != AiSchemaSnapshotStatus.SUCCESS:
            return cls._build_unavailable(
                instance_id=instance_id,
                db_type_code=snapshot.db_type_code,
                reason=ContextUnavailableReason.SNAPSHOT_NOT_SUCCESS,
                snapshot=snapshot,
            )

        # is_current 校验（理论上 get_snapshot_status 已经过滤；此处冗余防越界）
        if not snapshot.is_current:
            return cls._build_unavailable(
                instance_id=instance_id,
                db_type_code=snapshot.db_type_code,
                reason=ContextUnavailableReason.SNAPSHOT_NOT_CURRENT,
                snapshot=snapshot,
            )

        # TTL 校验
        if snapshot.expires_at is not None:
            now = cls._utcnow()
            expires_at_utc = cls._to_utc(snapshot.expires_at)
            if expires_at_utc <= now:
                return cls._build_unavailable(
                    instance_id=instance_id,
                    db_type_code=snapshot.db_type_code,
                    reason=ContextUnavailableReason.SNAPSHOT_EXPIRED,
                    snapshot=snapshot,
                )

        # ---- 全部通过 → 计算 schema_policy_hash + schema_context ----
        settings = get_settings()

        allowed_schemas = list(snapshot.allowed_schemas or [])
        allowed_tables = list(snapshot.allowed_tables or [])
        allowed_columns = cls._normalize_allowed_columns(snapshot.allowed_columns)
        denied_columns = list(snapshot.denied_columns or [])

        policy_hash = cls._compute_schema_policy_hash(
            snapshot_hash=snapshot.snapshot_hash or "",
            allowed_schemas=allowed_schemas,
            allowed_tables=allowed_tables,
            allowed_columns=allowed_columns,
            denied_columns=denied_columns,
            policy_version=cls.POLICY_VERSION,
        )

        # 受 AI_SCHEMA_MAX_TABLES / AI_SCHEMA_MAX_COLUMNS_PER_TABLE 限制
        allowed_tables_limited = allowed_tables[: settings.AI_SCHEMA_MAX_TABLES]
        allowed_columns_limited: dict[str, list[str]] = {}
        for qualified in allowed_tables_limited:
            cols = allowed_columns.get(qualified, [])
            allowed_columns_limited[qualified] = cols[: settings.AI_SCHEMA_MAX_COLUMNS_PER_TABLE]

        schema_context = cls._render_schema_context(
            db_type_code=snapshot.db_type_code,
            database_name=snapshot.database_name,
            allowed_schemas=allowed_schemas,
            allowed_tables=allowed_tables_limited,
            allowed_columns=allowed_columns_limited,
            denied_columns=denied_columns,
            max_chars=settings.AI_SCHEMA_CONTEXT_MAX_CHARS,
        )

        return {
            "available": True,
            "instance_id": instance_id,
            "db_type_code": snapshot.db_type_code,
            "sql_dialect": cls._dialect_for(snapshot.db_type_code),
            "schema_context": schema_context,
            "allowed_schemas": allowed_schemas,
            "allowed_tables": allowed_tables_limited,
            "allowed_columns": allowed_columns_limited,
            "denied_columns": denied_columns,
            "schema_snapshot_id": int(snapshot.id),
            "schema_policy_hash": policy_hash,
            "snapshot_hash": snapshot.snapshot_hash,
            "collected_at": snapshot.collected_at,
            "expires_at": snapshot.expires_at,
            "total_tables": snapshot.total_tables,
            "total_columns": snapshot.total_columns,
            "reason": None,
        }

    # ------------------------------------------------------------------
    # schema_policy_hash
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_schema_policy_hash(
        *,
        snapshot_hash: str,
        allowed_schemas: list[str],
        allowed_tables: list[str],
        allowed_columns: dict[str, list[str]],
        denied_columns: list[str],
        policy_version: str,
    ) -> str:
        """SHA-256 over canonical JSON of policy content.

        严格对齐 plan §4.5：hash 基于**规范化策略内容**而非展示文本 —
        文本格式变化（换行/空格）不应让 Execute 阶段误判策略变更。
        """
        canonical = {
            "snapshot_hash": snapshot_hash or "",
            "allowed_schemas": sorted(allowed_schemas or []),
            "allowed_tables": sorted(allowed_tables or []),
            "allowed_columns": {
                k: sorted(v or []) for k, v in sorted((allowed_columns or {}).items())
            },
            "denied_columns": sorted(denied_columns or []),
            "policy_version": policy_version,
        }
        blob = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # schema_context 文本渲染
    # ------------------------------------------------------------------
    @staticmethod
    def _render_schema_context(
        *,
        db_type_code: str,
        database_name: str,
        allowed_schemas: list[str],
        allowed_tables: list[str],
        allowed_columns: dict[str, list[str]],
        denied_columns: list[str],
        max_chars: int,
    ) -> str:
        """生成给 LLM 看的 schema 摘要文本。

        格式（稳定）：
          DB: <db_type_code> (database=<database_name>)
          Allowed schemas: [a, b, c]
          Allowed tables (N):
            - schema.table(col1, col2, ...)
            - ...
          Denied columns (sensitive): [password_hash, ...]

        不超 max_chars 时末尾追加 "…(truncated)" 标记 (但不参与 hash)。
        """
        lines: list[str] = []
        lines.append(f"DB: {db_type_code} (database={database_name})")
        lines.append(f"Allowed schemas: {sorted(allowed_schemas)}")
        if allowed_tables:
            lines.append(f"Allowed tables ({len(allowed_tables)}):")
            for qualified in allowed_tables:
                cols = allowed_columns.get(qualified, [])
                if cols:
                    lines.append(f"  - {qualified}({', '.join(cols)})")
                else:
                    lines.append(f"  - {qualified}()")
        else:
            lines.append("Allowed tables (0):")
        if denied_columns:
            lines.append(f"Denied columns (sensitive): {sorted(denied_columns)}")

        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        # 截断保留前 max_chars - len(suffix) 个字符，避免污染内容
        suffix = "\n…(truncated)"
        keep = max(max_chars - len(suffix), 0)
        return text[:keep] + suffix

    # ------------------------------------------------------------------
    # unavailable 响应
    # ------------------------------------------------------------------
    @staticmethod
    def _build_unavailable(
        *,
        instance_id: int,
        db_type_code: Optional[str],
        reason: str,
        snapshot: Optional[AiSchemaSnapshot],
    ) -> dict[str, Any]:
        return {
            "available": False,
            "instance_id": instance_id,
            "db_type_code": db_type_code,
            "sql_dialect": None,
            "schema_context": None,
            "allowed_schemas": None,
            "allowed_tables": None,
            "allowed_columns": None,
            "denied_columns": None,
            "schema_snapshot_id": int(snapshot.id) if snapshot is not None else None,
            "schema_policy_hash": None,
            "snapshot_hash": getattr(snapshot, "snapshot_hash", None) if snapshot is not None else None,
            "collected_at": getattr(snapshot, "collected_at", None) if snapshot is not None else None,
            "expires_at": getattr(snapshot, "expires_at", None) if snapshot is not None else None,
            "total_tables": getattr(snapshot, "total_tables", None) if snapshot is not None else None,
            "total_columns": getattr(snapshot, "total_columns", None) if snapshot is not None else None,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_allowed_columns(raw: Any) -> dict[str, list[str]]:
        """SQLAlchemy JSONB 字段返回 dict；确保 value 为 list[str] 便于排序。"""
        if not isinstance(raw, dict):
            return {}
        result: dict[str, list[str]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                result[str(k)] = [str(x) for x in v]
            elif v is None:
                result[str(k)] = []
        return result

    @classmethod
    def _dialect_for(cls, db_type_code: str) -> Optional[str]:
        return cls._DIALECT_MAP.get((db_type_code or "").upper())

    @staticmethod
    def _infer_db_type_code(db, instance_id: int) -> Optional[str]:
        try:
            from app.models.dbops_assets import DbInstance, DbType

            inst = db.query(DbInstance).filter(DbInstance.id == int(instance_id)).first()
            if inst is None:
                return None
            db_type_id = getattr(inst, "db_type_id", None)
            if db_type_id is None:
                return None
            db_type = db.query(DbType).filter(DbType.id == db_type_id).first()
            if db_type is None:
                return None
            return str(getattr(db_type, "type_code", "") or "").upper() or None
        except Exception:
            logger.exception("db_type_code inference failed for instance_id=%s", instance_id)
            return None

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)