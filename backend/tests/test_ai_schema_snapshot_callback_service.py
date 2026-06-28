"""Phase 3.6B0 C9 — AiSchemaSnapshotCallbackService 单元测试.

覆盖 (plan §13 Schema Snapshot 矩阵的 callback 部分):

  1.  non-ai_schema business_domain 跳过
  2.  非 DB_SCHEMA_METADATA_COLLECTION check_code 跳过
  3.  happy path success:
        - 新建 snapshot (status=success / is_current=true)
        - allowed_schemas/tables/columns 聚合正确
        - snapshot_hash 64 hex, 内容相同 → hash 相同 (deterministic)
        - expires_at = now + 24h
        - total_tables / total_columns 设置
  4.  truncated=true → status=failed, error_code=RESULT_TRUNCATED
  5.  空 rows + status=verified → status=failed, error_code=NO_ROWS
  6.  item_status=failed → status=failed, error_code 来自 raw_result / 派生
  7.  幂等 upsert: 同 (instance_id, db, collector_run_id) 已存在 → 更新非新建
  8.  两阶段发布: 已有 is_current=true → 新 success 后 → 旧 is_current=false
  9.  failed snapshot 不允许 is_current=true, 不带 expires_at / snapshot_hash
  10. snapshot_hash SHA-256 一致性 (相同 rows + columns → 相同 hash)
  11. db_type_code fallback POSTGRESQL / database_name fallback '<default>'
  12. mixed batch: 仅 ai_schema 落库
  13. asset_id<=0 跳过

策略:
- 自制 FakeSession + InMemoryQueryStore 模拟 SQLAlchemy 行为
- 不连真实 DB (与 test_ai_schema_metadata_builder.py / test_pg_schema_columns_sql.py 策略一致)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai.ai_schema_snapshot_callback_service import (
    _aggregate_whitelist,
    _compute_snapshot_hash,
    _derive_error_code,
    save_snapshots,
)


# ---------------------------------------------------------------------------
# Fake ORM primitives
# ---------------------------------------------------------------------------

@dataclass
class _FakeSession:
    """Minimal in-memory replacement for ``sqlalchemy.orm.Session``.

    模拟范围（够覆盖 C9 callback 测试）：
    - ``add`` + ``flush`` → 自动分配 autoincrement id
    - ``query`` 链式 filter / with_for_update / order_by / first / all
    - ``execute`` 对 update() 语句应用 where + values 到 store
    """

    store: dict[str, list[Any]] = field(default_factory=dict)
    executed: list[Any] = field(default_factory=list)
    flushed: int = 0
    committed: bool = False
    _next_id: dict[str, int] = field(default_factory=dict)

    def _alloc_id(self, obj: Any) -> int:
        cls_name = type(obj).__name__
        self._next_id[cls_name] = self._next_id.get(cls_name, 1000) + 1
        return self._next_id[cls_name]

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def flush(self) -> None:
        self.flushed += 1
        # Mimic SQLAlchemy's autoincrement id population
        for cls_name, items in self.store.items():
            for item in items:
                cur = getattr(item, "id", None)
                if cur is None:
                    new_id = self._alloc_id(item)
                    try:
                        item.id = new_id
                    except Exception:
                        try:
                            object.__setattr__(item, "id", new_id)
                        except Exception:
                            pass

    def commit(self) -> None:
        self.committed = True

    def execute(self, statement: Any) -> "_FakeExecuteResult":
        self.executed.append(statement)
        try:
            self._apply_update(statement)
        except Exception:
            pass
        return _FakeExecuteResult(rowcount=1)

    def _apply_update(self, statement: Any) -> None:
        """对 ``update(AiSchemaSnapshot).where(...).values(...)`` 做最小集模拟。

        仅处理 ``AiSchemaSnapshot`` 这张表，且仅当 ``values`` 含 ``is_current``
        时落库（覆盖 callback C9 两阶段发布场景）。
        """
        if not hasattr(statement, "_values"):
            return
        values = statement._values
        if values is None:
            return
        # immutabledict: keys are Column objects, values are BindParameter
        target_value: Any = None
        try:
            items_iter = values.items()
        except AttributeError:
            return
        for col_obj, val in items_iter:
            key = getattr(col_obj, "key", None)
            if key == "is_current":
                # BindParameter has .value
                target_value = getattr(val, "value", val)
                break
        if target_value is None:
            return
        where = getattr(statement, "whereclause", None)
        if where is None:
            where = getattr(statement, "_where_criteria", None)
        for items in self.store.values():
            for item in items:
                if where is not None and not _eval_filter_conj(where, item):
                    continue
                setattr(item, "is_current", target_value)

    def query(self, model: Any) -> "_FakeQueryResult":
        cls_name = model.__name__
        items = list(self.store.get(cls_name, []))
        return _FakeQueryResult(items=items)


@dataclass
class _FakeQueryResult:
    """Supports .filter(...).with_for_update().first() / .order_by(...).first() chains."""

    items: list[Any]
    filters: list[Any] = field(default_factory=list)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new = _FakeQueryResult(items=list(self.items), filters=list(self.filters))
        for a in args:
            new.filters.append(a)
        return new

    def with_for_update(self) -> "_FakeQueryResult":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        return self

    def _matches(self, item: Any) -> bool:
        return all(_eval_filter_conj(f, item) for f in self.filters)

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

    def all(self) -> list[Any]:
        return [item for item in self.items if self._matches(item)]


def _eval_filter_conj(expr: Any, item: Any) -> bool:
    """评估 SQLAlchemy 表达式到 item 属性。支持:
    - BooleanClauseList (and_ / or_)
    - BinaryExpression (== / in_ / is_)
    - 单值 (fallback pass)
    """
    # BooleanClauseList: has .operator and .clauses
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
    if op_name in ("in_", "in_op", "contains_op"):  # ColumnOperators.in_
        try:
            return left_val in right_val
        except TypeError:
            return False
    if op_name in ("is_", "is_op"):
        return left_val is right_val
    if op_name in ("is_not", "is_not_op"):
        return left_val is not right_val
    # 未知 operator: 默认通过,避免误伤测试
    return True


def _resolve(col_or_value: Any, item: Any) -> Any:
    """从 item 上拿 col 对应的属性值; 否则直接返回值字面量。

    处理顺序（避免误判）:
    1. SQLAlchemy ``True_()`` / ``False_()`` / ``Null()`` 单例 → 取 Python bool
    2. SQLAlchemy BindParameter（如 ``Column == 100`` 右侧）→ 取 ``.value``
    3. SQLAlchemy Column 引用 → 取 ``item.<key>``
    4. Python 字面量 → 原样返回
    """
    cls_name = type(col_or_value).__name__
    if cls_name in ("True_", "False_"):
        return cls_name == "True_"
    if cls_name == "Null":
        return None
    # BindParameter (from Column == literal) — check first because BindParameter
    # also has .key (the bind name) which would mislead _resolve into looking up
    # item.<bind_name> which doesn't exist.
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


class _FakeExecuteResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


def _make_dbtype(*, type_code: str = "postgresql") -> SimpleNamespace:
    return SimpleNamespace(id=1, type_code=type_code)


def _make_instance(*, instance_id: int = 100, db_type_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=instance_id, db_type_id=db_type_id, extra_attrs={})


def _make_callback_item(
    *,
    asset_id: int = 100,
    item_key: str = "ai_schema::100::pg-meta-01",
    item_status: str = "verified",
    business_domain: str = "ai_schema",
    check_code: str = "DB_SCHEMA_METADATA_COLLECTION",
    message: str = "ok",
    rows: Optional[list[dict[str, Any]]] = None,
    columns: Optional[list[str]] = None,
    truncated: bool = False,
    total_rows: int = 0,
    returned_rows: int = 0,
    error_code: str = "",
    sql_hash: str = "abc123",
    source: str = "dbops.ai.sql_templates.postgresql.pg_schema_columns",
    phase: str = "3.6B0",
) -> SimpleNamespace:
    if rows is None:
        rows = [
            {"table_schema": "public", "table_name": "t1", "column_name": "id", "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
            {"table_schema": "public", "table_name": "t1", "column_name": "name", "data_type": "varchar", "is_nullable": "YES", "ordinal_position": 2},
            {"table_schema": "app", "table_name": "users", "column_name": "uid", "data_type": "bigint", "is_nullable": "NO", "ordinal_position": 1},
        ]
    if columns is None:
        columns = ["table_schema", "table_name", "column_name", "data_type", "is_nullable", "ordinal_position"]
    total_rows = max(total_rows, len(rows))
    if not truncated:
        returned_rows = max(returned_rows, len(rows))

    return SimpleNamespace(
        item_key=item_key,
        check_code=check_code,
        business_domain=business_domain,
        asset_id=asset_id,
        target_host="10.0.0.10",
        target_port=5432,
        status=item_status,
        message=message,
        raw_result={
            "columns": columns,
            "rows": rows,
            "result_status": "ok" if item_status == "verified" else "error",
            "error_code": error_code,
            "connector": "postgresql",
            "duration_ms": 120,
            "sql_hash": sql_hash,
            "total_rows": total_rows,
            "returned_rows": returned_rows,
            "truncated": truncated,
            "max_bytes": 10485760,
            "source": source,
            "phase": phase,
            "rc": 0,
            "stderr": "",
        },
    )


def _make_run(*, run_id: str = "RUN-20260628-001", run_db_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(id=run_db_id, run_id=run_id)


def _seed_instance(db: _FakeSession, *, instance_id: int = 100, type_code: str = "postgresql") -> None:
    db.store.setdefault("DbInstance", []).append(_make_instance(instance_id=instance_id))
    db.store.setdefault("DbType", []).append(_make_dbtype(type_code=type_code))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_non_ai_schema_business_domain_skipped() -> None:
    db = _FakeSession()
    run = _make_run()
    cb = _make_callback_item(business_domain="inspection")
    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 0
    assert "AiSchemaSnapshot" not in db.store


def test_non_metadata_check_code_skipped() -> None:
    db = _FakeSession()
    run = _make_run()
    cb = _make_callback_item(check_code="DB_BASIC")
    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 0
    assert "AiSchemaSnapshot" not in db.store


def test_happy_path_success_creates_snapshot() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="verified", truncated=False)
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snaps = db.store["AiSchemaSnapshot"]
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.status == "success"
    assert snap.is_current is True
    assert snap.snapshot_hash is not None
    assert len(snap.snapshot_hash) == 64
    assert all(c in "0123456789abcdef" for c in snap.snapshot_hash)
    assert snap.total_tables == 2  # public.t1, app.users
    assert snap.total_columns == 3
    assert snap.allowed_schemas == ["app", "public"]
    assert snap.allowed_tables == ["app.users", "public.t1"]
    assert snap.allowed_columns == {
        "public.t1": ["id", "name"],
        "app.users": ["uid"],
    }
    assert snap.expires_at is not None
    assert snap.expires_at > snap.collected_at
    assert (snap.expires_at - snap.collected_at) <= timedelta(hours=25)
    assert snap.error_code is None
    assert snap.error_message is None
    assert snap.collector_run_id == 42


def test_truncated_true_yields_failed_with_result_truncated() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="verified", truncated=True, total_rows=20000, returned_rows=15000)
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.status == "failed"
    assert snap.error_code == "RESULT_TRUNCATED"
    assert "truncated=true" in snap.error_message
    assert snap.snapshot_hash is None
    assert snap.expires_at is None
    assert snap.collected_at is None
    assert snap.is_current is False


def test_empty_rows_with_verified_status_yields_no_rows_failed() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="verified", rows=[], total_rows=0, returned_rows=0)
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.status == "failed"
    assert snap.error_code == "NO_ROWS"
    assert snap.is_current is False
    assert snap.snapshot_hash is None


def test_failed_item_status_with_raw_error_code() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="failed", error_code="CONN_REFUSED", message="connection refused")
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.status == "failed"
    assert snap.error_code == "CONN_REFUSED"
    assert snap.error_message == "connection refused"


def test_failed_item_status_without_raw_error_code_derives_code() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="missing", error_code="", message="")
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.status == "failed"
    assert snap.error_code == "INSTANCE_UNREACHABLE"


def test_idempotent_upsert_same_run_no_duplicate() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb1 = _make_callback_item(item_status="verified")
    cb2 = _make_callback_item(item_status="verified")  # same run + asset + db
    save_snapshots(db, run=run, callback_items=[cb1])
    save_snapshots(db, run=run, callback_items=[cb2])

    snaps = db.store["AiSchemaSnapshot"]
    assert len(snaps) == 1, "snapshot 不应被重复落库"
    assert snaps[0].status == "success"


def test_two_phase_publish_old_is_current_set_to_false() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run(run_db_id=42)

    # First run: success → is_current=True
    cb1 = _make_callback_item(item_key="k1")
    save_snapshots(db, run=run, callback_items=[cb1])
    first = db.store["AiSchemaSnapshot"][0]
    assert first.is_current is True
    first_id = first.id

    # Second run: success → 应触发 UPDATE other rows is_current=False
    run2 = _make_run(run_id="RUN-20260628-002", run_db_id=43)
    cb2 = _make_callback_item(item_key="k2")
    save_snapshots(db, run=run2, callback_items=[cb2])

    snaps = db.store["AiSchemaSnapshot"]
    assert len(snaps) == 2
    current = [s for s in snaps if s.is_current]
    assert len(current) == 1
    assert current[0].id != first_id
    # 旧 current 已切 false
    first_after = next(s for s in snaps if s.id == first_id)
    assert first_after.is_current is False
    # execute 应被调用 (两阶段发布 UPDATE)
    assert db.executed, "expected at least one execute() for two-phase publish"


def test_failed_snapshot_does_not_publish_is_current() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="failed", error_code="X", message="x")
    save_snapshots(db, run=run, callback_items=[cb])

    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.is_current is False
    assert snap.expires_at is None
    assert snap.snapshot_hash is None
    assert snap.total_tables is None
    assert snap.total_columns is None


def test_snapshot_hash_is_sha256_64_hex_and_deterministic() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="verified")
    save_snapshots(db, run=run, callback_items=[cb])
    hash1 = db.store["AiSchemaSnapshot"][0].snapshot_hash

    cb2 = _make_callback_item(item_status="verified")
    save_snapshots(db, run=run, callback_items=[cb2])
    hash2 = db.store["AiSchemaSnapshot"][0].snapshot_hash

    assert hash1 == hash2
    assert len(hash1) == 64
    # SHA-256 sanity: 直接算一遍, 应一致
    expected = hashlib.sha256(
        json.dumps(
            {"columns": cb.raw_result["columns"], "rows": cb.raw_result["rows"]},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    assert hash1 == expected


def test_db_type_code_falls_back_to_postgresql_when_instance_missing() -> None:
    db = _FakeSession()  # no seeded instance / dbtype
    run = _make_run()

    cb = _make_callback_item(asset_id=999, item_status="failed", error_code="X", message="x")
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.db_type_code == "POSTGRESQL"


def test_database_name_defaults_to_default_placeholder() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(item_status="failed", error_code="X", message="x")
    save_snapshots(db, run=run, callback_items=[cb])

    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.database_name == "<default>"


def test_mixed_batch_only_ai_schema_items_saved() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    ai = _make_callback_item(item_status="verified", item_key="ai")
    insp = _make_callback_item(business_domain="inspection", item_key="insp", item_status="verified")
    bak = _make_callback_item(business_domain="backup_status", item_key="bak", item_status="verified")

    written = save_snapshots(db, run=run, callback_items=[ai, insp, bak])

    assert written == 1
    snaps = db.store["AiSchemaSnapshot"]
    assert len(snaps) == 1
    assert snaps[0].status == "success"


def test_asset_id_zero_is_skipped() -> None:
    db = _FakeSession()
    _seed_instance(db)
    run = _make_run()

    cb = _make_callback_item(asset_id=0, item_status="verified")
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 0
    assert "AiSchemaSnapshot" not in db.store


def test_aggregate_whitelist_groups_correctly() -> None:
    rows = [
        {"table_schema": "public", "table_name": "t1", "column_name": "id"},
        {"table_schema": "public", "table_name": "t1", "column_name": "name"},
        {"table_schema": "public", "table_name": "t2", "column_name": "id"},
        {"table_schema": "app", "table_name": "users", "column_name": "uid"},
        {"table_schema": "app", "table_name": "users", "column_name": "uid"},  # dup col
    ]
    schemas, tables, cols = _aggregate_whitelist(rows)
    assert schemas == ["app", "public"]
    assert tables == ["app.users", "public.t1", "public.t2"]
    assert cols == {
        "public.t1": ["id", "name"],
        "public.t2": ["id"],
        "app.users": ["uid"],
    }


def test_compute_snapshot_hash_stable_across_dict_order() -> None:
    columns = ["a", "b"]
    rows1 = [{"b": 2, "a": 1}, {"a": 3, "b": 4}]
    rows2 = [{"a": 1, "b": 2}, {"b": 4, "a": 3}]
    h1 = _compute_snapshot_hash(rows1, columns)
    h2 = _compute_snapshot_hash(rows2, columns)
    assert h1 == h2


def test_derive_error_code() -> None:
    assert _derive_error_code("skipped") == "COLLECTION_SKIPPED"
    assert _derive_error_code("missing") == "INSTANCE_UNREACHABLE"
    assert _derive_error_code("drifted") == "ASSET_DRIFTED"
    assert _derive_error_code("") == "COLLECTION_FAILED"
    assert _derive_error_code("failed") == "COLLECTION_FAILED"


def test_run_with_no_id_still_writes_with_null_collector_run_id() -> None:
    db = _FakeSession()
    _seed_instance(db)

    run = SimpleNamespace(id=None, run_id="RUN-NOID")
    cb = _make_callback_item(item_status="failed", error_code="X", message="x")
    written = save_snapshots(db, run=run, callback_items=[cb])

    assert written == 1
    snap = db.store["AiSchemaSnapshot"][0]
    assert snap.collector_run_id is None
