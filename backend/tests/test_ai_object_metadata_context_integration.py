"""
Phase 3.6B0 C16-F3 — AiSchemaContextService 集成测试（object_metadata 注入）

覆盖 (plan §13 Object Metadata Snapshot 矩阵的 context 集成部分):
  1.  无 schema snapshot → available=false, object_metadata 字段不存在 (no key)
  2.  schema snapshot success + 无 object metadata → object_metadata=None
  3.  schema snapshot success + 已发布 object metadata → object_metadata 注入 dict
  4.  object_metadata dict 必备键齐全 (snapshot_id / sha256 / counts / total / preview)
  5.  object_metadata sha256 与 AiObjectMetadataSnapshot.object_ddl_sha256 一致
  6.  counts (table/view/index/function/total) 数值与 snapshot 字段一致
  7.  object_ddl_text_preview 限 8000 字符注入（超过 → 截断到 8000）
  8.  现有 schema_context 键 (available/schema_context/policy_hash 等) 未被破坏
  9.  object_metadata lookup 抛异常 → 返回 None (try/except 兜底)

策略: 与 test_ai_schema_context_service.py 一致 — FakeSession + InMemoryQueryStore。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import (
    AiObjectMetadataSnapshot,
    AiObjectMetadataSnapshotStatus,
    AiSchemaSnapshot,
    AiSchemaSnapshotStatus,
)
from app.services.ai.ai_schema_context_service import (
    AiSchemaContextService,
    ContextUnavailableReason,
)


# ---------------------------------------------------------------------------
# Fake session (与 test_ai_schema_context_service.py 共用模式)
# ---------------------------------------------------------------------------
@dataclass
class _FakeQueryResult:
    items: list[Any]
    filters: list[Any] = field(default_factory=list)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for f in args:
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
            if not _eval_filter_conj(f, item):
                return False
        return True


def _eval_filter_conj(expr: Any, item: Any) -> bool:
    """评估 SQLAlchemy 表达式到 item 属性。支持:
    - BooleanClauseList (and_ / or_)
    - BinaryExpression (== / in_ / is_)
    - 单值 (fallback pass)
    """
    if hasattr(expr, "operator") and hasattr(expr, "clauses") and not hasattr(expr, "left"):
        op_name = getattr(expr.operator, "__name__", None) or str(expr.operator)
        clause_results = [_eval_filter_conj(c, item) for c in expr.clauses]
        if op_name == "and_":
            return all(clause_results)
        if op_name == "or_":
            return any(clause_results)
        return all(clause_results)
    return _eval_filter(expr, item)


def _eval_filter(expr: Any, item: Any) -> bool:
    """评估一个 SQLAlchemy BinaryExpression (== / in_ / is_) 到 item 属性。"""
    if not hasattr(expr, "left") or not hasattr(expr, "right"):
        return True
    op = getattr(expr, "operator", None)
    op_name = getattr(op, "__name__", None) or str(op)
    left_val = _resolve(expr.left, item)
    right_val = _resolve(expr.right, item)
    if op_name == "eq":
        return left_val == right_val
    if op_name == "ne":
        return left_val != right_val
    if op_name in ("in_", "in_op", "contains_op"):
        try:
            return left_val in right_val
        except TypeError:
            return False
    if op_name in ("is_", "is_op"):
        return left_val is right_val
    if op_name in ("is_not", "is_not_op"):
        return left_val is not right_val
    return True


def _resolve(col_or_value: Any, item: Any) -> Any:
    """从 item 上拿 col 对应的属性值; 否则直接返回值字面量。"""
    cls_name = type(col_or_value).__name__
    if cls_name in ("True_", "False_"):
        return cls_name == "True_"
    if cls_name == "Null":
        return None
    bind_value = getattr(col_or_value, "value", None)
    bind_type = getattr(col_or_value, "type", None)
    if bind_value is not None and bind_type is not None and not isinstance(col_or_value, (str, bytes)):
        return bind_value
    if hasattr(col_or_value, "key") and not isinstance(col_or_value, (str, bytes, int, float, bool, type(None))):
        try:
            return getattr(item, col_or_value.key, None)
        except Exception:
            return None
    if hasattr(col_or_value, "name") and not isinstance(col_or_value, (str, bytes, int, float, bool, type(None))):
        try:
            return getattr(item, col_or_value.name, None)
        except Exception:
            return None
    return col_or_value


@dataclass
class _FakeSession:
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
def _make_schema_snapshot(
    *,
    snapshot_id: int = 1,
    instance_id: int = 1,
    status: str = AiSchemaSnapshotStatus.SUCCESS,
    is_current: bool = True,
    expires_in_hours: Optional[float] = 24,
) -> AiSchemaSnapshot:
    now = datetime.now(tz=timezone.utc)
    snap = AiSchemaSnapshot(
        instance_id=instance_id,
        db_type_code="POSTGRESQL",
        database_name="<default>",
        schema_name="public",
        status=status,
        allowed_schemas=["app"],
        allowed_tables=["app.users", "app.orders"],
        allowed_columns={"app.users": ["id", "name"], "app.orders": ["id", "status"]},
        denied_columns=["password_hash"],
        is_current=is_current,
        snapshot_hash="d" * 64 if status == AiSchemaSnapshotStatus.SUCCESS else None,
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


def _make_object_metadata_snapshot(
    *,
    snapshot_id: int = 100,
    instance_id: int = 1,
    status: str = AiObjectMetadataSnapshotStatus.SUCCESS,
    is_current: bool = True,
    expires_in_hours: Optional[float] = 24,
    schema_name: str = "app",  # 匹配 schema snapshot allowed_schemas[0]
    db_type_code: str = "POSTGRESQL",
    database_name: str = "<default>",
    object_ddl_text: str = "CREATE TABLE t1 (id int);",
    object_ddl_sha256: str = "a" * 64,
    snapshot_hash: str = "b" * 64,
    table_count: int = 1,
    view_count: int = 1,
    index_count: int = 0,
    function_count: int = 0,
    total_object_count: int = 2,
) -> AiObjectMetadataSnapshot:
    now = datetime.now(tz=timezone.utc)
    snap = AiObjectMetadataSnapshot(
        instance_id=instance_id,
        db_type_code=db_type_code,
        database_name=database_name,
        schema_name=schema_name,
        status=status,
        is_current=is_current,
        collector_run_id=None,
        snapshot_hash=snapshot_hash,
        object_ddl_sha256=object_ddl_sha256,
        object_ddl_text=object_ddl_text,
        table_count=table_count,
        view_count=view_count,
        index_count=index_count,
        function_count=function_count,
        total_object_count=total_object_count,
        expires_at=(
            now + timedelta(hours=expires_in_hours)
            if expires_in_hours is not None and status == AiObjectMetadataSnapshotStatus.SUCCESS
            else None
        ),
        collected_at=now if status == AiObjectMetadataSnapshotStatus.SUCCESS else None,
        created_at=now,
    )
    snap.id = snapshot_id
    return snap


def _patch_db_type_inference(monkeypatch, db_type_code: Optional[str] = "POSTGRESQL") -> None:
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
# 1. 无 schema snapshot → object_metadata 字段不存在
# ---------------------------------------------------------------------------

def test_no_schema_snapshot_no_object_metadata_field(monkeypatch):
    """available=false → object_metadata 字段不在返回值中（C8 unavailable 形状保持稳定）"""
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    result = AiSchemaContextService.build_schema_context(db, instance_id=999)
    assert result["available"] is False
    assert result["reason"] == ContextUnavailableReason.NO_SNAPSHOT
    # F3 关键: unavailable 响应不增加 object_metadata 字段（避免破坏现有契约）
    assert "object_metadata" not in result


# ---------------------------------------------------------------------------
# 2. schema snapshot success + 无 object metadata → object_metadata=None
# ---------------------------------------------------------------------------

def test_schema_snapshot_success_no_object_metadata_returns_none(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    schema_snap = _make_schema_snapshot()
    db.add(schema_snap)
    # 不 seed object metadata snapshot
    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    assert result["available"] is True
    assert result["object_metadata"] is None


# ---------------------------------------------------------------------------
# 3. schema snapshot success + 已发布 object metadata → 注入 dict
# ---------------------------------------------------------------------------

def test_schema_snapshot_with_object_metadata_injects_dict(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    schema_snap = _make_schema_snapshot()
    db.add(schema_snap)
    obj_snap = _make_object_metadata_snapshot()
    db.add(obj_snap)

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    assert result["available"] is True
    assert isinstance(result["object_metadata"], dict)


# ---------------------------------------------------------------------------
# 4. object_metadata dict 必备键齐全
# ---------------------------------------------------------------------------

def test_object_metadata_dict_has_required_keys(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())
    db.add(_make_object_metadata_snapshot(snapshot_id=42))

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    obj = result["object_metadata"]
    assert obj is not None
    # 必备 8 键（C16-F3 §4.4 plan line 165）
    assert "snapshot_id" in obj
    assert "object_ddl_sha256" in obj
    assert "table_count" in obj
    assert "view_count" in obj
    assert "index_count" in obj
    assert "function_count" in obj
    assert "total_object_count" in obj
    assert "object_ddl_text_preview" in obj


# ---------------------------------------------------------------------------
# 5. sha256 与 AiObjectMetadataSnapshot.object_ddl_sha256 一致
# ---------------------------------------------------------------------------

def test_object_metadata_sha256_matches_snapshot(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())
    expected_sha = "deadbeef" * 8  # 64 hex chars
    db.add(_make_object_metadata_snapshot(
        snapshot_id=42, object_ddl_sha256=expected_sha,
    ))

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    assert result["object_metadata"]["snapshot_id"] == 42
    assert result["object_metadata"]["object_ddl_sha256"] == expected_sha


# ---------------------------------------------------------------------------
# 6. counts 数值与 snapshot 字段一致
# ---------------------------------------------------------------------------

def test_object_metadata_counts_match_snapshot(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())
    db.add(_make_object_metadata_snapshot(
        table_count=5, view_count=2, index_count=10, function_count=3,
        total_object_count=20,
    ))

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    obj = result["object_metadata"]
    assert obj["table_count"] == 5
    assert obj["view_count"] == 2
    assert obj["index_count"] == 10
    assert obj["function_count"] == 3
    assert obj["total_object_count"] == 20


# ---------------------------------------------------------------------------
# 7. object_ddl_text_preview 限 8000 字符注入（超过 → 截断到 8000）
# ---------------------------------------------------------------------------

def test_object_ddl_text_preview_truncated_to_8000_chars(monkeypatch):
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())
    big_ddl = "CREATE TABLE big_t (id int);\n" + ("--" + "x" * 100 + "\n") * 1000  # ~103KB
    db.add(_make_object_metadata_snapshot(object_ddl_text=big_ddl))

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    preview = result["object_metadata"]["object_ddl_text_preview"]
    assert len(preview) == 8000
    # 原文截断到 8000 字符（plan §4.4 line 168）
    assert preview == big_ddl[:8000]


# ---------------------------------------------------------------------------
# 8. 现有 schema_context 键未被破坏
# ---------------------------------------------------------------------------

def test_existing_schema_context_keys_intact(monkeypatch):
    """F3 不破坏 C10 schema_context 既有契约（plan §4.4 P0 修正）"""
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())
    db.add(_make_object_metadata_snapshot())

    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    # 既有 schema_context 键全部保留
    assert result["available"] is True
    assert "schema_context" in result and result["schema_context"]
    assert "schema_policy_hash" in result and result["schema_policy_hash"]
    assert "allowed_schemas" in result
    assert "allowed_tables" in result
    assert "allowed_columns" in result
    assert "denied_columns" in result
    assert "schema_snapshot_id" in result
    assert "snapshot_hash" in result
    assert "total_tables" in result
    assert "total_columns" in result
    # schema_policy_hash 仍是 64 hex
    assert len(result["schema_policy_hash"]) == 64


# ---------------------------------------------------------------------------
# 9. object_metadata lookup 抛异常 → 返回 None (try/except 兜底)
# ---------------------------------------------------------------------------

def test_object_metadata_lookup_exception_returns_none(monkeypatch):
    """AiObjectMetadataSnapshotService.get_published_object_metadata 抛异常 → object_metadata=None"""
    _patch_db_type_inference(monkeypatch, db_type_code="POSTGRESQL")
    db = _FakeSession()
    db.add(_make_schema_snapshot())

    # Patch get_published_object_metadata 抛异常
    from app.services.ai import ai_object_metadata_snapshot_service as obj_svc_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated lookup failure")

    monkeypatch.setattr(
        obj_svc_mod.AiObjectMetadataSnapshotService,
        "get_published_object_metadata",
        staticmethod(_raise),
    )

    # 不应抛异常 — try/except 兜底
    result = AiSchemaContextService.build_schema_context(db, instance_id=1)
    assert result["available"] is True
    assert result["object_metadata"] is None