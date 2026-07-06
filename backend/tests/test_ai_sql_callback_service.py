"""Phase 3.6B1 C14 — AiSqlCallbackService 单元测试.

覆盖（plan §6.5 + §19 P0-6）：
  1. happy path: business_domain='ai_sql' + check_code='DB_READONLY_SQL_EXEC' → audit SUCCESS + chat_message
  2. happy path: result_status=error → audit FAILED + chat_message with error_message
  3. happy path: item_status=timeout → audit TIMEOUT
  4. 幂等性：相同 audit_id 第二次 callback → rowcount=0 跳过（不更新 audit 不写 chat_msg）
  5. 过滤：business_domain='inspection' 的 callback item 被跳过
  6. 过滤：check_code != 'DB_READONLY_SQL_EXEC' 的 ai_sql callback item 被跳过
  7. 异常：callback item business_context 缺 audit_id → log + continue（不破坏主事务）
  8. 异常：audit 不存在 → log + continue（不破坏主事务）
  9. 完整集成：audit.session_id/message_id 缺失时不写 ai_chat_message
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import (
    AiChatMessage,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.services.ai.ai_sql_callback_service import (
    save_execution_results,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
@dataclass
class _FakeCallbackItem:
    business_domain: str
    check_code: str
    item_key: str
    business_context: dict
    raw_result: dict
    status: str = ""
    message: str = ""
    duration_ms: Optional[int] = None


@dataclass
class _FakeFilter:
    key: str
    value: Any


@dataclass
class _FakeQueryResult:
    items: list[Any]
    filters: list[_FakeFilter] = field(default_factory=list)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQueryResult":
        new_filters = list(self.filters)
        for a in args:
            # 解析 SQLAlchemy BinaryExpression（a.left.key / a.right.value）
            left = getattr(a, "left", None)
            right = getattr(a, "right", None)
            key = getattr(left, "key", None) if left is not None else getattr(a, "key", None)
            value = getattr(right, "value", None) if right is not None else getattr(a, "value", None)
            if key is not None and value is not None:
                new_filters.append(_FakeFilter(key=key, value=value))
        return _FakeQueryResult(items=list(self.items), filters=new_filters)

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

    def with_for_update(self) -> "_FakeQueryResult":
        return self

    def _matches(self, item: Any) -> bool:
        for f in self.filters:
            actual = getattr(item, f.key, None)
            if actual != f.value:
                return False
        return True


@dataclass
class _FakeExecuteResult:
    rowcount: int = 0


@dataclass
class _FakeSession:
    """Fake session that simulates the SQLAlchemy update returning rowcount."""
    store: dict[str, list[Any]] = field(default_factory=dict)
    update_rowcount: int = 1
    _chat_msg_id: int = 5000

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))

    def execute(self, stmt: Any) -> _FakeExecuteResult:
        # 简化版：识别 SQLAlchemy update()，把 values 应用到目标表的所有行
        cls_name = type(stmt).__name__
        if cls_name != "Update":
            return _FakeExecuteResult(rowcount=self.update_rowcount)
        # 幂等性测试：update_rowcount=0 时模拟「已是终态」→ 短路返回
        if self.update_rowcount == 0:
            return _FakeExecuteResult(rowcount=0)
        target_table = getattr(stmt, "table", None)
        target_table_name = getattr(target_table, "name", None)
        # 表名 → 类名映射（snake_case → CamelCase）
        cls_lookup = None
        if target_table_name:
            parts = target_table_name.split("_")
            cls_lookup = "".join(p.capitalize() for p in parts)
        values_dict = getattr(stmt, "_values", None)
        if not isinstance(values_dict, dict):
            values_dict = {}
        bind_values = getattr(stmt, "_bind_values", None)
        if not values_dict and isinstance(bind_values, dict):
            values_dict = {getattr(k, "key", str(k)): v for k, v in bind_values.items()}
        if cls_lookup and values_dict:
            items = self.store.get(cls_lookup, [])
            if items:
                for row in items:
                    for k, v in values_dict.items():
                        attr_name = getattr(k, "key", None) if not isinstance(k, str) else k
                        # BindParameter 包裹 value 在 .value
                        if hasattr(v, "value"):
                            v = v.value
                        if attr_name and hasattr(row, attr_name):
                            setattr(row, attr_name, v)
                return _FakeExecuteResult(rowcount=len(items))
        return _FakeExecuteResult(rowcount=self.update_rowcount)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def flush(self) -> None:
        # 给 AiChatMessage 分配 id（模拟 autoincrement）
        for items in self.store.values():
            for obj in items:
                if getattr(obj, "id", None) is None:
                    self._chat_msg_id += 1
                    obj.id = self._chat_msg_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_audit(
    *,
    audit_id: int = 100,
    session_id: Optional[int] = None,
    message_id: Optional[int] = None,
    exec_status: str = AiSqlAuditExecutionStatus.RUNNING,
    preview_status: str = AiSqlAuditPreviewSafety.PASSED,
) -> AiSqlAudit:
    audit = AiSqlAudit(
        instance_id=1,
        db_type_code="POSTGRESQL",
        user_question="q",
        approved_sql="SELECT 1",
        approved_sql_hash="h" * 64,
        preview_safety_status=preview_status,
        previewed_at=datetime.now(tz=timezone.utc),
        schema_snapshot_id=1,
        schema_policy_hash="p" * 64,
        execution_status=exec_status,
        created_at=datetime.now(tz=timezone.utc),
        session_id=session_id,
        message_id=message_id,
    )
    audit.id = audit_id
    return audit


def _make_callback_item(
    *,
    audit_id: int = 100,
    business_domain: str = "ai_sql",
    check_code: str = "DB_READONLY_SQL_EXEC",
    item_status: str = "verified",
    result_status: str = "ok",
    columns: Optional[list[str]] = None,
    rows: Optional[list[list[Any]]] = None,
    error_code: str = "",
    error_message: str = "",
    duration_ms: int = 100,
) -> _FakeCallbackItem:
    return _FakeCallbackItem(
        business_domain=business_domain,
        check_code=check_code,
        item_key=f"ai_sql:{audit_id}:1",
        business_context={
            "business_domain": "ai_sql",
            "business_context": {"audit_id": audit_id, "session_id": 1},
        },
        raw_result={
            "columns": columns if columns is not None else ["id", "name"],
            "rows": rows if rows is not None else [[1, "alice"], [2, "bob"]],
            "result_status": result_status,
            "error_code": error_code,
            "stderr": error_message,
        },
        status=item_status,
        message=error_message,
        duration_ms=duration_ms,
    )


def _make_audit_run() -> Any:
    """Fake CollectorRun-like object（仅作参数占位）。"""
    @dataclass
    class _Run:
        run_id: str = "ai-sql-test"
    return _Run()


# ---------------------------------------------------------------------------
# 1. happy path — SUCCESS
# ---------------------------------------------------------------------------
class TestHappyPath:
    def test_success_writes_chat_message(self):
        db = _FakeSession()
        audit = _make_audit(session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_callback_item(audit_id=100)

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 1
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        assert audit.row_count == 2
        assert audit.duration_ms == 100
        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1
        m = msgs[0]
        assert m.session_id == 1
        assert m.role == "assistant"
        assert m.message_type == "sql_result"
        assert m.parent_message_id == 10
        assert audit.result_message_id == m.id

    def test_failed_writes_chat_message_with_error(self):
        db = _FakeSession()
        audit = _make_audit(session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_callback_item(
            audit_id=100, item_status="failed", result_status="error",
            error_code="PG_DENIED", error_message="permission denied",
        )

        save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert audit.execution_status == AiSqlAuditExecutionStatus.FAILED
        assert "PG_DENIED" in (audit.error_message or "")
        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1

    def test_timeout_marks_timeout(self):
        db = _FakeSession()
        audit = _make_audit(session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_callback_item(
            audit_id=100, item_status="timeout", result_status="",
        )

        save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert audit.execution_status == AiSqlAuditExecutionStatus.TIMEOUT


# ---------------------------------------------------------------------------
# 2. 幂等性 — rowcount=0 跳过
# ---------------------------------------------------------------------------
class TestIdempotency:
    def test_second_callback_skips(self):
        db = _FakeSession(update_rowcount=0)  # 模拟「已是终态」
        audit = _make_audit(
            session_id=1, message_id=10,
            exec_status=AiSqlAuditExecutionStatus.SUCCESS,
        )
        db.store["AiSqlAudit"] = [audit]
        cb = _make_callback_item(audit_id=100)

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 1  # 函数层仍计 1（业务层尝试过）
        assert "AiChatMessage" not in db.store or len(db.store.get("AiChatMessage", [])) == 0


# ---------------------------------------------------------------------------
# 3. 过滤
# ---------------------------------------------------------------------------
class TestFilters:
    def test_skips_non_ai_sql_business_domain(self):
        db = _FakeSession()
        cb = _make_callback_item(business_domain="inspection")

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 0
        assert "AiSqlAudit" not in db.store

    def test_skips_non_db_readonly_check_code(self):
        db = _FakeSession()
        cb = _make_callback_item(check_code="OTHER_CHECK_CODE")

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 0
        assert "AiSqlAudit" not in db.store


# ---------------------------------------------------------------------------
# 4. 异常容错
# ---------------------------------------------------------------------------
class TestErrorTolerance:
    def test_missing_audit_id_continues(self):
        db = _FakeSession()
        cb = _make_callback_item()
        cb.business_context = {"business_domain": "ai_sql"}

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 0
        assert "AiSqlAudit" not in db.store

    def test_missing_audit_row_continues(self):
        db = _FakeSession()
        cb = _make_callback_item(audit_id=999)

        written = save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert written == 0

    def test_no_session_no_chat_message(self):
        """audit.session_id/message_id 为 None 时不写 chat_message（仅更新 audit）。"""
        db = _FakeSession()
        audit = _make_audit(session_id=None, message_id=None)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_callback_item(audit_id=100)

        save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        assert "AiChatMessage" not in db.store


# ---------------------------------------------------------------------------
# 5. C16-F2 — business_context passthrough + item_key fallback
# ---------------------------------------------------------------------------
class TestF2BusinessContextResolution:
    """C16-F2: 修复 F1 时代码正确但 Pydantic schema drop business_context 的
    隐性 bug。callback 必须能从 item 中拿到 audit_id，本组测试覆盖：
    1) 标准 nested business_context（正常路径，仍可用）
    2) flat business_context（AWX 简化格式回传）
    3) business_context 缺失时 item_key 兜底解析
    4) audit_id 拿到后 → audit 状态推进 + chat_message(message_type='sql_result') 落库
       + result_message_id 反向写回
    """

    def test_nested_business_context_still_works(self):
        """嵌套格式 business_context.business_context.audit_id 仍正确解析。"""
        from app.services.ai.ai_sql_callback_service import _extract_business_context

        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="ai_sql:100:965",
            business_context={
                "business_domain": "ai_sql",
                "business_context": {"audit_id": 100, "session_id": 1},
            },
            raw_result={},
        )
        result = _extract_business_context(cb)
        assert result.get("audit_id") == 100
        assert result.get("session_id") == 1

    def test_flat_business_context_works(self):
        """扁平格式 business_context.audit_id（AWX 直传简化）。"""
        from app.services.ai.ai_sql_callback_service import _extract_business_context

        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="ai_sql:100:965",
            business_context={"audit_id": 100, "session_id": 1},
            raw_result={},
        )
        result = _extract_business_context(cb)
        assert result.get("audit_id") == 100

    def test_item_key_fallback_when_business_context_missing(self):
        """business_context=None 时从 item_key=ai_sql:{audit_id}:{instance_id} 解析。"""
        from app.services.ai.ai_sql_callback_service import _extract_business_context

        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="ai_sql:42:965",
            business_context=None,
            raw_result={},
        )
        result = _extract_business_context(cb)
        assert result.get("audit_id") == 42
        assert "session_id" not in result

    def test_item_key_fallback_when_business_context_is_empty_dict(self):
        """business_context={} 时同样走 item_key 兜底。"""
        from app.services.ai.ai_sql_callback_service import _extract_business_context

        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="ai_sql:7:965",
            business_context={},
            raw_result={},
        )
        result = _extract_business_context(cb)
        assert result.get("audit_id") == 7

    def test_item_key_fallback_does_not_break_when_format_invalid(self):
        """item_key 不是 ai_sql: 前缀时 fallback 不抛异常。"""
        from app.services.ai.ai_sql_callback_service import _extract_business_context

        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="other:scope:123",
            business_context=None,
            raw_result={},
        )
        result = _extract_business_context(cb)
        assert result == {}

    def test_end_to_end_via_item_key_fallback_writes_chat_message(self):
        """End-to-end: business_context 缺失时，callback 通过 item_key 解析 audit_id，
        写 audit 状态 + chat_message(message_type='sql_result') + 反向 result_message_id。
        """
        db = _FakeSession()
        audit = _make_audit(audit_id=99, session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        # 直接构造一个无 business_context 的 callback，item_key 携带 audit_id
        cb = _FakeCallbackItem(
            business_domain="ai_sql",
            check_code="DB_READONLY_SQL_EXEC",
            item_key="ai_sql:99:965",
            business_context=None,  # 关键：缺失
            raw_result={
                "columns": ["n"],
                "rows": [[1], [2], [3]],
                "result_status": "ok",
            },
            status="verified",
            message="",
            duration_ms=200,
        )

        save_execution_results(db, run=_make_audit_run(), callback_items=[cb])
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        assert audit.row_count == 3
        assert audit.duration_ms == 200
        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1
        m = msgs[0]
        assert m.message_type == "sql_result"
        assert m.role == "assistant"
        assert m.session_id == 1
        assert m.parent_message_id == 10
        assert audit.result_message_id == m.id


# ---------------------------------------------------------------------------
# 6. C16-F2 — Pydantic schema accepts business_context (drop 修复)
# ---------------------------------------------------------------------------
class TestF2SchemaAcceptsBusinessContext:
    """C16-F2: CollectorCallbackItem schema 之前未声明 business_context 字段，
    Pydantic v2 默认 extra='ignore' 会把 AWX 回传的 business_context 静默丢掉。
    本组测试确认 schema 显式声明后，business_context 能进回调链。"""

    def test_collector_callback_item_accepts_business_context(self):
        from app.schemas.collector import CollectorCallbackItem

        item = CollectorCallbackItem(
            item_key="ai_sql:4:965",
            check_code="DB_READONLY_SQL_EXEC",
            target_scope="db_instance",
            asset_id=965,
            target_host="10.134.185.228",
            target_port=5432,
            status="verified",
            business_domain="ai_sql",
            business_context={
                "business_domain": "ai_sql",
                "business_context": {"audit_id": 4, "session_id": 1},
            },
        )
        assert item.business_context is not None
        assert item.business_context["business_context"]["audit_id"] == 4

    def test_collector_callback_item_business_context_optional(self):
        """不传 business_context 时 None（旧 callback 兼容）。"""
        from app.schemas.collector import CollectorCallbackItem

        item = CollectorCallbackItem(
            item_key="x:1:1",
            check_code="DB_BASIC_FACT_COLLECTION",
            target_scope="db_instance",
            asset_id=1,
            target_host="x",
            target_port=5432,
            status="collected",
        )
        assert item.business_context is None