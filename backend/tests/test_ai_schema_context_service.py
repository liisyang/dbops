"""Phase 3.6B0 C10 — AiSchemaContextService 单元测试.

覆盖 (plan §4.6 + §13):
  1.  build_schema_context: 无 snapshot → available=false, reason=no_snapshot
  2.  build_schema_context: snapshot 非 success → available=false, reason=snapshot_not_success
  3.  build_schema_context: snapshot.is_current=false → available=false, reason=snapshot_not_current
  4.  build_schema_context: 已过期 → available=false, reason=snapshot_expired
  5.  build_schema_context: 完整 success → available=true, schema_context 非空
  6.  build_schema_context: schema_policy_hash 基于策略 JSON (snapshot_hash 相同 → 相同 hash)
  7.  build_schema_context: schema_policy_hash 随策略内容变化 (snapshot_hash 不同 → 不同 hash)
  8.  build_schema_context: dialect 映射 (POSTGRESQL→postgres, MSSQL→tsql, ORACLE→oracle)
  9.  schema_context 文本截断 (max_chars 极小 → 含 truncated 标记)
  10. schema_policy_version 常量稳定
  11. available=false 时 schema_policy_hash 必须为 None
  12. SQL DIALECT 映射边界 (未知 db_type_code → None)

策略: 与 C10 snapshot service 测试共用 FakeSession 模式；不连真实 DB。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.services.ai.ai_schema_context_service import (
    AiSchemaContextService,
    ContextUnavailableReason,
)


# ---------------------------------------------------------------------------
# Fake session (与 test_ai_schema_snapshot_service.py 一致，但去掉了 execute
# 模拟 — context service 只读)
# ---------------------------------------------------------------------------
@dataclass
class _FakeFilter:
    field: str
    value: Any
    op: str = "=="


@dataclass
class _FakeQueryResult:
    items: list[Any]
    filters: list[_FakeFilter] = field(default_factory=list)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for f in args:
            if isinstance(f, _FakeFilter):
                new_filters.append(f)
        return _FakeQueryResult(items=list(self.items), filters=new_filters)

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        return self

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

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
        return True


@dataclass
class _FakeSession:
    """只读 session — AiSchemaContextService 不写 DB，只查 snapshot。"""

    store: dict[str, list[Any]] = field(default_factory=dict)

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_snapshot(
    *,
    snapshot_id: int = 1,
    instance_id: int = 1,
    database_name: str = "<default>",
    status: str = AiSchemaSnapshotStatus.SUCCESS,
    is_current: bool = True,
    expires_in_hours: Optional[float] = 24,
    snapshot_hash: str = "deadbeef" * 8,
    db_type_code: str = "POSTGRESQL",
    allowed_schemas: Optional[list[str]] = None,
    allowed_tables: Optional[list[str]] = None,
    allowed_columns: Optional[dict[str, list[str]]] = None,
    denied_columns: Optional[list[str]] = None,
) -> AiSchemaSnapshot:
    """直接构造 ORM 对象（与 C10 snapshot service tests 风格一致）。"""
    now = datetime.now(tz=timezone.utc)
    snap = AiSchemaSnapshot(
        instance_id=instance_id,
        db_type_code=db_type_code,
        database_name=database_name,
        schema_name="public",
        status=status,
        allowed_schemas=allowed_schemas if allowed_schemas is not None else ["app"],
        allowed_tables=allowed_tables if allowed_tables is not None else ["app.users", "app.orders"],
        allowed_columns=allowed_columns
        if allowed_columns is not None
        else {"app.users": ["id", "name"], "app.orders": ["id", "status"]},
        denied_columns=denied_columns if denied_columns is not None else ["password_hash"],
        is_current=is_current,
        snapshot_hash=snapshot_hash if status == AiSchemaSnapshotStatus.SUCCESS else None,
        total_tables=2,
        total_columns=4,
        expires_at=(
            now + timedelta(hours=expires_in_hours)
            if expires_in_hours is not None and status == AiSchemaSnapshotStatus.SUCCESS
            else None
        ),
        collected_at=now if status == AiSchemaSnapshotStatus.SUCCESS else None,
        created_at=now,
    )
    snap.id = snapshot_id
    return snap


def _patch_db_type_inference(monkeypatch, db_type_code: Optional[str] = "POSTGRESQL"):
    """monkey-patch _infer_db_type_code，避免真实 DB 查询。"""
    from app.services.ai import ai_schema_context_service

    def _fake_infer(db, instance_id):
        return db_type_code

    monkeypatch.setattr(
        ai_schema_context_service.AiSchemaContextService,
        "_infer_db_type_code",
        staticmethod(_fake_infer),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBuildSchemaContextUnavailable:
    def test_no_snapshot_returns_unavailable(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        result = AiSchemaContextService.build_schema_context(db, instance_id=999)
        assert result["available"] is False
        assert result["instance_id"] == 999
        assert result["reason"] == ContextUnavailableReason.NO_SNAPSHOT
        assert result["schema_policy_hash"] is None

    def test_pending_snapshot_returns_unavailable(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        snap = _make_snapshot(status=AiSchemaSnapshotStatus.PENDING, is_current=False)
        db.add(snap)
        result = AiSchemaContextService.build_schema_context(db, instance_id=1)
        assert result["available"] is False
        assert result["reason"] == ContextUnavailableReason.SNAPSHOT_NOT_SUCCESS

    def test_running_snapshot_returns_unavailable(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        snap = _make_snapshot(status=AiSchemaSnapshotStatus.RUNNING, is_current=False)
        db.add(snap)
        result = AiSchemaContextService.build_schema_context(db, instance_id=1)
        assert result["available"] is False
        assert result["reason"] == ContextUnavailableReason.SNAPSHOT_NOT_SUCCESS

    def test_not_current_returns_unavailable(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        snap = _make_snapshot(
            status=AiSchemaSnapshotStatus.SUCCESS,
            is_current=False,
        )
        db.add(snap)
        result = AiSchemaContextService.build_schema_context(db, instance_id=1)
        assert result["available"] is False
        assert result["reason"] == ContextUnavailableReason.SNAPSHOT_NOT_CURRENT

    def test_expired_returns_unavailable(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        snap = _make_snapshot(
            status=AiSchemaSnapshotStatus.SUCCESS,
            is_current=True,
            expires_in_hours=-1,
        )
        db.add(snap)
        result = AiSchemaContextService.build_schema_context(db, instance_id=1)
        assert result["available"] is False
        assert result["reason"] == ContextUnavailableReason.SNAPSHOT_EXPIRED


class TestBuildSchemaContextAvailable:
    def test_happy_path_returns_available(self, monkeypatch):
        _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
        db = _FakeSession()
        snap = _make_snapshot()
        db.add(snap)
        result = AiSchemaContextService.build_schema_context(db, instance_id=1)
        assert result["available"] is True
        assert result["instance_id"] == 1
        assert result["db_type_code"] == "POSTGRESQL"
        assert result["sql_dialect"] == "postgres"
        assert result["schema_snapshot_id"] == 1
        assert isinstance(result["schema_context"], str) and result["schema_context"]
        assert isinstance(result["schema_policy_hash"], str)
        assert len(result["schema_policy_hash"]) == 64
        assert result["allowed_tables"] == ["app.users", "app.orders"]
        assert "app.users" in result["allowed_columns"]
        assert "password_hash" in result["denied_columns"]

    def test_schema_policy_hash_stable_for_same_input(self):
        """相同输入 → 相同 hash（plan §4.5 P0-3 核心不变量）。"""
        h1 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=["app.users"],
            allowed_columns={"app.users": ["id", "name"]},
            denied_columns=["password"],
            policy_version="v1",
        )
        h2 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=["app.users"],
            allowed_columns={"app.users": ["id", "name"]},
            denied_columns=["password"],
            policy_version="v1",
        )
        assert h1 == h2

    def test_schema_policy_hash_changes_with_snapshot_hash(self):
        h1 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=["app.users"],
            allowed_columns={"app.users": ["id"]},
            denied_columns=[],
            policy_version="v1",
        )
        h2 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="xyz",
            allowed_schemas=["app"],
            allowed_tables=["app.users"],
            allowed_columns={"app.users": ["id"]},
            denied_columns=[],
            policy_version="v1",
        )
        assert h1 != h2

    def test_schema_policy_hash_changes_with_policy_version(self):
        h1 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=[],
            allowed_columns={},
            denied_columns=[],
            policy_version="v1",
        )
        h2 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=[],
            allowed_columns={},
            denied_columns=[],
            policy_version="v2",
        )
        assert h1 != h2

    def test_schema_policy_hash_independent_of_text_format(self):
        """hash 基于规范化策略 JSON 而非展示文本（plan §4.5 P0-3 硬约束）。

        通过 _compute_schema_policy_hash 直接验证：tables 顺序不同但
        排序后相同 → hash 相同（canonical JSON 内部 sort_keys 兜底）。
        """
        h1 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=["app.a", "app.b"],
            allowed_columns={"app.a": ["x", "y"], "app.b": ["p"]},
            denied_columns=["pw"],
            policy_version="v1",
        )
        h2 = AiSchemaContextService._compute_schema_policy_hash(
            snapshot_hash="abc",
            allowed_schemas=["app"],
            allowed_tables=["app.b", "app.a"],
            allowed_columns={"app.b": ["p"], "app.a": ["y", "x"]},
            denied_columns=["pw"],
            policy_version="v1",
        )
        assert h1 == h2


class TestSqlDialectMapping:
    @pytest.mark.parametrize(
        "db_type_code,expected",
        [
            ("POSTGRESQL", "postgres"),
            ("MYSQL", "mysql"),
            ("ORACLE", "oracle"),
            ("MSSQL", "tsql"),
            ("UNKNOWN", None),
            ("", None),
        ],
    )
    def test_dialect_mapping(self, db_type_code, expected):
        assert AiSchemaContextService._dialect_for(db_type_code) == expected


class TestSchemaContextRendering:
    def test_short_text_unchanged(self):
        text = AiSchemaContextService._render_schema_context(
            db_type_code="POSTGRESQL",
            database_name="postgres",
            allowed_schemas=["app"],
            allowed_tables=["app.users"],
            allowed_columns={"app.users": ["id", "name"]},
            denied_columns=["password_hash"],
            max_chars=30000,
        )
        assert "DB: POSTGRESQL (database=postgres)" in text
        assert "Allowed schemas: ['app']" in text
        assert "app.users(id, name)" in text
        assert "Denied columns (sensitive): ['password_hash']" in text
        assert "…(truncated)" not in text

    def test_long_text_truncated_with_marker(self):
        many_tables = [f"app.table_{i:04d}" for i in range(2000)]
        many_columns = {t: ["c1", "c2", "c3"] for t in many_tables}
        text = AiSchemaContextService._render_schema_context(
            db_type_code="POSTGRESQL",
            database_name="postgres",
            allowed_schemas=["app"],
            allowed_tables=many_tables,
            allowed_columns=many_columns,
            denied_columns=[],
            max_chars=500,
        )
        assert len(text) <= 500
        assert text.endswith("…(truncated)")

    def test_no_tables_section(self):
        text = AiSchemaContextService._render_schema_context(
            db_type_code="POSTGRESQL",
            database_name="postgres",
            allowed_schemas=[],
            allowed_tables=[],
            allowed_columns={},
            denied_columns=[],
            max_chars=10000,
        )
        assert "Allowed tables (0):" in text
        assert "Denied columns" not in text


class TestConstants:
    def test_policy_version_stable(self):
        """POLICY_VERSION 必须稳定 — 改值会破坏 Execute 阶段 hash 校验。"""
        assert AiSchemaContextService.POLICY_VERSION == "2026-06-28-v1"