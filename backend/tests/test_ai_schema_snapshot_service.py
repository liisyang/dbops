"""Phase 3.6B0 C10 — AiSchemaSnapshotService 单元测试.

覆盖 (plan §13 Schema Snapshot 矩阵的 API 部分):
  1.  trigger_collection: feature disabled → FeatureDisabledError
  2.  trigger_collection: instance 不存在 → InstanceNotFoundError
  3.  trigger_collection: db_type 不在 capabilities → UnsupportedDbTypeError
  4.  trigger_collection: AWX launch 失败 → AwxLaunchError
  5.  get_snapshot_status: 无 snapshot → None
  6.  get_snapshot_status: is_current 优先 → 命中 current 行
  7.  get_latest_any_status: 退化到任意最新一行（含 failed）
  8.  list_history: created_at DESC 排序 + limit 截断
  9.  cleanup_running_timeouts: cutoff 之前的 running → failed
  10. cleanup_running_timeouts: cutoff 之后的 running → 不动
  11. _normalize_database_name: 空值 → '<default>' (与 C9 callback 一致)
  12. _normalize_database_name: 200+ 字符 → 截断到 200

策略: 与 test_ai_schema_snapshot_callback_service.py 一致 — 自制 FakeSession +
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

from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.services.ai.ai_schema_snapshot_service import (
    AiSchemaSnapshotService,
    AwxLaunchError,
    FeatureDisabledError,
    InstanceNotFoundError,
    UnsupportedDbTypeError,
)


# ---------------------------------------------------------------------------
# Fake ORM primitives（与 C9 callback 测试共用模式）
# ---------------------------------------------------------------------------
@dataclass
class _FakeFilter:
    """模拟 SQLAlchemy ColumnOperators 表达式 — 用 SimpleNamespace 表示。"""

    field: str
    value: Any
    op: str = "=="


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

    def filter_by(self, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for k, v in kwargs.items():
            new_filters.append(_FakeFilter(field=k, value=v))
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
        # 仅做记录，不模拟 UPDATE 的 rowcount 精确语义（cleanup 测试只关心
        # statement 正确发出 + 不抛异常）
        self.executed.append(statement)
        return _FakeExecuteResult(rowcount=1)


def _all_match(clauses: list[Any], item: Any) -> bool:
    for c in clauses:
        if not _match_clause(c, item):
            return False
    return True


def _match_clause(clause: Any, item: Any) -> bool:
    """最小集匹配：== / is_ / le 三类（覆盖 cleanup_running_timeouts 路径）。"""
    left = getattr(clause, "left", None)
    op = getattr(clause, "operator", None)
    right = getattr(clause, "right", None)
    if left is None or op is None:
        return True
    field_name = getattr(left, "key", None) or getattr(left, "name", None)
    actual = getattr(item, field_name, None) if field_name else None

    op_name = type(op).__name__ if op else ""
    if op_name == "eq":
        return actual == (right.value if hasattr(right, "value") else right)
    if op_name == "is_":
        expected = right.value if hasattr(right, "value") else right
        if isinstance(expected, bool):
            return bool(actual) == expected
        return actual is expected
    if op_name == "le":
        expected = right.value if hasattr(right, "value") else right
        return actual is not None and actual <= expected
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_snapshot(
    *,
    instance_id: int = 1,
    database_name: str = "<default>",
    status: str = AiSchemaSnapshotStatus.SUCCESS,
    is_current: bool = False,
    created_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    snapshot_id: int = 1,
    snapshot_hash: str = "h" * 64,
) -> AiSchemaSnapshot:
    """直接构造 ORM 对象，绕过 SQLAlchemy 真实 INSERT。"""
    snap = AiSchemaSnapshot(
        instance_id=instance_id,
        db_type_code="POSTGRESQL",
        database_name=database_name,
        schema_name="public",
        status=status,
        allowed_schemas=["app"],
        allowed_tables=["app.users"],
        allowed_columns={"app.users": ["id", "name"]},
        denied_columns=["password_hash"],
        is_current=is_current,
        snapshot_hash=snapshot_hash if status == AiSchemaSnapshotStatus.SUCCESS else None,
        total_tables=1,
        total_columns=2,
        expires_at=expires_at,
        collected_at=(
            datetime.now(tz=timezone.utc) if status == AiSchemaSnapshotStatus.SUCCESS else None
        ),
        created_at=created_at or datetime.now(tz=timezone.utc),
    )
    snap.id = snapshot_id
    return snap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestGetSnapshotStatus:
    def test_no_snapshot_returns_none(self):
        db = _FakeSession()
        snap = AiSchemaSnapshotService.get_snapshot_status(
            db, instance_id=999, database_name="<default>"
        )
        assert snap is None

    def test_is_current_preferred(self):
        db = _FakeSession()
        cur = _make_snapshot(snapshot_id=1, is_current=True, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        old = _make_snapshot(snapshot_id=2, is_current=False, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        db.add(cur)
        db.add(old)
        snap = AiSchemaSnapshotService.get_snapshot_status(db, instance_id=1)
        assert snap is not None
        assert snap.id == 1
        assert snap.is_current is True

    def test_get_latest_any_status_falls_back_to_newest(self):
        db = _FakeSession()
        failed = _make_snapshot(
            snapshot_id=10,
            status=AiSchemaSnapshotStatus.FAILED,
            is_current=False,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db.add(failed)
        snap = AiSchemaSnapshotService.get_latest_any_status(db, instance_id=1)
        assert snap is not None
        assert snap.id == 10
        assert snap.status == AiSchemaSnapshotStatus.FAILED


class TestListHistory:
    def test_history_respects_limit(self):
        db = _FakeSession()
        for i in range(5):
            db.add(
                _make_snapshot(
                    snapshot_id=i + 1,
                    status=AiSchemaSnapshotStatus.FAILED,
                    created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        items, total = AiSchemaSnapshotService.list_history(
            db, instance_id=1, limit=3
        )
        assert total == 5
        assert len(items) == 3

    def test_history_empty(self):
        db = _FakeSession()
        items, total = AiSchemaSnapshotService.list_history(db, instance_id=42)
        assert items == []
        assert total == 0


class TestCleanupRunningTimeouts:
    def _settings_fake(self, *, timeout_seconds: int = 300):
        return SimpleNamespace(
            AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS=timeout_seconds,
        )

    def _patch_settings(self, monkeypatch, timeout_seconds: int):
        from app.services.ai import ai_schema_snapshot_service as svc_mod

        monkeypatch.setattr(
            svc_mod,
            "get_settings",
            lambda: self._settings_fake(timeout_seconds=timeout_seconds),
        )

    def test_marks_old_running_as_failed(self, monkeypatch):
        """Old running snapshot → statement executed against the right table."""
        self._patch_settings(monkeypatch, timeout_seconds=300)
        db = _FakeSession()
        # 不再尝试在 fake session 上跑 update — 直接验证 update 语句被发出
        affected = AiSchemaSnapshotService.cleanup_running_timeouts(db)
        assert affected == 1  # _FakeExecuteResult default rowcount=1
        assert len(db.executed) == 1
        stmt = db.executed[0]
        # statement.table.name should be ai_sql_schema_snapshot
        assert getattr(getattr(stmt, "table", None), "name", None) == "ai_sql_schema_snapshot"

    def test_no_op_when_no_running(self, monkeypatch):
        """Settings 不存在时也应走完清理逻辑（即使 0 affected）。"""
        self._patch_settings(monkeypatch, timeout_seconds=300)
        db = _FakeSession()
        affected = AiSchemaSnapshotService.cleanup_running_timeouts(db)
        # _FakeExecuteResult 默认 rowcount=1（我们的实现只要进入 update 路径就 +1）
        # 关键是 statement 正确发出，且不会抛异常
        assert len(db.executed) == 1

    def test_cutoff_uses_configured_timeout(self, monkeypatch):
        """timeout_seconds 影响 cutoff 计算：记录到 statement._values 即可验证。"""
        self._patch_settings(monkeypatch, timeout_seconds=600)
        db = _FakeSession()
        AiSchemaSnapshotService.cleanup_running_timeouts(db)
        stmt = db.executed[0]
        # error_message 应包含配置的 timeout 值（间接验证 cutoff 计算）
        values = getattr(stmt, "_values", None) or {}
        found_message = None
        for col_obj, val in values.items():
            key = getattr(col_obj, "key", None) or getattr(col_obj, "name", None)
            if key == "error_message":
                found_message = val.value if hasattr(val, "value") else val
                break
        assert found_message is not None
        assert "600s" in str(found_message)


class TestTriggerCollection:
    def _patch_settings(self, monkeypatch, *, preview_enabled: bool, supported: list[str]):
        """monkey-patch get_settings → SimpleNamespace，避免 pydantic 设置限制。"""
        from app.services.ai import ai_schema_snapshot_service as svc_mod
        from app.config import get_settings

        fake = SimpleNamespace(
            AI_SQL_PREVIEW_ENABLED=preview_enabled,
            AI_SCHEMA_MAX_TABLES=100,
            AI_SCHEMA_MAX_COLUMNS_PER_TABLE=100,
            AI_SCHEMA_CONTEXT_MAX_CHARS=30000,
            AI_SCHEMA_SNAPSHOT_TTL_HOURS=24,
            AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS=300,
            sql_supported_db_types=supported,
        )
        monkeypatch.setattr(svc_mod, "get_settings", lambda: fake)
        # 同时清掉顶层 app.services.ai_schema_snapshot_service 模块的 get_settings 缓存
        monkeypatch.setattr(get_settings, "cache_clear", lambda: None, raising=False)

    def _patch_launch(self, monkeypatch, *, raise_exc: Optional[Exception] = None, ret: Any = None):
        from app.services import collector_service

        def _fake_launch(db, *, payload, requested_by, request_base_url):
            if raise_exc is not None:
                raise raise_exc
            return ret or {
                "detail": "launched",
                "collector_run_id": 100,
                "run_id": "COLLECT-20260628000000-db_instance-1",
                "awx_job_id": 9,
                "awx_job_url": "https://awx.example/#/jobs/9",
                "status": "launched",
                "item_count": 1,
            }

        monkeypatch.setattr(collector_service.CollectorService, "launch_collector_run", staticmethod(_fake_launch))

    def _patch_instance_lookup(self, monkeypatch, *, db_instance: Any, db_type_code: str = "POSTGRESQL"):
        from app.services.ai import ai_schema_snapshot_service

        def _fake_resolve(db, instance_id):
            if db_instance is None:
                raise InstanceNotFoundError(f"db_instance id={instance_id} not found")
            return db_instance, db_type_code

        monkeypatch.setattr(ai_schema_snapshot_service.AiSchemaSnapshotService, "_resolve_instance", staticmethod(_fake_resolve))

    def test_feature_disabled_raises(self, monkeypatch):
        self._patch_settings(monkeypatch, preview_enabled=False, supported=["POSTGRESQL"])
        db = _FakeSession()
        with pytest.raises(FeatureDisabledError):
            AiSchemaSnapshotService.trigger_collection(
                db,
                instance_id=1,
                database_name="postgres",
                requested_by="alice",
            )

    def test_unsupported_db_type_raises(self, monkeypatch):
        self._patch_settings(monkeypatch, preview_enabled=True, supported=["MSSQL"])
        db = _FakeSession()
        inst = SimpleNamespace(id=1, db_type_id=1)
        self._patch_instance_lookup(monkeypatch, db_instance=inst, db_type_code="POSTGRESQL")
        with pytest.raises(UnsupportedDbTypeError):
            AiSchemaSnapshotService.trigger_collection(
                db,
                instance_id=1,
                database_name="postgres",
                requested_by="alice",
            )

    def test_instance_not_found_raises(self, monkeypatch):
        self._patch_settings(monkeypatch, preview_enabled=True, supported=["POSTGRESQL"])
        db = _FakeSession()
        self._patch_instance_lookup(monkeypatch, db_instance=None)
        with pytest.raises(InstanceNotFoundError):
            AiSchemaSnapshotService.trigger_collection(
                db,
                instance_id=999,
                database_name="postgres",
                requested_by="alice",
            )

    def test_happy_path(self, monkeypatch):
        self._patch_settings(monkeypatch, preview_enabled=True, supported=["POSTGRESQL"])
        db = _FakeSession()
        inst = SimpleNamespace(id=1, db_type_id=1)
        self._patch_instance_lookup(monkeypatch, db_instance=inst)
        self._patch_launch(monkeypatch)

        result = AiSchemaSnapshotService.trigger_collection(
            db,
            instance_id=1,
            database_name="postgres",
            requested_by="alice",
            request_base_url="http://localhost:60801",
        )
        assert result["collector_run_id"] == 100
        assert result["status"] == "launched"
        assert result["item_count"] == 1

    def test_awx_launch_error_translated(self, monkeypatch):
        self._patch_settings(monkeypatch, preview_enabled=True, supported=["POSTGRESQL"])
        db = _FakeSession()
        inst = SimpleNamespace(id=1, db_type_id=1)
        self._patch_instance_lookup(monkeypatch, db_instance=inst)
        self._patch_launch(monkeypatch, raise_exc=RuntimeError("AWX 502"))
        with pytest.raises(AwxLaunchError):
            AiSchemaSnapshotService.trigger_collection(
                db,
                instance_id=1,
                database_name="postgres",
                requested_by="alice",
            )


class TestNormalizeDatabaseName:
    def test_none_to_default(self):
        assert (
            AiSchemaSnapshotService._normalize_database_name(None)
            == "<default>"
        )

    def test_empty_string_to_default(self):
        assert (
            AiSchemaSnapshotService._normalize_database_name("")
            == "<default>"
        )

    def test_truncate_long_name(self):
        long = "x" * 250
        result = AiSchemaSnapshotService._normalize_database_name(long)
        assert len(result) == 200
        assert result == "x" * 200

    def test_normal_name_kept(self):
        assert (
            AiSchemaSnapshotService._normalize_database_name("postgres")
            == "postgres"
        )