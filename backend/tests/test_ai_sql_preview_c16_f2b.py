"""Phase 3.6B2 C16-F2b — AiSqlPreviewService Chat-flow 集成测试.

覆盖 (plan §21.3 C16-3 + handoff §4.2):
  Part A  Auth Chain (5 cases):
    1.  session 不存在          → ChatSessionNotFoundErrorPreview (404)
    2.  session 不属于当前用户   → ChatSessionForbiddenErrorPreview (403)
    3.  session.chat_mode='general' → ChatModeNotInstanceSqlError (422)
    4.  instance_id != bound_instance_id → ChatImmutableViolationErrorPreview (422)
    5.  DbInstance.status='inactive' → ChatInstanceNotAccessibleError (404)

  Part B  Idempotency (3 cases):
    6.  首次调用 → 走完整流程，audit + 2 messages 写入
    7.  同 client_request_id 重复 → 返回相同三元组 + idempotent_replay=True（不调 Dify）
    8.  client_request_id 命中 user_message 但 audit 缺失 → PreviewIncompleteRetryRequiredError (409)

  Part C  Dual Message Write (4 cases):
    9.  passed → user + preview message 都落库，audit.message_id + result_message_id 关联
    10. Dify 无 SQL (rejected) → user + preview 都写，preview content 含 reason
    11. AST 拒绝 (rejected) → user + preview 都写，audit.preview_safety_status='rejected'
    12. 双消息落库后 session.message_count += 2

  Part D  Response Fields (1 case):
    13. PreviewResult 包含 session_id / user_message_id / preview_message_id / idempotent_replay

策略:
  - 独立 _FakeSession / _FakeQueryResult（不复用 test_ai_sql_preview_service.py 的 fake，
    避免被 commit 1 改造的 _patch_chat_session 行为影响）
  - monkeypatch DifyService 与 AiSchemaContextService（不连真实 DB / Dify）
  - 端到端走 AiSqlPreviewService.preview() 全流程

注意: 不写任何 credentials / tokens / passwords（CLAUDE.md §1.10 强约束）。
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings, get_settings
from app.models.ai import (
    AiChatMessage,
    AiChatSession,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.services.ai import ai_sql_preview_service as svc_mod
from app.services.ai.ai_sql_preview_service import (
    AiSqlPreviewService,
    ChatImmutableViolationErrorPreview,
    ChatInstanceNotAccessibleError,
    ChatModeNotInstanceSqlError,
    ChatSessionForbiddenErrorPreview,
    ChatSessionNotFoundErrorPreview,
    FeatureDisabledError,
    PreviewIncompleteRetryRequiredError,
    PreviewResult,
)


# ---------------------------------------------------------------------------
# Fake user (simulate current_user)
# ---------------------------------------------------------------------------
@dataclass
class FakeUser:
    id: Any = uuid.UUID("00000000-0000-0000-0000-000000000001")
    username: str = "fake_user"


# ---------------------------------------------------------------------------
# Independent Fake session (不与 test_ai_sql_preview_service.py 的 fake 耦合)
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
        for k, v in kwargs.items():
            new_filters.append(_FakeFilter(field=k, value=v))
        return _FakeQueryResult(items=list(self.items), filters=new_filters)

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

    def one_or_none(self) -> Optional[Any]:
        """C16-5+ Commit 8: ai_sql_preview_service.run_preview uses .one_or_none()
        for DbInstance lookup. Mirror first() (single-item store; multi-row
        match would be a test design bug)."""
        return self.first()

    def all(self) -> list[Any]:
        return [i for i in self.items if self._matches(i)]

    def _matches(self, item: Any) -> bool:
        for f in self.filters:
            actual = getattr(item, f.field, None)
            if f.op == "==":
                if actual != f.value:
                    return False
        return True


@dataclass
class _FakeSession:
    """最小 fake session — 支持 add/query/commit/flush/refresh。"""

    store: dict[str, list[Any]] = field(default_factory=dict)
    commits: int = 0
    refreshes: int = 0
    _id_counter: dict[str, int] = field(default_factory=dict)

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def flush(self) -> None:
        """模拟 SQLAlchemy flush — 给新 add 的对象分配 id。"""
        for cls_name, items in self.store.items():
            for item in items:
                if getattr(item, "id", None) is None:
                    self._id_counter[cls_name] = self._id_counter.get(cls_name, 1000) + 1
                    item.id = self._id_counter[cls_name]

    def refresh(self, obj: Any) -> None:
        self.refreshes += 1
        if getattr(obj, "id", None) is None:
            cls_name = type(obj).__name__
            self._id_counter[cls_name] = self._id_counter.get(cls_name, 1000) + 1
            obj.id = self._id_counter[cls_name]


# ---------------------------------------------------------------------------
# Helpers — settings / schema context / dify / chat session / db instance
# ---------------------------------------------------------------------------
def _patch_settings(monkeypatch, *, preview_enabled: bool = True):
    """覆盖 settings.AI_SQL_PREVIEW_ENABLED（不污染其他字段）。"""

    base = get_settings()
    base.AI_SQL_PREVIEW_ENABLED = preview_enabled
    monkeypatch.setattr(svc_mod, "get_settings", lambda: base)


def _patch_schema_context(
    monkeypatch,
    *,
    available: bool = True,
    reason: str = "ok",
    schema_snapshot_id: int = 100,
    schema_policy_hash: str = "abc123",
    allowed_tables: Optional[list[str]] = None,
    allowed_columns: Optional[dict[str, list[str]]] = None,
    denied_columns: Optional[list[str]] = None,
    db_type_code: str = "POSTGRESQL",
):
    """monkeypatch AiSchemaContextService.build_schema_context。"""
    if allowed_tables is None:
        allowed_tables = ["public.orders"]
    if allowed_columns is None:
        allowed_columns = {"public.orders": ["id", "amount"]}
    if denied_columns is None:
        denied_columns = ["password_hash", "secret_key"]

    def _fake_build(*args, **kwargs):
        if available:
            return {
                "available": True,
                "instance_id": kwargs.get("instance_id", 1),
                "db_type_code": db_type_code,
                "sql_dialect": "postgres",
                "schema_context": "schema-context-text",
                "allowed_schemas": ["public"],
                "allowed_tables": allowed_tables,
                "allowed_columns": allowed_columns,
                "denied_columns": denied_columns,
                "schema_snapshot_id": schema_snapshot_id,
                "schema_policy_hash": schema_policy_hash,
                "collected_at": None,
                "expires_at": None,
                "total_tables": 1,
                "total_columns": 2,
                "reason": None,
            }
        return {
            "available": False,
            "instance_id": kwargs.get("instance_id", 1),
            "reason": reason,
        }

    monkeypatch.setattr(
        "app.services.ai.ai_schema_context_service.AiSchemaContextService.build_schema_context",
        staticmethod(_fake_build),
    )


def _patch_dify_configured(monkeypatch, configured: bool = True):
    from app.services.dify_service import DifyService

    monkeypatch.setattr(DifyService, "is_configured", classmethod(lambda cls: configured))


def _patch_dify_success(monkeypatch, *, generated_sql: str = "SELECT 1"):
    """调 Dify 成功，返回 generated_sql 走 AST 校验通过。"""

    def _fake_run(*args, **kwargs):
        return {
            "workflow_run_id": "wf-fake-001",
            "outputs": {"generated_sql": generated_sql},
        }

    from app.services.dify_service import DifyService

    monkeypatch.setattr(DifyService, "run_sql_workflow", staticmethod(_fake_run))


def _patch_dify_no_sql(monkeypatch):
    """Dify 返回但无 generated_sql → 走 rejected audit 分支。"""

    def _fake_run(*args, **kwargs):
        return {
            "workflow_run_id": "wf-fake-002",
            "outputs": {},
        }

    from app.services.dify_service import DifyService

    monkeypatch.setattr(DifyService, "run_sql_workflow", staticmethod(_fake_run))


def _patch_ast_invalid(monkeypatch):
    """让 AST 校验拒绝（FOR UPDATE）— 走 rejected audit 分支。"""

    def _fake_validate(*args, **kwargs):
        return {
            "valid": False,
            "approved_sql": "",
            "approved_sql_hash": "",
            "errors": ["forbidden_keyword: FOR UPDATE"],
            "warnings": [],
        }

    monkeypatch.setattr(
        "app.services.sql_safety_service.SqlSafetyService.validate_with_ast",
        staticmethod(_fake_validate),
    )


def _inject_session(
    db: _FakeSession,
    *,
    session_id: int = 1,
    user_id: Any = None,
    chat_mode: str = "instance_sql",
    bound_instance_id: int = 1,
):
    """向 fake session 注入 AiChatSession。user_id 默认等于 FakeUser.id。"""
    if user_id is None:
        user_id = FakeUser().id
    sess = AiChatSession(
        session_code=f"FAKE-{session_id}",
        user_id=user_id,
        title="fake",
        chat_mode=chat_mode,
        bound_instance_id=bound_instance_id,
    )
    sess.id = session_id
    db.store["AiChatSession"] = [sess]
    return sess


def _inject_instance(db: _FakeSession, *, instance_id: int = 1, status: str = "active"):
    """向 fake session 注入 DbInstance + DbType。"""
    from app.models.dbops_assets import DbInstance, DbType

    db_type = DbType(id=1, type_code="POSTGRESQL")
    instance = DbInstance(id=instance_id, db_type_id=1, status=status)
    db.store["DbInstance"] = [instance]
    db.store["DbType"] = [db_type]
    return instance


# ---------------------------------------------------------------------------
# Part A — Auth Chain (5 cases)
# ---------------------------------------------------------------------------
class TestAuthChainSessionNotFound:
    def test_missing_session_raises_not_found(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        # No _inject_session → store 中无 AiChatSession
        _inject_instance(db := _FakeSession(), instance_id=1)

        with pytest.raises(ChatSessionNotFoundErrorPreview):
            AiSqlPreviewService.preview(
                db,
                instance_id=1,
                database_name=None,
                user_question="q",
                session_id=999,
                client_request_id=uuid.uuid4(),
                requested_by=FakeUser(),
            )


class TestAuthChainSessionForbidden:
    def test_session_owned_by_others_raises_forbidden(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        # session.user_id != FakeUser().id
        _inject_session(
            db := _FakeSession(),
            session_id=1,
            user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            bound_instance_id=1,
        )
        _inject_instance(db, instance_id=1)

        with pytest.raises(ChatSessionForbiddenErrorPreview):
            AiSqlPreviewService.preview(
                db,
                instance_id=1,
                database_name=None,
                user_question="q",
                session_id=1,
                client_request_id=uuid.uuid4(),
                requested_by=FakeUser(),
            )


class TestAuthChainChatMode:
    def test_general_mode_session_raises_422(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        _inject_session(db := _FakeSession(), chat_mode="general", bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        with pytest.raises(ChatModeNotInstanceSqlError):
            AiSqlPreviewService.preview(
                db,
                instance_id=1,
                database_name=None,
                user_question="q",
                session_id=1,
                client_request_id=uuid.uuid4(),
                requested_by=FakeUser(),
            )


class TestAuthChainImmutableViolation:
    def test_instance_id_mismatch_raises_422(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)
        # 注：bound_instance_id=1 但 request.instance_id=999 → 应抛 ChatImmutableViolationErrorPreview
        with pytest.raises(ChatImmutableViolationErrorPreview):
            AiSqlPreviewService.preview(
                db,
                instance_id=999,
                database_name=None,
                user_question="q",
                session_id=1,
                client_request_id=uuid.uuid4(),
                requested_by=FakeUser(),
            )


class TestAuthChainInstanceInactive:
    def test_instance_status_inactive_raises_404(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1, status="inactive")

        with pytest.raises(ChatInstanceNotAccessibleError):
            AiSqlPreviewService.preview(
                db,
                instance_id=1,
                database_name=None,
                user_question="q",
                session_id=1,
                client_request_id=uuid.uuid4(),
                requested_by=FakeUser(),
            )


# ---------------------------------------------------------------------------
# Part B — Idempotency (3 cases)
# ---------------------------------------------------------------------------
class TestIdempotency:
    def test_first_call_creates_audit_and_messages(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT id FROM public.orders")
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)
        client_request_id = uuid.uuid4()

        result = AiSqlPreviewService.preview(
            db,
            instance_id=1,
            database_name=None,
            user_question="q",
            session_id=1,
            client_request_id=client_request_id,
            requested_by=FakeUser(),
        )

        assert isinstance(result, PreviewResult)
        assert result.idempotent_replay is False
        assert result.user_message_id > 0
        assert result.preview_message_id > 0
        assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.PASSED
        # 三类对象都写入 fake session store
        assert len(db.store.get("AiSqlAudit", [])) == 1
        assert len(db.store.get("AiChatMessage", [])) == 2

    def test_repeat_call_returns_same_triplet_without_dify(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT id FROM public.orders")
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)
        client_request_id = uuid.uuid4()

        # 首次调用
        result1 = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="q",
            session_id=1, client_request_id=client_request_id, requested_by=FakeUser(),
        )

        # 重复调用（同 client_request_id）
        result2 = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="q",
            session_id=1, client_request_id=client_request_id, requested_by=FakeUser(),
        )

        # 三元组一致 + idempotent_replay=True
        assert result2.idempotent_replay is True
        assert result2.audit.id == result1.audit.id
        assert result2.user_message_id == result1.user_message_id
        assert result2.preview_message_id == result1.preview_message_id
        # 重复调用不应新增 audit 或 message
        assert len(db.store.get("AiSqlAudit", [])) == 1
        assert len(db.store.get("AiChatMessage", [])) == 2

    def test_replay_with_missing_audit_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        # 预先注入 user_message 但**不**关联 audit（模拟上次事务 1/2 中途中断）
        existing_user_msg = AiChatMessage(
            session_id=1,
            user_id=FakeUser().id,
            client_request_id=uuid.uuid4(),
            role="user",
            message_type="chat",
            status="completed",
            content="interrupted question",
            attempt_count=0,
        )
        existing_user_msg.id = 8888
        db.store["AiChatMessage"] = [existing_user_msg]

        client_request_id = existing_user_msg.client_request_id

        with pytest.raises(PreviewIncompleteRetryRequiredError) as exc_info:
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
                session_id=1, client_request_id=client_request_id, requested_by=FakeUser(),
            )

        # 验证异常携带 user_message_id
        assert exc_info.value.user_message_id == 8888


# ---------------------------------------------------------------------------
# Part C — Dual Message Write (4 cases)
# ---------------------------------------------------------------------------
class TestDualMessageWritePassed:
    def test_passed_writes_user_preview_messages(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT id FROM public.orders")
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        result = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="Q1",
            session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
        )

        messages = db.store.get("AiChatMessage", [])
        assert len(messages) == 2
        user_msg = next(m for m in messages if m.role == "user")
        preview_msg = next(m for m in messages if m.role == "assistant")

        # user message 属性
        assert user_msg.message_type == "chat"
        assert user_msg.content == "Q1"
        assert user_msg.session_id == 1
        # preview message 属性
        assert preview_msg.message_type == "sql_preview_link"
        assert preview_msg.parent_message_id == user_msg.id
        assert preview_msg.session_id == 1
        # audit 关联
        assert result.audit.message_id == user_msg.id
        assert result.audit.result_message_id == preview_msg.id


class TestDualMessageWriteDifyNoSql:
    def test_rejected_dify_no_sql_still_writes_messages(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_no_sql(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        result = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="Q",
            session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
        )

        # rejected 也写 audit + 双 messages
        assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.REJECTED
        messages = db.store.get("AiChatMessage", [])
        assert len(messages) == 2
        preview_msg = next(m for m in messages if m.role == "assistant")
        # preview content 含 reason
        try:
            content = json.loads(preview_msg.content)
        except (json.JSONDecodeError, TypeError):
            content = {}
        assert content.get("preview_safety_status") == "rejected"
        assert "reason" in content


class TestDualMessageWriteAstRejected:
    def test_rejected_ast_still_writes_messages(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT * FROM t FOR UPDATE")
        _patch_ast_invalid(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        result = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="Q",
            session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
        )

        assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.REJECTED
        # 双 messages 写入
        assert len(db.store.get("AiChatMessage", [])) == 2
        # user_message.client_request_id 落库（partial unique 自然校验）
        user_msg = next(m for m in db.store["AiChatMessage"] if m.role == "user")
        assert user_msg.client_request_id is not None


class TestDualMessageSessionCountIncrement:
    def test_message_count_increments_by_two(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT id FROM public.orders")
        sess = _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)
        # 初始 message_count
        assert sess.message_count == 0 or sess.message_count is None

        AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="Q",
            session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
        )

        # session.message_count += 2
        sess_after = db.store["AiChatSession"][0]
        assert sess_after.message_count == 2
        assert sess_after.last_message_at is not None


# ---------------------------------------------------------------------------
# Part D — Response Fields (1 case)
# ---------------------------------------------------------------------------
class TestPreviewResultFields:
    def test_preview_result_has_all_required_fields(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)
        _patch_dify_success(monkeypatch, generated_sql="SELECT id FROM public.orders")
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        result = AiSqlPreviewService.preview(
            db, instance_id=1, database_name=None, user_question="Q",
            session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
        )

        # PreviewResult 4 个 C16-F2b 新字段都在
        assert hasattr(result, "session_id")
        assert hasattr(result, "user_message_id")
        assert hasattr(result, "preview_message_id")
        assert hasattr(result, "idempotent_replay")
        assert result.session_id == 1
        assert isinstance(result.idempotent_replay, bool)
        assert result.idempotent_replay is False


# ---------------------------------------------------------------------------
# Extra — FeatureDisabled guard (commit 1 既有异常，本文件额外覆盖)
# ---------------------------------------------------------------------------
class TestFeatureDisabledGuard:
    def test_disabled_raises_before_auth_chain(self, monkeypatch):
        """功能开关关闭时，连鉴权链都不应进入（C16-F2b P0-1 顺序：开关在前）。"""
        _patch_settings(monkeypatch, preview_enabled=False)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)
        _inject_session(db := _FakeSession(), bound_instance_id=1)
        _inject_instance(db, instance_id=1)

        with pytest.raises(FeatureDisabledError):
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
                session_id=1, client_request_id=uuid.uuid4(), requested_by=FakeUser(),
            )