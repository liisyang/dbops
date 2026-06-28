"""Phase 3.6B0 C10 — AiSchemaSnapshotService.

API 触发面 (plan §4.1 + §4.3):

- ``trigger_collection(db, *, instance_id, database_name, requested_by, request_base_url)``
  → 复用 ``CollectorService.launch_collector_run`` (run_type="ai_schema") 调起
  AWX，callback 通过 ``business_domain='ai_schema'`` 路由到
  ``AiSchemaSnapshotCallbackService.save_snapshots`` (C9) 落库。

- ``get_snapshot_status(db, *, instance_id, database_name)``
  → 返回该 instance 当前 is_current=true 的 snapshot (C10 GET status)。

- ``list_history(db, *, instance_id, database_name, limit)``
  → 按 created_at DESC 返回历史 snapshots (C10 GET history)。

- ``cleanup_running_timeouts(db)``
  → 启动时清理超过 ``AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS`` 的 running 行
  → 与 C3 chat stale cleanup 同款策略 (plan §7 P0-5 / §18 lease 机制)。

风格:
- 全部为 staticmethod / classmethod，签名 ``Service.method(db, *, kw=...)``
- 不重新发明轮子：复用 C8 builder 调 AWX、C9 callback 落库
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.models.dbops_assets import DbInstance

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常
# =============================================================================
class AiSchemaSnapshotError(Exception):
    """Schema Snapshot 服务基类异常。"""


class InstanceNotFoundError(AiSchemaSnapshotError):
    """instance_id 不存在 → 404。"""


class FeatureDisabledError(AiSchemaSnapshotError):
    """AI_SQL_PREVIEW_ENABLED=false → 503 (plan §11 P1 解耦)。"""


class UnsupportedDbTypeError(AiSchemaSnapshotError):
    """db_type 当前不在 capabilities 支持列表 → 422。"""


class AwxLaunchError(AiSchemaSnapshotError):
    """AWX launch 失败 → 502。"""


# =============================================================================
# AiSchemaSnapshotService
# =============================================================================
class AiSchemaSnapshotService:
    """Schema Snapshot 触发 + 状态查询。"""

    DEFAULT_DATABASE_PLACEHOLDER = "<default>"

    # ------------------------------------------------------------------
    # 触发采集
    # ------------------------------------------------------------------
    @staticmethod
    def trigger_collection(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str],
        requested_by: Optional[str],
        request_base_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """触发 schema metadata 采集。

        复用 ``CollectorService.launch_collector_run`` 路径，强制
        ``check_codes=["DB_SCHEMA_METADATA_COLLECTION"]`` + ``run_type="ai_schema"``，
        让 C8 Builder 产出 ``business_domain='ai_schema'`` items，最终
        callback 路由到 C9 ``AiSchemaSnapshotCallbackService``。

        Raises:
            InstanceNotFoundError: instance_id 不存在 → 404
            FeatureDisabledError: AI_SQL_PREVIEW_ENABLED=false → 503
            UnsupportedDbTypeError: 当前 capabilities 不支持该 db_type → 422
            AwxLaunchError: AWX launch 失败 → 502
        """
        settings = get_settings()

        # 功能开关（plan §11 P1 — 按功能解耦）
        if not settings.AI_SQL_PREVIEW_ENABLED:
            raise FeatureDisabledError("AI_SQL_PREVIEW_ENABLED=false")

        # instance 必须存在 + db_type 必须支持
        instance, db_type_code = AiSchemaSnapshotService._resolve_instance(db, instance_id)

        if db_type_code.upper() not in settings.sql_supported_db_types:
            raise UnsupportedDbTypeError(
                f"db_type '{db_type_code}' not in capabilities "
                f"({settings.sql_supported_db_types}); see GET /api/v1/ai/capabilities"
            )

        # 准备 CollectorRunCreateRequest（直接构造，绕过 Pydantic 校验以避免
        # 默认值的过度约束）
        from app.schemas.collector import CollectorRunCreateRequest

        # database_name 透传：request 阶段先尝试以 option 注入，C9 callback
        # 阶段 fallback 到 extra_attrs.ai_schema_database_name / '<default>'。
        options: dict[str, Any] = {
            "ai_schema_database_name": (database_name or "").strip()
            or AiSchemaSnapshotService.DEFAULT_DATABASE_PLACEHOLDER,
        }
        payload = CollectorRunCreateRequest(
            run_type="ai_schema",
            target_scope="db_instance",
            asset_ids=[instance_id],
            check_codes=["DB_SCHEMA_METADATA_COLLECTION"],
            options=options,
        )

        # 复用 CollectorService 调 AWX
        from app.services.collector_service import CollectorService

        try:
            result = CollectorService.launch_collector_run(
                db,
                payload=payload,
                requested_by=requested_by or "",
                request_base_url=request_base_url or "",
            )
        except LookupError as exc:
            raise InstanceNotFoundError(str(exc)) from exc
        except ValueError as exc:
            # Builder 派生为 skipped (UNSUPPORTED_DB_TYPE / CREDENTIAL_MISSING) 时
            # CollectorService 会把 run.status=failed 后抛 ValueError；此处
            # 转成 UnsupportedDbTypeError 让前端明确知道原因
            msg = str(exc)
            if "未生成任何可执行校验项" in msg:
                raise UnsupportedDbTypeError(
                    f"no collectible items generated for instance {instance_id} "
                    f"(likely unsupported db_type or missing credential)"
                ) from exc
            raise AiSchemaSnapshotError(msg) from exc
        except RuntimeError as exc:
            raise AwxLaunchError(f"AWX launch failed: {exc}") from exc

        logger.info(
            "ai_schema snapshot collection triggered: instance_id=%s db=%s collector_run_id=%s run_id=%s",
            instance_id,
            options["ai_schema_database_name"],
            result.get("collector_run_id"),
            result.get("run_id"),
        )

        return {
            "detail": "launched",
            "collector_run_id": int(result.get("collector_run_id") or 0),
            "run_id": str(result.get("run_id") or ""),
            "awx_job_id": result.get("awx_job_id"),
            "awx_job_url": result.get("awx_job_url"),
            "status": str(result.get("status") or "launched"),
            "item_count": int(result.get("item_count") or 0),
        }

    # ------------------------------------------------------------------
    # 状态查询 (GET status)
    # ------------------------------------------------------------------
    @staticmethod
    def get_snapshot_status(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
    ) -> Optional[AiSchemaSnapshot]:
        """返回该 instance 当前 is_current=true 的 snapshot；不存在则 None。

        database_name 默认取 ``<default>``（保持与 C9 callback 默认一致）。
        调用方需根据返回是否为 None 决定 404 vs 200 with available=false。
        """
        db_name = AiSchemaSnapshotService._normalize_database_name(database_name)
        return (
            db.query(AiSchemaSnapshot)
            .filter(
                AiSchemaSnapshot.instance_id == instance_id,
                AiSchemaSnapshot.database_name == db_name,
                AiSchemaSnapshot.is_current.is_(True),
            )
            .order_by(AiSchemaSnapshot.id.desc())
            .first()
        )

    @staticmethod
    def get_latest_any_status(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
    ) -> Optional[AiSchemaSnapshot]:
        """返回该 instance 最新任意状态的 snapshot（包含 pending/running/failed）。

        若 is_current 存在则优先 is_current，否则取最新一行 — 用于 GET status
        在未完成采集时也能返回 200 + 进度信息。
        """
        db_name = AiSchemaSnapshotService._normalize_database_name(database_name)
        current = (
            db.query(AiSchemaSnapshot)
            .filter(
                AiSchemaSnapshot.instance_id == instance_id,
                AiSchemaSnapshot.database_name == db_name,
                AiSchemaSnapshot.is_current.is_(True),
            )
            .first()
        )
        if current is not None:
            return current
        return (
            db.query(AiSchemaSnapshot)
            .filter(
                AiSchemaSnapshot.instance_id == instance_id,
                AiSchemaSnapshot.database_name == db_name,
            )
            .order_by(AiSchemaSnapshot.id.desc())
            .first()
        )

    # ------------------------------------------------------------------
    # 历史 (GET history)
    # ------------------------------------------------------------------
    @staticmethod
    def list_history(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[AiSchemaSnapshot], int]:
        """返回历史 snapshot 列表（created_at DESC, id DESC）。

        包含失败 / 过期版本；前端可选择只显示 success。
        """
        settings = get_settings()
        cap = min(max(limit, 1), settings.AI_SCHEMA_MAX_TABLES or 200)

        db_name = AiSchemaSnapshotService._normalize_database_name(database_name)
        base = db.query(AiSchemaSnapshot).filter(
            AiSchemaSnapshot.instance_id == instance_id,
            AiSchemaSnapshot.database_name == db_name,
        )
        total = base.count()
        items = base.order_by(
            AiSchemaSnapshot.created_at.desc(),
            AiSchemaSnapshot.id.desc(),
        ).limit(cap).all()
        return items, total

    # ------------------------------------------------------------------
    # Stale cleanup（启动时调用，与 chat cleanup 同款策略 — plan §18 C32）
    # ------------------------------------------------------------------
    @classmethod
    def cleanup_running_timeouts(cls, db: Session) -> int:
        """把超过 ``AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS`` 的 running 行标 failed。

        启动时调用一次（main.py lifespan），防止 collector 中途异常退出后
        running 永久卡住。

        Returns:
            更新的行数
        """
        settings = get_settings()
        timeout_seconds = int(getattr(settings, "AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS", 300))
        cutoff = cls._utcnow() - timedelta(seconds=timeout_seconds)

        result = db.execute(
            update(AiSchemaSnapshot)
            .where(
                and_(
                    AiSchemaSnapshot.status == AiSchemaSnapshotStatus.RUNNING,
                    AiSchemaSnapshot.created_at <= cutoff,
                )
            )
            .values(
                status=AiSchemaSnapshotStatus.FAILED,
                error_code="COLLECTION_TIMEOUT",
                error_message=(
                    f"running for more than {timeout_seconds}s without callback; "
                    "marked failed by startup cleanup"
                )[:4000],
            )
        )
        affected = result.rowcount or 0
        db.commit()
        if affected > 0:
            logger.warning(
                "AiSchemaSnapshotService.cleanup_running_timeouts: marked %s snapshots failed (timeout)",
                affected,
            )
        return affected

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_instance(db: Session, instance_id: int) -> tuple[DbInstance, str]:
        """返回 (instance, db_type_code)；instance 不存在 → LookupError。"""
        instance = db.query(DbInstance).filter(DbInstance.id == int(instance_id)).first()
        if instance is None:
            raise InstanceNotFoundError(f"db_instance id={instance_id} not found")

        # 依赖 dbops_assets 的 DbType 关联；与 callback service 同款 fallback
        db_type_code = "POSTGRESQL"
        try:
            db_type_id = getattr(instance, "db_type_id", None)
            if db_type_id is not None:
                from app.models.dbops_assets import DbType

                db_type = db.query(DbType).filter(DbType.id == db_type_id).first()
                if db_type is not None and getattr(db_type, "type_code", None):
                    db_type_code = str(db_type.type_code).upper()
        except Exception:
            logger.exception("db_type_code lookup failed for instance_id=%s", instance_id)
            db_type_code = "POSTGRESQL"

        return instance, db_type_code

    @staticmethod
    def _normalize_database_name(name: Optional[str]) -> str:
        """归一化 database_name；空值 → '<default>'（与 C9 callback 一致）。"""
        if not name:
            return AiSchemaSnapshotService.DEFAULT_DATABASE_PLACEHOLDER
        cleaned = name.strip()[:200]
        return cleaned or AiSchemaSnapshotService.DEFAULT_DATABASE_PLACEHOLDER

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)