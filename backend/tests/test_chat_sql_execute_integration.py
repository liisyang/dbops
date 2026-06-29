"""Phase 3.6B1 C14 — Chat ↔ SQL Execute 端到端集成测试.

覆盖（plan §6.5 + §10）：
  1. 完整链路 1：SUCCESS 回调 → audit 终态 + chat_message(sql_result) 完整结构
  2. 完整链路 2：FAILED 回调 → audit FAILED + chat_message 含 error_message
  3. 完整链路 3：TIMEOUT 回调 → audit TIMEOUT
  4. 幂等键写入：chat_message.metadata_json.audit_id 存在
  5. result_message_id 双向绑定：audit.result_message_id == chat_msg.id
  6. 混合 business_domain：ai_sql + inspection 同时到达时只 ai_sql 落库
  7. 端到端 1+1 串行：第一次 SUCCESS 写 chat_msg，第二次 callback 短路（无 chat_msg 重复）

复用 #22 test_ai_sql_callback_service.py 的 _FakeSession 模板（验证可用）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import (
    AiChatMessage,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.services.ai.ai_sql_callback_service import save_execution_results


# ---------------------------------------------------------------------------
# Fakes (复用 test_ai_sql_callback_service.py 模板，扩展：INSERT 也走 flush)
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
            left = getattr(a, "left", None)
            right = getattr(a, "right", None)
            key = getattr(left, "key", None) if left is not None else getattr(a, "key", None)
            value = (
                getattr(right, "value", None) if right is not None else getattr(a, "value", None)
            )
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
            if getattr(item, f.key, None) != f.value:
                return False
        return True


@dataclass
class _FakeExecuteResult:
    rowcount: int = 0


@dataclass
class _FakeSession:
    """最小化 SQLAlchemy Session fake。"""

    store: dict[str, list[Any]] = field(default_factory=dict)
    update_rowcount: int = 1
    _id_counter: int = 1000

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))

    def execute(self, stmt: Any) -> _FakeExecuteResult:
        cls_name = type(stmt).__name__
        if cls_name != "Update":
            return _FakeExecuteResult(rowcount=self.update_rowcount)
        if self.update_rowcount == 0:
            return _FakeExecuteResult(rowcount=0)
        target_table = getattr(stmt, "table", None)
        target_table_name = getattr(target_table, "name", None)
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
        for items in self.store.values():
            for obj in items:
                if getattr(obj, "id", None) is None:
                    self._id_counter += 1
                    obj.id = self._id_counter


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _make_audit(
    *,
    audit_id: int = 100,
    session_id: Optional[int] = 1,
    message_id: Optional[int] = 10,
    exec_status: str = AiSqlAuditExecutionStatus.RUNNING,
) -> AiSqlAudit:
    audit = AiSqlAudit(
        instance_id=1,
        db_type_code="POSTGRESQL",
        user_question="q",
        approved_sql="SELECT 1",
        approved_sql_hash="h" * 64,
        preview_safety_status=AiSqlAuditPreviewSafety.PASSED,
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


def _make_cb(
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


@dataclass
class _RunStub:
    run_id: str = "ai-sql-integration-test"


# ---------------------------------------------------------------------------
# 1. 端到端 SUCCESS
# ---------------------------------------------------------------------------
class TestEndToEndSuccess:
    def test_callback_writes_chat_message_with_full_structure(self):
        db = _FakeSession()
        audit = _make_audit(session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_cb(audit_id=100, duration_ms=250)

        written = save_execution_results(db, run=_RunStub(), callback_items=[cb])
        assert written == 1

        # audit 终态
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        assert audit.row_count == 2
        assert audit.duration_ms == 250
        assert audit.completed_at is not None
        assert audit.error_message is None

        # chat_message 完整结构
        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1
        m = msgs[0]
        assert m.session_id == 1
        assert m.role == "assistant"
        assert m.message_type == "sql_result"
        assert m.status == "completed"
        assert m.parent_message_id == 10

        # 幂等键：metadata_json.audit_id
        assert m.metadata_json["audit_id"] == 100
        assert m.metadata_json["execution_status"] == "success"
        assert m.metadata_json["row_count"] == 2

        # audit.result_message_id 双向绑定
        assert audit.result_message_id == m.id

        # content JSON 反序列化校验
        import json as _json

        content = _json.loads(m.content)
        assert content["columns"] == ["id", "name"]
        assert content["rows"] == [[1, "alice"], [2, "bob"]]
        assert content["status"] == "success"
        assert content["row_count"] == 2
        assert content["duration_ms"] == 250
        assert "executed_at" in content


# ---------------------------------------------------------------------------
# 2. 端到端 FAILED
# ---------------------------------------------------------------------------
class TestEndToEndFailed:
    def test_failed_callback_writes_chat_message_with_error(self):
        db = _FakeSession()
        audit = _make_audit(session_id=2, message_id=20)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_cb(
            audit_id=100, item_status="failed", result_status="error",
            error_code="PG_DENIED", error_message="permission denied to table foo",
            rows=[],
        )

        save_execution_results(db, run=_RunStub(), callback_items=[cb])

        assert audit.execution_status == AiSqlAuditExecutionStatus.FAILED
        assert "PG_DENIED" in (audit.error_message or "")
        assert "permission denied" in (audit.error_message or "")

        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1
        m = msgs[0]
        import json as _json

        content = _json.loads(m.content)
        assert content["status"] == "failed"
        assert content["error_message"] is not None
        assert "permission denied" in content["error_message"]


# ---------------------------------------------------------------------------
# 3. 端到端 TIMEOUT
# ---------------------------------------------------------------------------
class TestEndToEndTimeout:
    def test_timeout_callback_marks_audit_timeout(self):
        db = _FakeSession()
        audit = _make_audit(session_id=3, message_id=30)
        db.store["AiSqlAudit"] = [audit]
        cb = _make_cb(audit_id=100, item_status="timeout", result_status="")

        save_execution_results(db, run=_RunStub(), callback_items=[cb])

        assert audit.execution_status == AiSqlAuditExecutionStatus.TIMEOUT
        msgs = db.store.get("AiChatMessage", [])
        assert len(msgs) == 1


# ---------------------------------------------------------------------------
# 4. 混合 business_domain
# ---------------------------------------------------------------------------
class TestMixedBusinessDomain:
    def test_ai_sql_processed_inspection_skipped(self):
        db = _FakeSession()
        audit = _make_audit(audit_id=100, session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        ai_cb = _make_cb(audit_id=100, business_domain="ai_sql")
        insp_cb = _make_cb(audit_id=100, business_domain="inspection")

        written = save_execution_results(
            db, run=_RunStub(), callback_items=[ai_cb, insp_cb]
        )

        assert written == 1
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        msgs = db.store.get("AiChatMessage", [])
        # 只 1 个 chat_msg（ai_sql 路径）
        assert len(msgs) == 1


# ---------------------------------------------------------------------------
# 5. 1+1 串行：第二次短路
# ---------------------------------------------------------------------------
class TestSerialTwoCallbacks:
    def test_second_callback_is_idempotent_skip(self):
        db = _FakeSession()
        audit = _make_audit(session_id=1, message_id=10)
        db.store["AiSqlAudit"] = [audit]
        cb1 = _make_cb(audit_id=100)

        save_execution_results(db, run=_RunStub(), callback_items=[cb1])
        assert audit.execution_status == AiSqlAuditExecutionStatus.SUCCESS
        first_msgs = list(db.store.get("AiChatMessage", []))
        assert len(first_msgs) == 1

        # 模拟 AWX 第二次 callback：update_rowcount=0 表示已是终态
        db.update_rowcount = 0
        cb2 = _make_cb(audit_id=100, rows=[[99, "replay"]])
        save_execution_results(db, run=_RunStub(), callback_items=[cb2])

        # chat_message 不重复
        second_msgs = list(db.store.get("AiChatMessage", []))
        assert len(second_msgs) == 1
        # 内容仍是第一次的（rows 不会被 cb2 覆盖）
        import json as _json

        content = _json.loads(second_msgs[0].content)
        assert content["rows"] == [[1, "alice"], [2, "bob"]]
