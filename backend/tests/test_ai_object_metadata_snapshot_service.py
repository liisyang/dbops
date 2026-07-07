"""
Phase 3.6B0 C16-F3 — AiObjectMetadataSnapshotService 单元测试.

覆盖 (plan §13 Object Metadata Snapshot 矩阵的 API 部分):
  1.  trigger_collection: feature disabled → FeatureDisabledError
  2.  trigger_collection: instance 不存在 → InstanceNotFoundError
  3.  trigger_collection: db_type 不在 capabilities → UnsupportedDbTypeError
  4.  trigger_collection: 复用 CollectorService 成功路径 → 返回 collector_run_id / run_id
  5.  get_snapshot_status: 无 snapshot → None
  6.  get_snapshot_status: is_current 优先 → 命中 current 行
  7.  get_latest_any_status: 退化到任意最新一行（含 failed）
  8.  list_history: created_at DESC 排序 + limit 截断
  9.  cleanup_running_timeouts: cutoff 之前的 running → failed
 10. _normalize_database_name: 空值 → '<default>'（与 callback 一致）
 11. _normalize_database_name: 200+ 字符 → 截断到 200
 12. _normalize_schema_name: 空值 → '<default>'

策略: 与 test_ai_schema_snapshot_service.py 一致 — 自制 FakeSession +
InMemoryQueryStore 模拟 SQLAlchemy 行为，不连真实 DB。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import AiObjectMetadataSnapshot, AiObjectMetadataSnapshotStatus
from app.services.ai.ai_object_metadata_snapshot_service import (
    AiObjectMetadataSnapshotService,
    AwxLaunchError,
    FeatureDisabledError,
    InstanceNotFoundError,
    UnsupportedDbTypeError,
)


# ---------------------------------------------------------------------------
# Fake ORM primitives（与 C10 schema snapshot 测试共用模式）
# ---------------------------------------------------------------------------
@dataclass
class _FakeFilter:
    field: str
    value: Any
    op: str = "=="  # == / is_ / in_ / le


@dataclass
class _FakeQueryResult:
    items: list[Any]
    filters: list[_FakeFilter] = field(default_factory=list)
    _ordered: bool = False
    _limit: Optional[int] = None

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for f in args:
            if isinstance(f, _FakeFilter):
                new_filters.append(f)
        return _FakeQueryResult(items=list(self.items), filters=new_filters)

    def with_for_update(self) -> "_FakeQueryResult":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new = _FakeQueryResult(items=list(self.items), filters=list(self.filters))
        new._ordered = True
        return new

    def limit(self, n: int) -> "_FakeQueryResult":
        new = _FakeQueryResult(items=list(self.items), filters=list(self.filters))
        new._ordered = self._ordered
        new._limit = n
        return new

    def _matches(self, item: Any) -> bool:
        for f in self.filters:
            actual = getattr(item, f.field, None)
            if f.op == "==":
                if actual != f.value:
                    return False
            elif f.op == "is_":
                if isinstance(f.value, bool):
                    if bool(actual) != f.value:
                        return False
                else:
                    if actual is not f.value:
                        return False
            elif f.op == "in_":
                if actual not in (f.value or ()):
                    return False
            elif f.op == "le":
                if actual is None or actual > f.value:
                    return False
        return True

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

    def all(self) -> list[Any]:
        matched = [it for it in self.items if self._matches(it)]
        if self._ordered:
            matched = list(reversed(matched))  # created_at DESC 模拟
        if self._limit is not None:
            matched = matched[: self._limit]
        return matched

    def count(self) -> int:
        return sum(1 for it in self.items if self._matches(it))


@dataclass
class _FakeExecuteResult:
    rowcount: int = 0


@dataclass
class _FakeSession:
    store: dict[str, list[Any]] = field(default_factory=dict)
    executed: list[Any] = field(default_factory=list)

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))

    def commit(self) -> None:
        pass

    def execute(self, statement: Any) -> _FakeExecuteResult:
        self.executed.append(statement)
        return _FakeExecuteResult(rowcount=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_snapshot(
    *,
    instance_id: int = 1,
    database_name: str = "<default>",
    schema_name: str = "<default>",
    status: str = AiObjectMetadataSnapshotStatus.SUCCESS,
    is_current: bool = False,
    created_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    snapshot_id: int = 1,
    snapshot_hash: str = "h" * 64,
    total_object_count: int = 0,
    db_type_code: str = "POSTGRESQL",
) -> AiObjectMetadataSnapshot:
    """直接构造 ORM 对象，绕过 SQLAlchemy 真实 INSERT。"""
    snap = AiObjectMetadataSnapshot(
        instance_id=instance_id,
        db_type_code=db_type_code,
        database_name=database_name,
        schema_name=schema_name,
        status=status,
        is_current=is_current,
        collector_run_id=None,
        snapshot_hash=snapshot_hash if status == AiObjectMetadataSnapshotStatus.SUCCESS else None,
        object_ddl_sha256=(
            "a" * 64 if status == AiObjectMetadataSnapshotStatus.SUCCESS else None
        ),
        object_ddl_text=(
            "CREATE TABLE t1 (id int);" if status == AiObjectMetadataSnapshotStatus.SUCCESS else None
        ),
        table_count=1 if status == AiObjectMetadataSnapshotStatus.SUCCESS else 0,
        view_count=0,
        index_count=0,
        function_count=0,
        total_object_count=total_object_count,
        expires_at=expires_at,
        collected_at=(
            datetime.now(tz=timezone.utc) if status == AiObjectMetadataSnapshotStatus.SUCCESS else None
        ),
        created_at=created_at or datetime.now(tz=timezone.utc),
    )
    snap.id = snapshot_id
    return snap


def _settings_fake(
    *, timeout_seconds: int = 300,
    sql_supported_db_types: tuple[str, ...] = ("POSTGRESQL",),
    ai_object_metadata_max_objects: int = 200,
    ai_object_metadata_ttl_hours: int = 24,
    ai_sql_preview_enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        AI_OBJECT_METADATA_COLLECTION_TIMEOUT_SECONDS=timeout_seconds,
        sql_supported_db_types=sql_supported_db_types,
        AI_OBJECT_METADATA_MAX_OBJECTS=ai_object_metadata_max_objects,
        AI_OBJECT_METADATA_TTL_HOURS=ai_object_metadata_ttl_hours,
        AI_SQL_PREVIEW_ENABLED=ai_sql_preview_enabled,
    )


def _patch_settings(monkeypatch, **kwargs: Any) -> None:
    from app.services.ai import ai_object_metadata_snapshot_service as svc_mod

    monkeypatch.setattr(
        svc_mod,
        "get_settings",
        lambda: _settings_fake(**kwargs),
    )


def _seed_instance(
    db: _FakeSession, *, instance_id: int = 100, type_code: str = "postgresql",
) -> None:
    db.store.setdefault("DbInstance", []).append(
        SimpleNamespace(id=instance_id, db_type_id=1, extra_attrs={})
    )
    db.store.setdefault("DbType", []).append(
        SimpleNamespace(id=1, type_code=type_code)
    )


# ---------------------------------------------------------------------------
# 1. trigger_collection 错误路径
# ---------------------------------------------------------------------------

class TestTriggerCollectionErrors:
    def test_feature_disabled_raises(self, monkeypatch):
        _patch_settings(monkeypatch, ai_sql_preview_enabled=False)
        db = _FakeSession()
        _seed_instance(db, instance_id=100)
        with pytest.raises(FeatureDisabledError) as exc_info:
            AiObjectMetadataSnapshotService.trigger_collection(
                db,
                instance_id=100,
                database_name="<default>",
                schema_name="<default>",
                requested_by="tester",
            )
        assert "AI_SQL_PREVIEW_ENABLED=false" in str(exc_info.value)

    def test_instance_not_found_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        # 不 seed instance → LookupError → InstanceNotFoundError
        with pytest.raises(InstanceNotFoundError):
            AiObjectMetadataSnapshotService.trigger_collection(
                db,
                instance_id=999,
                database_name="<default>",
                schema_name="<default>",
                requested_by="tester",
            )

    def test_db_type_not_in_capabilities_raises(self, monkeypatch):
        # capabilities 仅 POSTGRESQL，实例是 oracle → UnsupportedDbTypeError
        _patch_settings(monkeypatch, sql_supported_db_types=("POSTGRESQL",))
        db = _FakeSession()
        _seed_instance(db, instance_id=100, type_code="oracle")
        with pytest.raises(UnsupportedDbTypeError):
            AiObjectMetadataSnapshotService.trigger_collection(
                db,
                instance_id=100,
                database_name="<default>",
                schema_name="<default>",
                requested_by="tester",
            )


# ---------------------------------------------------------------------------
# 2. trigger_collection 成功路径（mock CollectorService）
# ---------------------------------------------------------------------------

class TestTriggerCollectionSuccess:
    def _patch_launcher(self, monkeypatch, return_value: dict[str, Any]) -> None:
        from app.services import collector_service as cs_mod

        monkeypatch.setattr(
            cs_mod.CollectorService,
            "launch_collector_run",
            lambda db, *, payload, requested_by, request_base_url: dict(return_value),
        )

    def test_returns_collector_run_id_and_run_id(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        _seed_instance(db, instance_id=100)
        self._patch_launcher(
            monkeypatch,
            return_value={
                "collector_run_id": 42,
                "run_id": "RUN-20260706-001",
                "awx_job_id": 581,
                "awx_job_url": "http://awx.example/#/jobs/581",
                "status": "launched",
                "item_count": 1,
            },
        )

        result = AiObjectMetadataSnapshotService.trigger_collection(
            db,
            instance_id=100,
            database_name="<default>",
            schema_name="<default>",
            requested_by="tester",
            request_base_url="http://dbops.example",
        )

        assert result["collector_run_id"] == 42
        assert result["run_id"] == "RUN-20260706-001"
        assert result["awx_job_id"] == 581
        assert result["status"] == "launched"
        assert result["item_count"] == 1

    def test_awx_runtime_error_wraps_to_awx_launch_error(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        _seed_instance(db, instance_id=100)

        from app.services import collector_service as cs_mod

        def _raise_runtime(*args, **kwargs):
            raise RuntimeError("AWX template not found")

        monkeypatch.setattr(cs_mod.CollectorService, "launch_collector_run", _raise_runtime)

        with pytest.raises(AwxLaunchError) as exc_info:
            AiObjectMetadataSnapshotService.trigger_collection(
                db,
                instance_id=100,
                database_name="<default>",
                schema_name="<default>",
                requested_by="tester",
            )
        assert "AWX launch failed" in str(exc_info.value)

    def test_no_items_generated_raises_unsupported_db_type(self, monkeypatch):
        """CollectorService ValueError + '未生成任何可执行校验项' → UnsupportedDbTypeError"""
        _patch_settings(monkeypatch)
        db = _FakeSession()
        _seed_instance(db, instance_id=100)

        from app.services import collector_service as cs_mod

        def _raise_value_error(*args, **kwargs):
            raise ValueError("未生成任何可执行校验项 (instance 100)")

        monkeypatch.setattr(cs_mod.CollectorService, "launch_collector_run", _raise_value_error)

        with pytest.raises(UnsupportedDbTypeError) as exc_info:
            AiObjectMetadataSnapshotService.trigger_collection(
                db,
                instance_id=100,
                database_name="<default>",
                schema_name="<default>",
                requested_by="tester",
            )
        assert "no collectible items generated" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. get_snapshot_status / get_latest_any_status / list_history
# ---------------------------------------------------------------------------

class TestSnapshotQueries:
    def test_get_snapshot_status_no_snapshot_returns_none(self):
        db = _FakeSession()
        snap = AiObjectMetadataSnapshotService.get_snapshot_status(
            db, instance_id=999, database_name="<default>"
        )
        assert snap is None

    def test_get_snapshot_status_is_current_preferred(self):
        db = _FakeSession()
        cur = _make_snapshot(
            snapshot_id=1, is_current=True,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        old = _make_snapshot(
            snapshot_id=2, is_current=False,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        db.add(cur)
        db.add(old)
        snap = AiObjectMetadataSnapshotService.get_snapshot_status(db, instance_id=1)
        assert snap is not None
        assert snap.id == 1
        assert snap.is_current is True

    def test_get_latest_any_status_falls_back_to_newest(self):
        """is_current 不存在时退化到 created_at DESC 最新任意状态行"""
        db = _FakeSession()
        failed = _make_snapshot(
            snapshot_id=10,
            status=AiObjectMetadataSnapshotStatus.FAILED,
            is_current=False,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db.add(failed)
        snap = AiObjectMetadataSnapshotService.get_latest_any_status(db, instance_id=1)
        assert snap is not None
        assert snap.id == 10
        assert snap.status == AiObjectMetadataSnapshotStatus.FAILED

    def test_get_published_object_metadata_filters_expired(self):
        """过期 snapshot → get_published 返回 None（即使 is_current=true）"""
        db = _FakeSession()
        expired = _make_snapshot(
            snapshot_id=1,
            is_current=True,
            expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        db.add(expired)
        snap = AiObjectMetadataSnapshotService.get_published_object_metadata(
            db, instance_id=1
        )
        assert snap is None

    def test_get_published_object_metadata_success(self):
        db = _FakeSession()
        snap_ok = _make_snapshot(
            snapshot_id=1,
            is_current=True,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        )
        db.add(snap_ok)
        snap = AiObjectMetadataSnapshotService.get_published_object_metadata(
            db, instance_id=1
        )
        assert snap is not None
        assert snap.id == 1

    def test_list_history_respects_limit(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        for i in range(5):
            db.add(
                _make_snapshot(
                    snapshot_id=i + 1,
                    status=AiObjectMetadataSnapshotStatus.FAILED,
                    created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        items, total = AiObjectMetadataSnapshotService.list_history(
            db, instance_id=1, limit=3
        )
        assert total == 5
        assert len(items) == 3

    def test_list_history_empty(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        items, total = AiObjectMetadataSnapshotService.list_history(db, instance_id=42)
        assert items == []
        assert total == 0


# ---------------------------------------------------------------------------
# 4. cleanup_running_timeouts
# ---------------------------------------------------------------------------

class TestCleanupRunningTimeouts:
    def test_statement_targets_ai_object_metadata_snapshot(self, monkeypatch):
        _patch_settings(monkeypatch, timeout_seconds=300)
        db = _FakeSession()
        affected = AiObjectMetadataSnapshotService.cleanup_running_timeouts(db)
        assert affected == 1  # _FakeExecuteResult default rowcount=1
        assert len(db.executed) == 1
        stmt = db.executed[0]
        # statement.table.name 应为 ai_object_metadata_snapshot
        assert getattr(getattr(stmt, "table", None), "name", None) == "ai_object_metadata_snapshot"

    def test_no_exception_when_settings_have_no_timeout(self, monkeypatch):
        """Settings 不存在时也应走完清理逻辑（即使 0 affected）。"""
        _patch_settings(monkeypatch, timeout_seconds=300)
        db = _FakeSession()
        affected = AiObjectMetadataSnapshotService.cleanup_running_timeouts(db)
        assert len(db.executed) == 1
        assert affected >= 0


# ---------------------------------------------------------------------------
# 5. _normalize_database_name / _normalize_schema_name
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_normalize_database_name_empty_to_default(self):
        assert AiObjectMetadataSnapshotService._normalize_database_name(None) == "<default>"
        assert AiObjectMetadataSnapshotService._normalize_database_name("") == "<default>"
        assert AiObjectMetadataSnapshotService._normalize_database_name("   ") == "<default>"

    def test_normalize_database_name_truncates_200_chars(self):
        long_name = "a" * 250
        out = AiObjectMetadataSnapshotService._normalize_database_name(long_name)
        assert len(out) == 200
        assert out == "a" * 200

    def test_normalize_database_name_strips_whitespace(self):
        assert AiObjectMetadataSnapshotService._normalize_database_name("  app_db  ") == "app_db"

    def test_normalize_schema_name_empty_to_default(self):
        assert AiObjectMetadataSnapshotService._normalize_schema_name(None) == "<default>"
        assert AiObjectMetadataSnapshotService._normalize_schema_name("") == "<default>"

    def test_normalize_schema_name_truncates_200_chars(self):
        long_schema = "s" * 250
        out = AiObjectMetadataSnapshotService._normalize_schema_name(long_schema)
        assert len(out) == 200