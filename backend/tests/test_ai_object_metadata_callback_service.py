"""
Phase 3.6B0 C16-F3 — AiObjectMetadataSnapshotCallbackService 单元测试

覆盖 (plan §13 Object Metadata Snapshot 矩阵的 callback 部分):

  1.  非 ai_object_metadata business_domain 跳过
  2.  非 DB_OBJECT_METADATA check_code 跳过 (defensive)
  3.  happy path success: 新建 snapshot (status=success / is_current=true)
  4.  asset_id<=0 跳过
  5.  空 rows + status=verified → status=failed, error_code=NO_OBJECTS
  6.  truncated=true → status=failed, error_code=RESULT_TRUNCATED
  7.  item_status=failed → status=failed, error_code 来自 raw_result / 派生
  8.  幂等 upsert: 同 (instance, db, schema, collector_run_id) 已存在 → 更新非新建
  9.  两阶段发布: 已有 is_current=true → 新 success 后 → 旧 is_current=false
 10.  failed snapshot 不允许 is_current=true
 11.  SHA-256 一致性 (相同 rows + columns → 相同 hash)
 12.  1MB 截断: DDL 超过 max_bytes → 截断并标 error_code=TRUNCATED
 13.  5 类对象 DDL 拼接 (table/view/index/function/constraint)
 14.  防御: 单条 item 抛异常不影响主事务

策略:
- 自制 FakeSession + InMemoryQueryStore 模拟 SQLAlchemy 行为
- 不连真实 DB (与 C9 callback 测试策略一致)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import AiObjectMetadataSnapshotStatus
from app.services.ai.ai_object_metadata_callback_service import (
    _aggregate_ddl,
    _compute_snapshot_hash,
    _derive_error_code,
    _resolve_db_type_code,
    _resolve_database_name,
    _resolve_schema_name_from_rows,
    save_snapshots,
)


# ---------------------------------------------------------------------------
# Fake ORM primitives (镜像 C9 schema callback test)
# ---------------------------------------------------------------------------

@dataclass
class _FakeSession:
    """Minimal in-memory replacement for ``sqlalchemy.orm.Session``.

    模拟范围（够覆盖 C16-F3 callback 测试）：
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
        """对 ``update(AiObjectMetadataSnapshot).where(...).values(...)`` 做最小集模拟。

        仅处理 ``AiObjectMetadataSnapshot`` 这张表，且仅当 ``values`` 含 ``is_current``
        时落库（覆盖 callback 两阶段发布场景）。
        """
        if not hasattr(statement, "_values"):
            return
        values = statement._values
        if values is None:
            return
        target_value: Any = None
        try:
            items_iter = values.items()
        except AttributeError:
            return
        for col_obj, val in items_iter:
            key = getattr(col_obj, "key", None)
            if key == "is_current":
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


class _FakeExecuteResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


def _make_dbtype(*, type_code: str = "postgresql") -> SimpleNamespace:
    return SimpleNamespace(id=1, type_code=type_code)


def _make_instance(
    *, instance_id: int = 100, db_type_id: int = 1,
    extra_attrs: Optional[dict[str, Any]] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=instance_id,
        db_type_id=db_type_id,
        extra_attrs=extra_attrs if extra_attrs is not None else {},
    )


def _make_callback_item(
    *,
    asset_id: int = 100,
    item_key: str = "db_instance:100:DB_OBJECT_METADATA:10.0.0.10:5432",
    item_status: str = "verified",
    business_domain: str = "ai_object_metadata",
    check_code: str = "DB_OBJECT_METADATA",
    message: str = "ok",
    rows: Optional[list[dict[str, Any]]] = None,
    columns: Optional[list[str]] = None,
    truncated: bool = False,
    total_rows: int = 0,
    returned_rows: int = 0,
    error_code: str = "",
    sql_hash: str = "abc123",
    source: str = "dbops.ai.sql_templates.postgresql.pg_object_metadata",
    phase: str = "3.6B0.F3",
    max_bytes: int = 1048576,
) -> SimpleNamespace:
    if rows is None:
        rows = [
            {"object_type": "table", "schema_name": "public", "object_name": "t1",
             "ddl_text": "CREATE TABLE t1 (id int);", "comment": ""},
            {"object_type": "view", "schema_name": "public", "object_name": "v1",
             "ddl_text": "CREATE VIEW v1 AS SELECT * FROM t1;", "comment": ""},
            {"object_type": "primary_key", "schema_name": "public", "object_name": "t1_pkey",
             "ddl_text": "PRIMARY KEY (id)", "comment": ""},
        ]
    if columns is None:
        columns = ["object_type", "schema_name", "object_name", "ddl_text", "comment"]
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
            "max_bytes": max_bytes,
            "source": source,
            "phase": phase,
            "rc": 0,
            "stderr": "",
        },
    )


def _make_run(*, run_id: str = "RUN-20260706-001", run_db_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(id=run_db_id, run_id=run_id)


def _seed_instance(
    db: _FakeSession, *, instance_id: int = 100, type_code: str = "postgresql",
    extra_attrs: Optional[dict[str, Any]] = None,
) -> None:
    db.store.setdefault("DbInstance", []).append(_make_instance(
        instance_id=instance_id, extra_attrs=extra_attrs,
    ))
    db.store.setdefault("DbType", []).append(_make_dbtype(type_code=type_code))


# ---------------------------------------------------------------------------
# 1. business_domain / check_code guards
# ---------------------------------------------------------------------------

def test_non_ai_object_metadata_business_domain_skipped():
    db = _FakeSession()
    run = _make_run()
    cb = _make_callback_item(business_domain="inspection")
    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 0
    assert "AiObjectMetadataSnapshot" not in db.store


def test_non_db_object_metadata_check_code_skipped():
    """defensive: ai_object_metadata business_domain 但 check_code 错配 → 跳过"""
    db = _FakeSession()
    run = _make_run()
    cb = _make_callback_item(
        business_domain="ai_object_metadata",
        check_code="DB_SCHEMA_METADATA_COLLECTION",
    )
    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 0
    assert "AiObjectMetadataSnapshot" not in db.store


def test_asset_id_zero_skipped():
    db = _FakeSession()
    run = _make_run()
    cb = _make_callback_item(asset_id=0)
    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 0


# ---------------------------------------------------------------------------
# 2. Happy path success
# ---------------------------------------------------------------------------

def test_happy_path_success_persists_snapshot():
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item()

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snaps = db.store.get("AiObjectMetadataSnapshot", [])
    assert len(snaps) == 1
    snap = snaps[0]

    # 状态 + 计数
    assert snap.status == AiObjectMetadataSnapshotStatus.SUCCESS
    assert snap.is_current is True
    # primary_key 归并到 constraint → table=1, view=1, constraint=1, total=3
    assert snap.table_count == 1
    assert snap.view_count == 1  # view(1) + materialized_view(0)
    assert snap.index_count == 0
    assert snap.function_count == 0  # function(0) + procedure(0)
    assert snap.total_object_count == 3
    # DB 元数据
    assert snap.db_type_code == "POSTGRESQL"
    assert snap.database_name == "<default>"  # F3 default fallback
    assert snap.schema_name == "public"  # 从 rows[0].schema_name 解析
    assert snap.collector_run_id == 42
    # SHA-256 长度
    assert snap.object_ddl_sha256 and len(snap.object_ddl_sha256) == 64
    assert snap.snapshot_hash and len(snap.snapshot_hash) == 64
    # expires_at 设置
    assert snap.expires_at is not None
    # error_code: success 无错
    assert snap.error_code is None
    assert snap.error_message is None


# ---------------------------------------------------------------------------
# 3. Failed paths
# ---------------------------------------------------------------------------

def test_empty_rows_success_status_marks_failed_no_objects():
    """status=verified 但 0 rows → failed, error_code=NO_OBJECTS"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item(rows=[])

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snap = db.store["AiObjectMetadataSnapshot"][0]
    assert snap.status == AiObjectMetadataSnapshotStatus.FAILED
    assert snap.error_code == "NO_OBJECTS"
    assert "0 rows" in snap.error_message
    assert snap.is_current is False
    assert snap.object_ddl_text is None
    assert snap.expires_at is None


def test_truncated_true_marks_failed_result_truncated():
    """collector 报 truncated=true → failed, error_code=RESULT_TRUNCATED"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item(truncated=True, total_rows=50000, returned_rows=20000)

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snap = db.store["AiObjectMetadataSnapshot"][0]
    assert snap.status == AiObjectMetadataSnapshotStatus.FAILED
    assert snap.error_code == "RESULT_TRUNCATED"
    assert "truncated=true" in snap.error_message
    assert snap.is_current is False


def test_item_status_failed_marks_failed():
    """item_status=failed → status=failed, error_code 派生"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item(
        item_status="failed", message="connection refused",
        error_code="DB_CONNECTION_REFUSED",
    )

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snap = db.store["AiObjectMetadataSnapshot"][0]
    assert snap.status == AiObjectMetadataSnapshotStatus.FAILED
    assert snap.error_code == "DB_CONNECTION_REFUSED"
    assert snap.is_current is False


def test_item_status_failed_without_error_code_uses_derived():
    """item_status=failed 但 raw_result.error_code 缺失 → _derive_error_code 派生"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item(item_status="failed", error_code="")

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snap = db.store["AiObjectMetadataSnapshot"][0]
    assert snap.status == AiObjectMetadataSnapshotStatus.FAILED
    # failed + 空 error_code → _derive_error_code("failed") = "COLLECTION_FAILED"
    assert snap.error_code == "COLLECTION_FAILED"


# ---------------------------------------------------------------------------
# 4. Upsert + 两阶段发布
# ---------------------------------------------------------------------------

def test_idempotent_upsert_same_run():
    """同 (instance, db, schema, collector_run_id) 已存在 → 更新非新建"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    cb = _make_callback_item()

    # 第一次
    save_snapshots(db, run=run, callback_items=[cb])
    # 第二次同 callback
    save_snapshots(db, run=run, callback_items=[cb])

    snaps = db.store["AiObjectMetadataSnapshot"]
    assert len(snaps) == 1  # 幂等: 仍只 1 行


def test_two_phase_publish_demotes_previous_current():
    """已有 is_current=true 的成功 snapshot → 新 success 后 → 旧 is_current=false"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run1 = _make_run(run_db_id=1)
    run2 = _make_run(run_db_id=2)
    cb1 = _make_callback_item(item_key="db_instance:100:DB_OBJECT_METADATA:10.0.0.10:5432:v1")
    cb2 = _make_callback_item(item_key="db_instance:100:DB_OBJECT_METADATA:10.0.0.10:5432:v2")

    # 第一轮采集
    save_snapshots(db, run=run1, callback_items=[cb1])
    first = db.store["AiObjectMetadataSnapshot"][0]
    assert first.is_current is True

    # 第二轮采集（同 instance + db + schema + 不同 collector_run_id）
    save_snapshots(db, run=run2, callback_items=[cb2])

    snaps = db.store["AiObjectMetadataSnapshot"]
    assert len(snaps) == 2
    # 旧 is_current=false
    old = next(s for s in snaps if s.collector_run_id == 1)
    new = next(s for s in snaps if s.collector_run_id == 2)
    assert old.is_current is False
    assert new.is_current is True


def test_failed_snapshot_not_promoted_to_current():
    """failed snapshot 不会成为 is_current=true，旧 success 仍生效"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run1 = _make_run(run_db_id=1)
    run2 = _make_run(run_db_id=2)
    cb_ok = _make_callback_item(item_key="db_instance:100:DB_OBJECT_METADATA:10.0.0.10:5432:ok")
    cb_fail = _make_callback_item(
        item_key="db_instance:100:DB_OBJECT_METADATA:10.0.0.10:5432:fail",
        item_status="failed", error_code="DB_TIMEOUT",
    )

    save_snapshots(db, run=run1, callback_items=[cb_ok])
    save_snapshots(db, run=run2, callback_items=[cb_fail])

    snaps = db.store["AiObjectMetadataSnapshot"]
    assert len(snaps) == 2
    ok = next(s for s in snaps if s.collector_run_id == 1)
    fail = next(s for s in snaps if s.collector_run_id == 2)
    assert ok.is_current is True  # 旧 success 仍 current
    assert fail.is_current is False  # failed 不 promote
    assert fail.expires_at is None


# ---------------------------------------------------------------------------
# 5. SHA-256 + 1MB 截断
# ---------------------------------------------------------------------------

def test_snapshot_hash_deterministic():
    """相同 rows + columns → 相同 hash"""
    cols = ["object_type", "schema_name", "object_name", "ddl_text"]
    rows = [{"object_type": "table", "schema_name": "public", "object_name": "t1", "ddl_text": "CREATE TABLE t1 (id int);"}]
    h1 = _compute_snapshot_hash(rows, cols)
    h2 = _compute_snapshot_hash(list(rows), list(cols))
    assert h1 == h2
    assert len(h1) == 64
    # 与手算 SHA-256 一致
    canonical = {"columns": list(cols), "rows": list(rows)}
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    assert h1 == hashlib.sha256(blob.encode("utf-8")).hexdigest()


def test_1mb_truncation_marks_truncated():
    """DDL 超过 max_bytes → 截断并标 error_code=TRUNCATED (但不 failed)"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()
    # 故意造一个超大 DDL 单行
    big_ddl = "CREATE TABLE big_t (id int, payload text);\n" + ("--" + "x" * 2000 + "\n") * 1000
    cb = _make_callback_item(
        rows=[{"object_type": "table", "schema_name": "public", "object_name": "big_t",
               "ddl_text": big_ddl, "comment": ""}],
        max_bytes=2048,  # 2KB cap 强制截断
    )

    written = save_snapshots(db, run=run, callback_items=[cb])
    assert written == 1
    snap = db.store["AiObjectMetadataSnapshot"][0]
    # status 仍 success（截断本身不破坏内容），但 error_code=TRUNCATED
    assert snap.status == AiObjectMetadataSnapshotStatus.SUCCESS
    assert snap.error_code == "TRUNCATED"
    assert "truncated to" in snap.error_message
    # DDL 字节数不超过 max_bytes
    assert len((snap.object_ddl_text or "").encode("utf-8")) <= 2048


# ---------------------------------------------------------------------------
# 6. DDL 拼接 + 5 类对象
# ---------------------------------------------------------------------------

def test_aggregate_ddl_5_object_types():
    """5 类对象 DDL 按 _DDL_SECTION_ORDER 拼接"""
    rows = [
        {"object_type": "table", "schema_name": "public", "object_name": "t1",
         "ddl_text": "CREATE TABLE t1 (id int);", "comment": ""},
        {"object_type": "view", "schema_name": "public", "object_name": "v1",
         "ddl_text": "CREATE VIEW v1 AS SELECT * FROM t1;", "comment": ""},
        {"object_type": "index", "schema_name": "public", "object_name": "i1",
         "ddl_text": "CREATE INDEX i1 ON t1 (id);", "comment": ""},
        {"object_type": "function", "schema_name": "public", "object_name": "f1",
         "ddl_text": "CREATE FUNCTION f1() RETURNS int AS $$ SELECT 1 $$ LANGUAGE sql;", "comment": ""},
        {"object_type": "primary_key", "schema_name": "public", "object_name": "t1_pkey",
         "ddl_text": "PRIMARY KEY (id)", "comment": ""},
    ]
    ddl, counts = _aggregate_ddl(rows, max_bytes=1048576)
    # 5 段 header
    assert "-- table --" in ddl
    assert "-- view --" in ddl
    assert "-- index --" in ddl
    assert "-- function --" in ddl
    assert "-- constraint --" in ddl
    # DDL 内容拼接
    assert "CREATE TABLE t1" in ddl
    assert "CREATE VIEW v1" in ddl
    assert "CREATE INDEX i1" in ddl
    assert "CREATE FUNCTION f1" in ddl
    assert "PRIMARY KEY (id)" in ddl
    # counts: constraint 段包含 primary_key 归并
    assert counts["table"] == 1
    assert counts["view"] == 1
    assert counts["index"] == 1
    assert counts["function"] == 1
    assert counts["constraint"] == 1


def test_aggregate_ddl_constraint_subtypes_merged():
    """constraint 4 子类（PK/UK/FK/CHECK）合并到 constraint 段"""
    rows = [
        {"object_type": "primary_key", "schema_name": "public", "object_name": "pk1",
         "ddl_text": "PRIMARY KEY (id)", "comment": ""},
        {"object_type": "unique_constraint", "schema_name": "public", "object_name": "uk1",
         "ddl_text": "UNIQUE (id)", "comment": ""},
        {"object_type": "foreign_key", "schema_name": "public", "object_name": "fk1",
         "ddl_text": "FOREIGN KEY (id) REFERENCES t1(id)", "comment": ""},
        {"object_type": "check_constraint", "schema_name": "public", "object_name": "ck1",
         "ddl_text": "CHECK (id > 0)", "comment": ""},
    ]
    ddl, counts = _aggregate_ddl(rows, max_bytes=1048576)
    assert "-- constraint --" in ddl
    # 4 子类都合并到 constraint 段
    assert counts["constraint"] == 4
    # 4 段内容都在
    assert "PRIMARY KEY" in ddl
    assert "UNIQUE" in ddl
    assert "FOREIGN KEY" in ddl
    assert "CHECK" in ddl


# ---------------------------------------------------------------------------
# 7. 防御：单条 item 异常不影响主事务
# ---------------------------------------------------------------------------

def test_single_item_exception_does_not_break_loop():
    """cb 抛异常 → save_snapshots 不抛；返回 written 计数已成功的"""
    db = _FakeSession()
    _seed_instance(db, instance_id=100)
    run = _make_run()

    # 构造一个会让 _save_one 抛异常的 cb: asset_id 非 int 触发 ValueError
    cb_bad = SimpleNamespace(
        item_key="bad",
        check_code="DB_OBJECT_METADATA",
        business_domain="ai_object_metadata",
        asset_id=None,
        raw_result={"rows": []},
    )
    cb_good = _make_callback_item(item_key="good")

    # _save_one 处理 cb_bad 时 asset_id <= 0 → ValueError，被 try/except 吞掉
    written = save_snapshots(db, run=run, callback_items=[cb_bad, cb_good])
    assert written == 1  # 仅 cb_good 成功
    assert len(db.store["AiObjectMetadataSnapshot"]) == 1


# ---------------------------------------------------------------------------
# 8. Helpers: resolve_db_type_code / resolve_database_name / _derive_error_code
# ---------------------------------------------------------------------------

def test_resolve_db_type_code_fallback_postgresql():
    db = _FakeSession()
    # 无 DbInstance → fallback POSTGRESQL
    code = _resolve_db_type_code(db, instance_id=999)
    assert code == "POSTGRESQL"


def test_resolve_database_name_default_placeholder():
    db = _FakeSession()
    # 无 extra_attrs → '<default>'
    _seed_instance(db, instance_id=100)
    name = _resolve_database_name(db, instance_id=100)
    assert name == "<default>"


def test_resolve_database_name_from_extra_attrs():
    db = _FakeSession()
    _seed_instance(db, instance_id=100, extra_attrs={"ai_object_metadata_database_name": "app_db"})
    name = _resolve_database_name(db, instance_id=100)
    assert name == "app_db"


def test_resolve_schema_name_from_rows():
    rows = [{"schema_name": "app", "object_type": "table", "object_name": "t1", "ddl_text": "..."}]
    assert _resolve_schema_name_from_rows(rows) == "app"
    assert _resolve_schema_name_from_rows([]) is None


def test_derive_error_code_mapping():
    assert _derive_error_code("skipped") == "COLLECTION_SKIPPED"
    assert _derive_error_code("missing") == "INSTANCE_UNREACHABLE"
    assert _derive_error_code("drifted") == "ASSET_DRIFTED"
    assert _derive_error_code("failed") == "COLLECTION_FAILED"
    assert _derive_error_code("unknown") == "COLLECTION_FAILED"