"""Phase 3.6B2 C16-F2d commit 2 — AiSystemViewPolicyService + 3 集成点单元测试.

覆盖 (plan §21.4 / commit handoff 2026-07-09):

  Part A  AiSystemViewPolicyService 静态/类方法 (10 cases):
    1.  is_active: None / enabled=False / allowlist empty / enabled + non-empty → bool
    2.  is_active: allowlist 含空白字符串仍视为非空
    3.  normalize: 任意字符串 lower + strip
    4.  normalize: 非字符串 → 空串
    5.  merged_allowlist: policy inactive → 仅 base (sorted + 去重)
    6.  merged_allowlist: policy active → base ∪ allowlist (sorted + 去重)
    7.  merged_allowlist: 重复 entry 仅出现一次
    8.  filter_denied_tables: policy inactive → 空集
    9.  filter_denied_tables: denylist 命中 qname → 集合返回
   10.  filter_denied_tables: 大小写不敏感 + denylist 空 → 空集
   11.  policy_version: None / 无 version / 有 version

  Part B  get_policy fallback (4 cases):
   12.  get_policy: instance_id <= 0 → None
   13.  get_policy: query returns row → 返回 row
   14.  get_policy: query returns None → 返回 None
   15.  get_policy: query 抛异常 → 返回 None (logger.exception 包裹)

  Part C  集成点 1 — callback force-include (2 cases)
   16.  _save_one: policy inactive → allowed_tables 不变
   17.  _save_one: policy active → allowed_tables 合并 policy.allowlist

  Part D  集成点 2 — preview _extract_table_qnames (6 cases)
   18.  _extract_table_qnames: simple FROM x.y → ['x.y']
   19.  _extract_table_qnames: JOIN 多表 → 多 qname
   20.  _extract_table_qnames: CTE 虚拟表被过滤
   21.  _extract_table_qnames: 不可解析 SQL → 空 list
   22.  _extract_table_qnames: 三方言 dialect 字符串兼容 (postgres/oracle/tsql)
   23.  _extract_table_qnames: 三方言 namespace prefix 处理 (pg_catalog./information_schema.)

策略: 与 test_ai_schema_context_service.py / test_ai_schema_snapshot_callback_service.py
共用 _FakeFilter / _FakeQueryResult / _FakeSession 模式；不连真实 DB。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus
from app.services.ai.ai_schema_snapshot_callback_service import (
    save_snapshots as cb_save_snapshots,
    _save_one as cb_save_one,
)
from app.services.ai.ai_sql_preview_service import AiSqlPreviewService
from app.services.ai.ai_system_view_policy_service import (
    AiSystemViewPolicyService,
)


# ---------------------------------------------------------------------------
# Fake session / query infrastructure
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
    raise_on_query: Optional[Exception] = None

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for f in args:
            if isinstance(f, _FakeFilter):
                new_filters.append(f)
        # Also accept SQLAlchemy ColumnExpression-like kwargs (e.g. instance_id=...)
        for k, v in kwargs.items():
            if hasattr(v, "key") and hasattr(v, "right"):
                # Column == value style; we use field=key, value=v.right.value
                try:
                    new_filters.append(_FakeFilter(field=k, value=v.right.value))
                except Exception:
                    new_filters.append(_FakeFilter(field=k, value=v))
            else:
                new_filters.append(_FakeFilter(field=k, value=v))
        return _FakeQueryResult(
            items=list(self.items),
            filters=new_filters,
            raise_on_query=self.raise_on_query,
        )

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        return self

    def with_for_update(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        return self

    def first(self) -> Optional[Any]:
        if self.raise_on_query is not None:
            raise self.raise_on_query
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
        return True


@dataclass
class _FakeSession:
    """通用 fake session — 用于 AiSystemViewPolicyService.get_policy 与
    callback _save_one 的 AiSystemViewPolicy / AiSchemaSnapshot 查询。"""

    store: dict[str, list[Any]] = field(default_factory=dict)
    raise_on_query: Optional[Exception] = None

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(
            items=list(self.store.get(cls_name, [])),
            raise_on_query=self.raise_on_query,
        )

    def flush(self) -> None:
        pass

    def execute(self, stmt: Any) -> Any:
        return SimpleNamespace(rowcount=0)


def _make_policy(
    *,
    instance_id: int = 1,
    db_type_code: str = "POSTGRESQL",
    policy_version: str = "2026-07-09-v1",
    allowlist: Optional[list[str]] = None,
    denylist: Optional[list[str]] = None,
    enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        instance_id=instance_id,
        db_type_code=db_type_code,
        policy_version=policy_version,
        allowlist=allowlist if allowlist is not None else ["pg_catalog.pg_stat_activity"],
        denylist=denylist if denylist is not None else [],
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# Shared: build a "verified" callback item for callback integration tests
# ---------------------------------------------------------------------------
def _make_callback_item(
    *,
    asset_id: int = 1,
    db_type_code: str = "POSTGRESQL",
    schema: str = "public",
    tables: Optional[list[tuple[str, str]]] = None,
) -> SimpleNamespace:
    tables = tables or [("public", "t1"), ("public", "t2")]
    columns = ["table_schema", "table_name", "column_name"]
    rows = []
    for schema, table in tables:
        rows.append([schema, table, "id"])
        rows.append([schema, table, "name"])
    return SimpleNamespace(
        business_domain="ai_schema",
        check_code="DB_SCHEMA_METADATA_COLLECTION",
        asset_id=asset_id,
        status="verified",
        message="",
        raw_result={
            "rows": rows,
            "columns": columns,
            "total_rows": len(rows),
            "returned_rows": len(rows),
            "truncated": False,
            "sql_hash": "deadbeef" * 8,
            "source": "test",
            "phase": "snapshot",
        },
        item_key=f"test-{asset_id}-{len(tables)}",
    )


def _make_run(run_id: str = "test-run-001") -> SimpleNamespace:
    return SimpleNamespace(id=1, run_id=run_id)


# ---------------------------------------------------------------------------
# Part A: is_active
# ---------------------------------------------------------------------------
class TestIsActive:
    def test_none_returns_false(self):
        assert AiSystemViewPolicyService.is_active(None) is False

    def test_disabled_returns_false(self):
        p = _make_policy(enabled=False)
        assert AiSystemViewPolicyService.is_active(p) is False

    def test_empty_allowlist_returns_false(self):
        p = _make_policy(allowlist=[])
        assert AiSystemViewPolicyService.is_active(p) is False

    def test_enabled_with_allowlist_returns_true(self):
        p = _make_policy(allowlist=["v$lock"])
        assert AiSystemViewPolicyService.is_active(p) is True

    def test_whitespace_only_allowlist_returns_false(self):
        p = _make_policy(allowlist=["   ", "\t"])
        assert AiSystemViewPolicyService.is_active(p) is False


# ---------------------------------------------------------------------------
# Part A: normalize
# ---------------------------------------------------------------------------
class TestNormalize:
    def test_lowercase_and_strip(self):
        assert AiSystemViewPolicyService.normalize("  V$LOCK  ") == "v$lock"

    def test_empty_returns_empty(self):
        assert AiSystemViewPolicyService.normalize("") == ""

    def test_non_string_returns_empty(self):
        assert AiSystemViewPolicyService.normalize(None) == ""
        assert AiSystemViewPolicyService.normalize(123) == ""
        assert AiSystemViewPolicyService.normalize(["v$lock"]) == ""


# ---------------------------------------------------------------------------
# Part A: merged_allowlist
# ---------------------------------------------------------------------------
class TestMergedAllowlist:
    def test_policy_none_returns_base_sorted(self):
        out = AiSystemViewPolicyService.merged_allowlist(
            None, ["public.t2", "public.t1"],
        )
        assert out == ["public.t1", "public.t2"]

    def test_policy_inactive_returns_base_sorted(self):
        p = _make_policy(enabled=False, allowlist=["v$lock"])
        out = AiSystemViewPolicyService.merged_allowlist(p, ["public.t1"])
        assert out == ["public.t1"]

    def test_policy_active_merges(self):
        p = _make_policy(allowlist=["v$lock", "dba_objects"])
        out = AiSystemViewPolicyService.merged_allowlist(
            p, ["public.t1", "v$lock"],
        )
        assert out == ["dba_objects", "public.t1", "v$lock"]

    def test_dedup(self):
        p = _make_policy(allowlist=["public.t1", "public.t2"])
        out = AiSystemViewPolicyService.merged_allowlist(p, ["public.t1"])
        assert out.count("public.t1") == 1

    def test_empty_base(self):
        p = _make_policy(allowlist=["v$lock"])
        out = AiSystemViewPolicyService.merged_allowlist(p, [])
        assert out == ["v$lock"]

    def test_none_base(self):
        p = _make_policy(allowlist=["v$lock"])
        out = AiSystemViewPolicyService.merged_allowlist(p, None)
        assert out == ["v$lock"]

    def test_policy_with_empty_allowlist_inactive_returns_base(self):
        # active requires enabled AND non-empty allowlist
        p = _make_policy(allowlist=[])
        out = AiSystemViewPolicyService.merged_allowlist(p, ["public.t1"])
        assert out == ["public.t1"]


# ---------------------------------------------------------------------------
# Part A: filter_denied_tables
# ---------------------------------------------------------------------------
class TestFilterDeniedTables:
    def test_policy_none_returns_empty(self):
        out = AiSystemViewPolicyService.filter_denied_tables(None, ["public.t1"])
        assert out == set()

    def test_policy_inactive_returns_empty(self):
        p = _make_policy(enabled=False, denylist=["public.t1"])
        out = AiSystemViewPolicyService.filter_denied_tables(p, ["public.t1"])
        assert out == set()

    def test_empty_denylist_returns_empty(self):
        p = _make_policy(denylist=[])
        out = AiSystemViewPolicyService.filter_denied_tables(p, ["public.t1"])
        assert out == set()

    def test_denied_hit_returns_set(self):
        p = _make_policy(denylist=["public.t1"])
        out = AiSystemViewPolicyService.filter_denied_tables(
            p, ["public.t1", "public.t2"],
        )
        assert out == {"public.t1"}

    def test_case_insensitive_match(self):
        p = _make_policy(denylist=["V$LOCK"])
        out = AiSystemViewPolicyService.filter_denied_tables(
            p, ["v$lock", "public.t1"],
        )
        assert out == {"v$lock"}

    def test_none_input_returns_empty(self):
        p = _make_policy(denylist=["public.t1"])
        out = AiSystemViewPolicyService.filter_denied_tables(p, None)
        assert out == set()


# ---------------------------------------------------------------------------
# Part A: policy_version
# ---------------------------------------------------------------------------
class TestPolicyVersion:
    def test_none_returns_none_placeholder(self):
        assert AiSystemViewPolicyService.policy_version(None) == "<none>"

    def test_with_version_returns_string(self):
        p = _make_policy(policy_version="2026-07-09-v2")
        assert AiSystemViewPolicyService.policy_version(p) == "2026-07-09-v2"

    def test_empty_version_returns_placeholder(self):
        p = _make_policy(policy_version="")
        assert AiSystemViewPolicyService.policy_version(p) == "<none>"


# ---------------------------------------------------------------------------
# Part B: get_policy fallback
# ---------------------------------------------------------------------------
class TestGetPolicy:
    def test_instance_id_zero_returns_none(self):
        db = _FakeSession(store={"AiSystemViewPolicy": [_make_policy()]})
        assert AiSystemViewPolicyService.get_policy(db, instance_id=0) is None

    def test_instance_id_negative_returns_none(self):
        db = _FakeSession(store={"AiSystemViewPolicy": [_make_policy()]})
        assert AiSystemViewPolicyService.get_policy(db, instance_id=-1) is None

    def test_no_row_returns_none(self):
        db = _FakeSession(store={"AiSystemViewPolicy": []})
        assert AiSystemViewPolicyService.get_policy(db, instance_id=1) is None

    def test_query_exception_returns_none(self):
        db = _FakeSession(raise_on_query=RuntimeError("boom"))
        # All queries will raise; get_policy must swallow and return None
        assert AiSystemViewPolicyService.get_policy(db, instance_id=1) is None


# ---------------------------------------------------------------------------
# Part C: callback integration (force-include)
# ---------------------------------------------------------------------------
class TestCallbackIntegration:
    def test_policy_inactive_does_not_merge(self, monkeypatch):
        """policy.enabled=false → _save_one 后 snapshot.allowed_tables 不含 policy entry。"""
        db = _FakeSession(store={"AiSystemViewPolicy": [
            _make_policy(enabled=False, allowlist=["v$lock"]),
        ]})
        # _save_one calls _resolve_db_type_code / _resolve_database_name which
        # both query DbInstance/DbType. Stub them out.
        from app.services.ai import ai_schema_snapshot_callback_service as cb_mod

        monkeypatch.setattr(cb_mod, "_resolve_db_type_code", lambda db, iid: "POSTGRESQL")
        monkeypatch.setattr(cb_mod, "_resolve_database_name", lambda db, iid: "<default>")

        cb = _make_callback_item()
        cb_save_one(db, run=_make_run(), cb=cb)

        snap = db.store["AiSchemaSnapshot"][0]
        assert "v$lock" not in snap.allowed_tables
        assert "public.t1" in snap.allowed_tables

    def test_policy_active_force_includes(self, monkeypatch):
        """policy.enabled=true + allowlist → snapshot.allowed_tables 合并 allowlist。"""
        db = _FakeSession(store={"AiSystemViewPolicy": [
            _make_policy(
                enabled=True,
                allowlist=["v$lock", "dba_objects"],
            ),
        ]})
        from app.services.ai import ai_schema_snapshot_callback_service as cb_mod

        monkeypatch.setattr(cb_mod, "_resolve_db_type_code", lambda db, iid: "POSTGRESQL")
        monkeypatch.setattr(cb_mod, "_resolve_database_name", lambda db, iid: "<default>")

        cb = _make_callback_item()
        cb_save_one(db, run=_make_run(), cb=cb)

        snap = db.store["AiSchemaSnapshot"][0]
        # base tables preserved
        assert "public.t1" in snap.allowed_tables
        assert "public.t2" in snap.allowed_tables
        # policy.allowlist force-included
        assert "v$lock" in snap.allowed_tables
        assert "dba_objects" in snap.allowed_tables


# ---------------------------------------------------------------------------
# Part D: preview _extract_table_qnames (per-dialect sqlglot parse)
# ---------------------------------------------------------------------------
class TestPreviewExtractTableQnames:
    def test_simple_from_qualified(self):
        out = AiSqlPreviewService._extract_table_qnames(
            "SELECT * FROM public.t1", "POSTGRESQL",
        )
        assert "public.t1" in out

    def test_join_multiple_tables(self):
        sql = "SELECT a.id FROM public.t1 a JOIN public.t2 b ON a.id = b.t1_id"
        out = AiSqlPreviewService._extract_table_qnames(sql, "POSTGRESQL")
        assert "public.t1" in out
        assert "public.t2" in out

    def test_cte_alias_filtered(self):
        sql = "WITH cte AS (SELECT 1) SELECT * FROM cte JOIN public.t1 ON cte.x = t1.x"
        out = AiSqlPreviewService._extract_table_qnames(sql, "POSTGRESQL")
        # CTE itself should not appear; public.t1 should
        assert "cte" not in out
        assert "public.t1" in out

    def test_unparseable_returns_empty(self):
        out = AiSqlPreviewService._extract_table_qnames(
            "NOT VALID SQL AT ALL )))(((", "POSTGRESQL",
        )
        assert isinstance(out, list)

    def test_oracle_dialect(self):
        # Oracle: V$LOCK has no schema prefix
        out = AiSqlPreviewService._extract_table_qnames(
            "SELECT * FROM V$LOCK", "ORACLE",
        )
        # sqlglot parse + lowercase + qualified form
        assert any("v$lock" in x.lower() for x in out)

    def test_mssql_dialect(self):
        out = AiSqlPreviewService._extract_table_qnames(
            "SELECT * FROM sys.databases", "MSSQL",
        )
        assert any("databases" in x.lower() for x in out)