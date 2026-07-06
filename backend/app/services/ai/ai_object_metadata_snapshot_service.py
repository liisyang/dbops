"""Phase 3.6B0 C16-F3 — AiObjectMetadataSnapshotService.

API 触发面 (plan §4.1 + §4.3):

- ``trigger_collection(db, *, instance_id, database_name, schema_name,
  requested_by, request_base_url)``
  → 复用 ``CollectorService.launch_collector_run`` (run_type="ai_object_metadata")
  调起 AWX，callback 通过 ``business_domain='ai_object_metadata'`` 路由到
  ``AiObjectMetadataSnapshotCallbackService.save_snapshots`` 落库。

- ``get_snapshot_status(db, *, instance_id, database_name, schema_name)``
  → 返回该 instance 当前 is_current=true 的 snapshot。

- ``list_history(db, *, instance_id, database_name, schema_name, limit)``
  → 按 created_at DESC 返回历史 snapshots。

- ``get_published_object_metadata(db, *, instance_id, database_name, schema_name)``
  → 供 ``AiSchemaContextService.build_schema_context`` 集成用，返回
  is_current=true + status=success 的最新 snapshot。

- ``cleanup_running_timeouts(db)``
  → 启动时清理超过 ``AI_OBJECT_METADATA_COLLECTION_TIMEOUT_SECONDS`` 的 running
  行，与 C10 schema snapshot 同样策略。

风格（与 C10 AiSchemaSnapshotService 对齐）:
- 全部为 staticmethod / classmethod，签名 ``Service.method(db, *, kw=...)``
- 不重新发明轮子：复用 C16-F3 builder 调 AWX、callback 落库
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import AiObjectMetadataSnapshot, AiObjectMetadataSnapshotStatus
from app.models.dbops_assets import DbInstance

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常
# =============================================================================
class AiObjectMetadataSnapshotError(Exception):
    """Object Metadata Snapshot 服务基类异常。"""


class InstanceNotFoundError(AiObjectMetadataSnapshotError):
    """instance_id 不存在 → 404。"""


class FeatureDisabledError(AiObjectMetadataSnapshotError):
    """AI_SQL_PREVIEW_ENABLED=false → 503 (plan §11 P1 解耦)。"""


class UnsupportedDbTypeError(AiObjectMetadataSnapshotError):
    """db_type 当前不在 capabilities 支持列表 → 422。"""


class AwxLaunchError(AiObjectMetadataSnapshotError):
    """AWX launch 失败 → 502。"""


# =============================================================================
# AiObjectMetadataSnapshotService
# =============================================================================
class AiObjectMetadataSnapshotService:
    """Object Metadata Snapshot 触发 + 状态查询。"""

    DEFAULT_DATABASE_PLACEHOLDER = "<default>"
    DEFAULT_SCHEMA_PLACEHOLDER = "<default>"

    # ------------------------------------------------------------------
    # 触发采集
    # ------------------------------------------------------------------
    @staticmethod
    def trigger_collection(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str],
        schema_name: Optional[str],
        requested_by: Optional[str],
        request_base_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """触发 object metadata 采集。

        复用 ``CollectorService.launch_collector_run`` 路径，强制
        ``check_codes=["DB_OBJECT_METADATA"]`` + ``run_type="ai_object_metadata"``，
        让 C16-F3 Builder 产出 ``business_domain='ai_object_metadata'`` items，
        最终 callback 路由到 ``AiObjectMetadataSnapshotCallbackService``。

        Raises:
            InstanceNotFoundError: instance_id 不存在 → 404
            FeatureDisabledError: AI_SQL_PREVIEW_ENABLED=false → 503
            UnsupportedDbTypeError: 当前 capabilities 不支持该 db_type → 422
            AwxLaunchError: AWX launch 失败 → 502
        """
        settings = get_settings()

        # 功能开关（plan §11 P1 — 按功能解耦，AI_SQL_PREVIEW 同时管控 preview/object metadata）
        if not settings.AI_SQL_PREVIEW_ENABLED:
            raise FeatureDisabledError("AI_SQL_PREVIEW_ENABLED=false")

        # instance 必须存在 + db_type 必须支持
        instance, db_type_code = AiObjectMetadataSnapshotService._resolve_instance(
            db, instance_id
        )

        if db_type_code.upper() not in settings.sql_supported_db_types:
            raise UnsupportedDbTypeError(
                f"db_type '{db_type_code}' not in capabilities "
                f"({settings.sql_supported_db_types}); see GET /api/v1/ai/capabilities"
            )

        # 准备 CollectorRunCreateRequest（直接构造，绕过 Pydantic 校验以避免
        # 默认值的过度约束）
        from app.schemas.collector import CollectorRunCreateRequest

        # database_name / schema_name 透传：request 阶段先尝试以 option 注入，
        # callback 阶段 fallback 到 extra_attrs.ai_object_metadata_* / '<default>'。
        normalized_db = (
            (database_name or "").strip()
            or AiObjectMetadataSnapshotService.DEFAULT_DATABASE_PLACEHOLDER
        )
        normalized_schema = (
            (schema_name or "").strip()
            or AiObjectMetadataSnapshotService.DEFAULT_SCHEMA_PLACEHOLDER
        )
        options: dict[str, Any] = {
            "ai_object_metadata_database_name": normalized_db,
            "ai_object_metadata_schema_name": normalized_schema,
        }
        payload = CollectorRunCreateRequest(
            run_type="ai_object_metadata",
            target_scope="db_instance",
            asset_ids=[instance_id],
            check_codes=["DB_OBJECT_METADATA"],
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
            raise AiObjectMetadataSnapshotError(msg) from exc
        except RuntimeError as exc:
            raise AwxLaunchError(f"AWX launch failed: {exc}") from exc

        logger.info(
            "ai_object_metadata snapshot collection triggered: instance_id=%s db=%s schema=%s "
            "collector_run_id=%s run_id=%s",
            instance_id,
            normalized_db,
            normalized_schema,
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
        schema_name: Optional[str] = None,
    ) -> Optional[AiObjectMetadataSnapshot]:
        """返回该 instance 当前 is_current=true 的 snapshot；不存在则 None。

        database_name / schema_name 默认取 ``<default>``（保持与 callback
        默认一致）。调用方需根据返回是否为 None 决定 404 vs 200 with
        available=false。
        """
        db_name = AiObjectMetadataSnapshotService._normalize_database_name(database_name)
        sch_name = AiObjectMetadataSnapshotService._normalize_schema_name(schema_name)
        return (
            db.query(AiObjectMetadataSnapshot)
            .filter(
                AiObjectMetadataSnapshot.instance_id == instance_id,
                AiObjectMetadataSnapshot.database_name == db_name,
                AiObjectMetadataSnapshot.schema_name == sch_name,
                AiObjectMetadataSnapshot.is_current.is_(True),
            )
            .order_by(AiObjectMetadataSnapshot.id.desc())
            .first()
        )

    @staticmethod
    def get_latest_any_status(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
    ) -> Optional[AiObjectMetadataSnapshot]:
        """返回该 instance 最新任意状态的 snapshot（包含 pending/running/failed）。

        若 is_current 存在则优先 is_current，否则取最新一行 — 用于 GET status
        在未完成采集时也能返回 200 + 进度信息。
        """
        db_name = AiObjectMetadataSnapshotService._normalize_database_name(database_name)
        sch_name = AiObjectMetadataSnapshotService._normalize_schema_name(schema_name)
        current = (
            db.query(AiObjectMetadataSnapshot)
            .filter(
                AiObjectMetadataSnapshot.instance_id == instance_id,
                AiObjectMetadataSnapshot.database_name == db_name,
                AiObjectMetadataSnapshot.schema_name == sch_name,
                AiObjectMetadataSnapshot.is_current.is_(True),
            )
            .first()
        )
        if current is not None:
            return current
        return (
            db.query(AiObjectMetadataSnapshot)
            .filter(
                AiObjectMetadataSnapshot.instance_id == instance_id,
                AiObjectMetadataSnapshot.database_name == db_name,
                AiObjectMetadataSnapshot.schema_name == sch_name,
            )
            .order_by(AiObjectMetadataSnapshot.id.desc())
            .first()
        )

    # ------------------------------------------------------------------
    # 已发布的 object metadata（供 AiSchemaContextService 集成用）
    # ------------------------------------------------------------------
    @staticmethod
    def get_published_object_metadata(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
    ) -> Optional[AiObjectMetadataSnapshot]:
        """返回 is_current=true + status=success 的最新 snapshot。

        与 ``get_snapshot_status`` 的区别：本方法额外校验 ``status == success``
        以及 ``expires_at`` 未过期 — 专供 context service 消费。
        """
        snap = AiObjectMetadataSnapshotService.get_snapshot_status(
            db,
            instance_id=instance_id,
            database_name=database_name,
            schema_name=schema_name,
        )
        if snap is None:
            return None
        if snap.status != AiObjectMetadataSnapshotStatus.SUCCESS:
            return None
        if snap.expires_at is not None and snap.expires_at <= AiObjectMetadataSnapshotService._utcnow():
            return None
        return snap

    # ------------------------------------------------------------------
    # 历史 (GET history)
    # ------------------------------------------------------------------
    @staticmethod
    def list_history(
        db: Session,
        *,
        instance_id: int,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[AiObjectMetadataSnapshot], int]:
        """返回历史 snapshot 列表（created_at DESC, id DESC）。

        包含失败 / 过期版本；前端可选择只显示 success。
        """
        settings = get_settings()
        cap = min(max(limit, 1), settings.AI_OBJECT_METADATA_MAX_OBJECTS or 200)

        db_name = AiObjectMetadataSnapshotService._normalize_database_name(database_name)
        sch_name = AiObjectMetadataSnapshotService._normalize_schema_name(schema_name)
        base = db.query(AiObjectMetadataSnapshot).filter(
            AiObjectMetadataSnapshot.instance_id == instance_id,
            AiObjectMetadataSnapshot.database_name == db_name,
            AiObjectMetadataSnapshot.schema_name == sch_name,
        )
        total = base.count()
        items = (
            base.order_by(
                AiObjectMetadataSnapshot.created_at.desc(),
                AiObjectMetadataSnapshot.id.desc(),
            )
            .limit(cap)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # Stale cleanup（启动时调用，与 chat cleanup 同款策略 — plan §18 C32）
    # ------------------------------------------------------------------
    @classmethod
    def cleanup_running_timeouts(cls, db: Session) -> int:
        """把超过 ``AI_OBJECT_METADATA_COLLECTION_TIMEOUT_SECONDS`` 的 running 行标 failed。

        启动时调用一次（main.py lifespan），防止 collector 中途异常退出后
        running 永久卡住。

        Returns:
            更新的行数
        """
        settings = get_settings()
        timeout_seconds = int(
            getattr(settings, "AI_OBJECT_METADATA_COLLECTION_TIMEOUT_SECONDS", 600)
        )
        cutoff = cls._utcnow_naive() - timedelta(seconds=timeout_seconds)

        result = db.execute(
            update(AiObjectMetadataSnapshot)
            .where(
                and_(
                    AiObjectMetadataSnapshot.status == AiObjectMetadataSnapshotStatus.RUNNING,
                    AiObjectMetadataSnapshot.created_at <= cutoff,
                )
            )
            .values(
                status=AiObjectMetadataSnapshotStatus.FAILED,
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
                "AiObjectMetadataSnapshotService.cleanup_running_timeouts: marked %s snapshots failed (timeout)",
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
        """归一化 database_name；空值 → '<default>'（与 callback 一致）。"""
        if not name:
            return AiObjectMetadataSnapshotService.DEFAULT_DATABASE_PLACEHOLDER
        cleaned = name.strip()[:200]
        return cleaned or AiObjectMetadataSnapshotService.DEFAULT_DATABASE_PLACEHOLDER

    @staticmethod
    def _normalize_schema_name(name: Optional[str]) -> str:
        """归一化 schema_name；空值 → '<default>'（与 callback 一致）。"""
        if not name:
            return AiObjectMetadataSnapshotService.DEFAULT_SCHEMA_PLACEHOLDER
        cleaned = name.strip()[:200]
        return cleaned or AiObjectMetadataSnapshotService.DEFAULT_SCHEMA_PLACEHOLDER

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _utcnow_naive() -> datetime:
        """naive UTC (DB 端 created_at 是 naive TIMESTAMPTZ 比较需要)."""
        return datetime.now(tz=timezone.utc).replace(tzinfo=None)
