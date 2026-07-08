"""Phase 3.6B1 C12 — AiSqlPreviewService 单元测试.

覆盖 (plan §13 + C12 plan):
  1.  happy path: instance + snapshot + Dify returns valid SQL → AST passes
  2.  feature disabled: AI_SQL_PREVIEW_ENABLED=false → FeatureDisabledError
  3.  instance not found: instance_id missing → InstanceNotFoundError
  4.  unsupported db_type: db_type not in capabilities → UnsupportedDbTypeError
  5.  snapshot unavailable (no snapshot) → SnapshotUnavailableError
  6.  snapshot unavailable (pending) → SnapshotUnavailableError
  7.  snapshot unavailable (expired) → SnapshotUnavailableError
  8.  Dify client not configured → DifyUnavailableError
  9.  Dify timeout → DifyTimeoutError_
  10. Dify workflow failed → DifyWorkflowFailedError_
  11. Dify returns no generated_sql → rejected audit
  12. AST rejects (FOR UPDATE) → rejected audit
  13. AST rejects (table.*) → rejected audit
  14. approved_sql_hash stability (same input → same hash)
  15. rejected audit has preview_safety_reason NOT NULL
  16. passed audit has preview_safety_reason NULL + approved_sql NOT NULL
  17. canonical_json_hash stability
  18. _extract_sql_block extracts ```sql ... ``` block
  19. _extract_generated_sql from outputs.generated_sql
  20. _normalize_current_page allowlist enforcement

策略: FakeSession + monkeypatch DifyService 与 AiSchemaContextService，
      不连真实 DB 与 Dify 服务。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings, get_settings
from app.models.ai import (
    AiSchemaSnapshot,
    AiSchemaSnapshotStatus,
    AiSqlAudit,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.services.ai import ai_sql_preview_service as svc_mod
from app.services.ai.ai_sql_preview_service import (
    AiSqlPreviewService,
    DifyTimeoutError_,
    DifyUnavailableError,
    DifyWorkflowFailedError_,
    FeatureDisabledError,
    InstanceNotFoundError,
    SnapshotUnavailableError,
    UnsupportedDbTypeError,
    canonical_json_hash,
)
from app.services.dify_service import (
    DifyService,
    DifyTimeoutError as DifyTimeoutErrorOrig,
    DifyWorkflowFailedError as DifyWorkflowFailedErrorOrig,
)


# ---------------------------------------------------------------------------
# Fake session (与 C10 schema service tests 风格一致)
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

    def first(self) -> Optional[Any]:
        for item in self.items:
            if self._matches(item):
                return item
        return None

    def one_or_none(self) -> Optional[Any]:
        """C16-5+ Commit 8: ai_sql_preview_service.run_preview uses .one_or_none()
        for DbInstance lookup (returns None on no match, raises on multiple).
        Mirror first() since the fake store is single-item keyed by class —
        a multi-row match would be a test design bug, not a production bug."""
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
    """Fake DB session — supports add/query/commit/refresh 与 rollback."""

    store: dict[str, list[Any]] = field(default_factory=dict)
    commits: int = 0
    refreshes: int = 0

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
        """C16-F2b: 模拟 SQLAlchemy flush — 给 add 进去的对象分配 id。"""
        for cls_name, items in self.store.items():
            for item in items:
                if getattr(item, "id", None) is None:
                    item.id = self._next_id(cls_name)

    next_id_counter: dict[str, int] = None  # type: ignore[assignment]

    def _next_id(self, cls_name: str) -> int:
        if self.next_id_counter is None:
            object.__setattr__(self, "next_id_counter", {})
        counter = self.next_id_counter
        counter[cls_name] = counter.get(cls_name, 1000) + 1
        return counter[cls_name]

    def refresh(self, obj: Any) -> None:
        self.refreshes += 1
        if obj.id is None:
            obj.id = 9999  # fake DB autoincrement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_snapshot(
    *,
    snapshot_id: int = 1,
    instance_id: int = 1,
    db_type_code: str = "POSTGRESQL",
    status: str = AiSchemaSnapshotStatus.SUCCESS,
    is_current: bool = True,
    expires_in_hours: float = 24,
    allowed_schemas: Optional[list[str]] = None,
    allowed_tables: Optional[list[str]] = None,
    allowed_columns: Optional[dict[str, list[str]]] = None,
    denied_columns: Optional[list[str]] = None,
) -> AiSchemaSnapshot:
    now = datetime.now(tz=timezone.utc)
    snap = AiSchemaSnapshot(
        instance_id=instance_id,
        db_type_code=db_type_code,
        database_name="<default>",
        schema_name="public",
        status=status,
        allowed_schemas=allowed_schemas if allowed_schemas is not None else ["app"],
        allowed_tables=allowed_tables if allowed_tables is not None else ["app.users"],
        allowed_columns=allowed_columns
        if allowed_columns is not None
        else {"app.users": ["id", "name", "status"]},
        denied_columns=denied_columns if denied_columns is not None else [],
        is_current=is_current,
        snapshot_hash="a" * 64 if status == AiSchemaSnapshotStatus.SUCCESS else None,
        total_tables=1,
        total_columns=3,
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


def _patch_settings(monkeypatch, *, preview_enabled: bool = True, supported: Optional[list[str]] = None):
    """monkeypatch get_settings 返回的 Settings。

    ⚠️ 注意：不要直接修改 type(Settings).sql_supported_db_types — 那会污染
    全局 Settings 类，影响其他 test 文件（如 test_dify_service.py）。
    改用动态子类让 override 仅生效于当前 fake 实例。
    """
    if supported is None:
        fake = Settings(
            SECRET_KEY="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_USER="test",
            POSTGRES_HOST="localhost",
            POSTGRES_PORT=5432,
            POSTGRES_DB="test",
            SQLALCHEMY_DATABASE_URI="postgresql://test:test@localhost:5432/test",
            AI_SQL_PREVIEW_ENABLED=preview_enabled,
            AI_SQL_EXECUTION_ENABLED=False,
            DIFY_SQL_WORKFLOW_VERSION="2026-06-28-v1",
            DIFY_SQL_TIMEOUT_SECONDS=60.0,
            DIFY_BASE_URL="http://localhost/v1",
            DIFY_SQL_WORKFLOW_KEY="test-key",
        )
    else:
        # 动态子类：override property 仅影响该 fake 实例
        class _OverrideSettings(Settings):
            @property
            def sql_supported_db_types(self) -> list[str]:
                return list(supported)

        fake = _OverrideSettings(
            SECRET_KEY="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_USER="test",
            POSTGRES_HOST="localhost",
            POSTGRES_PORT=5432,
            POSTGRES_DB="test",
            SQLALCHEMY_DATABASE_URI="postgresql://test:test@localhost:5432/test",
            AI_SQL_PREVIEW_ENABLED=preview_enabled,
            AI_SQL_EXECUTION_ENABLED=False,
            DIFY_SQL_WORKFLOW_VERSION="2026-06-28-v1",
            DIFY_SQL_TIMEOUT_SECONDS=60.0,
            DIFY_BASE_URL="http://localhost/v1",
            DIFY_SQL_WORKFLOW_KEY="test-key",
        )

    monkeypatch.setattr(svc_mod, "get_settings", lambda: fake)


def _patch_schema_context(monkeypatch, available: bool = True, **kwargs):
    """monkeypatch AiSchemaContextService.build_schema_context.

    available=False 时可指定 reason；available=True 时返回完整 ctx。
    """
    from app.services.ai import ai_schema_context_service as ctx_mod

    if not available:
        reason = kwargs.get("reason", "no_snapshot")
        snapshot_id = kwargs.get("snapshot_id", None)

        def _fake_unavailable(db, *, instance_id, database_name=None):
            return {
                "available": False,
                "instance_id": instance_id,
                "db_type_code": kwargs.get("db_type_code", "POSTGRESQL"),
                "sql_dialect": None,
                "schema_context": None,
                "allowed_schemas": None,
                "allowed_tables": None,
                "allowed_columns": None,
                "denied_columns": None,
                "schema_snapshot_id": snapshot_id,
                "schema_policy_hash": None,
                "snapshot_hash": None,
                "collected_at": None,
                "expires_at": None,
                "total_tables": None,
                "total_columns": None,
                "reason": reason,
            }
        monkeypatch.setattr(
            ctx_mod.AiSchemaContextService,
            "build_schema_context",
            staticmethod(_fake_unavailable),
        )
        return

    snapshot_id = kwargs.get("snapshot_id", 1)
    allowed_tables = kwargs.get("allowed_tables", ["app.users"])
    allowed_columns = kwargs.get("allowed_columns", {"app.users": ["id", "name", "status"]})
    allowed_schemas = kwargs.get("allowed_schemas", ["app"])
    denied_columns = kwargs.get("denied_columns", [])
    db_type_code = kwargs.get("db_type_code", "POSTGRESQL")
    sql_dialect = kwargs.get("sql_dialect", "postgres")
    schema_context = kwargs.get("schema_context", "DB: POSTGRESQL\nAllowed tables: app.users(id, name, status)")

    def _fake_available(db, *, instance_id, database_name=None):
        return {
            "available": True,
            "instance_id": instance_id,
            "db_type_code": db_type_code,
            "sql_dialect": sql_dialect,
            "schema_context": schema_context,
            "allowed_schemas": allowed_schemas,
            "allowed_tables": allowed_tables,
            "allowed_columns": allowed_columns,
            "denied_columns": denied_columns,
            "schema_snapshot_id": snapshot_id,
            "schema_policy_hash": "deadbeef" * 8,
            "snapshot_hash": "a" * 64,
            "collected_at": datetime.now(tz=timezone.utc),
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=24),
            "total_tables": 1,
            "total_columns": 3,
            "reason": None,
        }
    monkeypatch.setattr(
        ctx_mod.AiSchemaContextService,
        "build_schema_context",
        staticmethod(_fake_available),
    )


def _patch_instance(db: _FakeSession, instance_id: int, db_type_code: str = "POSTGRESQL"):
    """向 fake session 注入 DbInstance + DbType 让 _resolve_instance 通过。

    ⚠️ 注意：必须把 instance 注入到「真正」调用 preview() 的那个 session 中，
    不能再创建一个临时 session 然后丢弃。
    """
    from app.models.dbops_assets import DbInstance, DbType

    db_type = DbType(id=1, type_code=db_type_code)
    instance = DbInstance(id=instance_id, db_type_id=1)
    db.store["DbInstance"] = [instance]
    db.store["DbType"] = [db_type]


def _patch_chat_session(
    db: _FakeSession,
    *,
    session_id: int = 1,
    instance_id: int = 1,
    user_id: Optional[Any] = uuid.UUID("00000000-0000-0000-0000-000000000001"),
    chat_mode: str = "instance_sql",
    bound_instance_id: Optional[int] = None,
    instance_status: str = "active",
):
    """C16-F2b — 向 fake session 注入 AiChatSession 让 _auth_check 通过。

    默认 session_id=1, chat_mode='instance_sql', bound_instance_id=instance_id,
    user_id 任意 UUID；user/instance 不一致场景可显式覆盖。

    顺带保证 DbInstance.status='active' 让 _auth_check 第 4 步通过（仅当
    store 中还没有 DbInstance 时；否则由调用方决定）。
    """
    from app.models.ai import AiChatSession

    session_obj = AiChatSession(
        session_code=f"FAKE-{session_id}",
        user_id=user_id,
        title="fake",
        chat_mode=chat_mode,
        bound_instance_id=bound_instance_id if bound_instance_id is not None else instance_id,
    )
    session_obj.id = session_id
    db.store["AiChatSession"] = [session_obj]
    # 默认同时保证 DbInstance.status='active' 让 _auth_check 第 4 步通过
    if "DbInstance" not in db.store:
        _patch_instance(db, instance_id)
    if instance_status != "active":
        # 显式标记 inactive 测试场景（覆盖默认 active）
        if "DbInstance" not in db.store:
            _patch_instance(db, instance_id)
        db.store["DbInstance"][0].status = instance_status


# C16-F2b: 测试统一 client_request_id（fake UUID，partial unique 不校验 fake session）
TEST_CLIENT_REQUEST_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _patch_dify_configured(monkeypatch, configured: bool = True):
    monkeypatch.setattr(DifyService, "is_configured", classmethod(lambda cls: configured))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestFeatureDisabled:
    def test_disabled_raises(self, monkeypatch):
        _patch_settings(monkeypatch, preview_enabled=False)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(FeatureDisabledError):
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )


class TestInstanceInactive:
    def test_instance_inactive_raises_chat_instance_not_accessible(self, monkeypatch):
        """C16-F2b：bound_instance 存在但 status='inactive' → ChatInstanceNotAccessibleError (404)。

        C12 旧版用 _resolve_instance 抛 InstanceNotFoundError；C16-F2b 把
        instance 校验合并到 auth 链 step 4（status='active' 检查），异常
        类型变为 ChatInstanceNotAccessibleError（语义上等价 + 复用 C16-F2a）。
        """
        from app.services.ai.ai_sql_preview_service import ChatInstanceNotAccessibleError

        _patch_settings(monkeypatch)
        db = _FakeSession()
        _patch_chat_session(db, instance_status="inactive")
        with pytest.raises(ChatInstanceNotAccessibleError):
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )


class TestUnsupportedDbType:
    def test_oracle_unsupported_raises(self, monkeypatch):
        _patch_settings(monkeypatch, supported=["POSTGRESQL"])

        db = _FakeSession()
        _patch_instance(db, 1, db_type_code="ORACLE")
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(UnsupportedDbTypeError):
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )


class TestSnapshotUnavailable:
    def test_no_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "no_snapshot"

    def test_pending_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="snapshot_not_success")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "snapshot_not_success"

    def test_expired_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="snapshot_expired")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "snapshot_expired"


class TestDifyNotConfigured:
    def test_dify_client_not_initialized_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch, configured=False)

        db = _FakeSession()
        _patch_instance(db, 1)
        _patch_chat_session(db)
        _patch_chat_session(db)
        with pytest.raises(DifyUnavailableError):
            AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )


class TestDifyTimeout:
    def test_dify_timeout_raises_504_error(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            mock.side_effect = DifyTimeoutErrorOrig("test timeout")
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            with pytest.raises(DifyTimeoutError_):
                AiSqlPreviewService.preview(
                    db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
                )


class TestDifyWorkflowFailed:
    def test_dify_workflow_failed_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            mock.side_effect = DifyWorkflowFailedErrorOrig("workflow failed")
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            with pytest.raises(DifyWorkflowFailedError_):
                AiSqlPreviewService.preview(
                    db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
                )


class TestDifyNoGeneratedSql:
    def test_dify_returns_no_sql_creates_rejected_audit(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            # 返回空 outputs
            mock.return_value = {
                "workflow_run_id": "wf-123",
                "outputs": {},
            }

            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
            assert result.audit is not None
            assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.REJECTED
            assert result.audit.preview_safety_reason is not None
            assert "generated_sql" in result.audit.preview_safety_reason
            assert db.commits == 1


class TestASTReject:
    def test_for_update_rejected_creates_audit(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            mock.return_value = {
                "workflow_run_id": "wf-123",
                "outputs": {"generated_sql": "SELECT id FROM app.users FOR UPDATE"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
            assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.REJECTED
            assert "FOR UPDATE" in (result.audit.preview_safety_reason or "")
            assert "FOR UPDATE" in " ".join(result.audit._preview_errors)

    def test_table_star_rejected_creates_audit(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            mock.return_value = {
                "workflow_run_id": "wf-123",
                "outputs": {"generated_sql": "SELECT u.* FROM app.users u"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
            assert result.audit.preview_safety_status == AiSqlAuditPreviewSafety.REJECTED


class TestHappyPath:
    def test_valid_sql_creates_passed_audit(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock:
            mock.return_value = {
                "workflow_run_id": "wf-123",
                "outputs": {"generated_sql": "SELECT id, name FROM app.users WHERE status = 'active'"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
            )
            audit = result.audit
            assert audit.preview_safety_status == AiSqlAuditPreviewSafety.PASSED
            assert audit.approved_sql is not None
            assert audit.approved_sql_hash is not None
            assert len(audit.approved_sql_hash) == 64
            assert audit.schema_snapshot_id == 1
            assert audit.schema_policy_hash == "deadbeef" * 8
            assert audit.dify_workflow_run_id == "wf-123"
            assert audit.safety_policy_version == AiSqlPreviewService.SAFETY_POLICY_VERSION
            assert audit.execution_status == AiSqlAuditExecutionStatus.NOT_REQUESTED
            assert audit.preview_safety_reason is None
            assert db.commits == 1


class TestHashStability:
    def test_approved_sql_hash_stable(self, monkeypatch):
        """approved_sql_hash 在相同 SQL 输入下保持稳定（plan §5 P0-4 核心不变量）。"""
        _patch_settings(monkeypatch)
        _patch_instance(_FakeSession(), 1)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        def _capture_hashes():
            with patch.object(DifyService, "run_sql_workflow") as mock:
                mock.return_value = {
                    "workflow_run_id": "wf-123",
                    "outputs": {"generated_sql": "SELECT id FROM app.users WHERE status = 'active'"},
                }
                db1 = _FakeSession()
                _patch_instance(db1, 1)
                _patch_chat_session(db1)
                r1 = AiSqlPreviewService.preview(
                    db1, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
                )
                db2 = _FakeSession()
                _patch_instance(db2, 1)
                _patch_chat_session(db2)
                r2 = AiSqlPreviewService.preview(
                    db2, session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1, database_name=None, user_question="q",
                )
                return r1.audit.approved_sql_hash, r2.audit.approved_sql_hash

        h1, h2 = _capture_hashes()
        assert h1 == h2
        assert len(h1) == 64


class TestHelpers:
    def test_extract_sql_block_from_markdown(self):
        text = "以下是 SQL：\n```sql\nSELECT id FROM app.users\n```\n祝好"
        sql = AiSqlPreviewService._extract_sql_block(text)
        assert sql == "SELECT id FROM app.users"

    def test_extract_sql_block_returns_none_if_no_marker(self):
        assert AiSqlPreviewService._extract_sql_block("SELECT 1") is None

    def test_extract_generated_sql_from_outputs(self):
        response = {
            "workflow_run_id": "wf-1",
            "outputs": {"generated_sql": "SELECT 1"},
        }
        sql = AiSqlPreviewService._extract_generated_sql(response)
        assert sql == "SELECT 1"

    def test_extract_generated_sql_from_answer_markdown(self):
        response = {
            "answer": "下面是 SQL：\n```sql\nSELECT 2\n```",
        }
        sql = AiSqlPreviewService._extract_generated_sql(response)
        assert sql == "SELECT 2"

    def test_extract_generated_sql_empty(self):
        response = {"workflow_run_id": "wf-1", "outputs": {}}
        assert AiSqlPreviewService._extract_generated_sql(response) is None

    def test_normalize_current_page_allowlist(self):
        assert AiSqlPreviewService._normalize_current_page("ai_chat") == "ai_chat"
        assert AiSqlPreviewService._normalize_current_page("instance_detail") == "instance_detail"
        assert AiSqlPreviewService._normalize_current_page("malicious_page") == "ai_chat"
        assert AiSqlPreviewService._normalize_current_page(None) == "ai_chat"


class TestCanonicalJsonHash:
    def test_canonical_hash_stable(self):
        h1 = canonical_json_hash({"a": 1, "b": 2})
        h2 = canonical_json_hash({"b": 2, "a": 1})  # 顺序不影响
        assert h1 == h2
        assert len(h1) == 64

    def test_canonical_hash_changes_with_value(self):
        h1 = canonical_json_hash({"a": 1})
        h2 = canonical_json_hash({"a": 2})
        assert h1 != h2


# =============================================================================
# Phase 3.6 C13 — Layer 1 集成 + Dify Code 节点 JSON 解析（plan §5 Layer 1）
# =============================================================================


class TestLayer1Integration:
    """Layer 1 正则预检在 AiSqlPreviewService.preview() 流程中的集成测试。

    验证：
    - 命中 → 构造 rejected audit 落库 + Dify **不**被调
    - 未命中 → 正常进 Dify
    - 关闭开关（LAYER1_PRECHECK_ENABLED=False） → 跳过预检
    """

    def test_layer1_hit_en_rejected_audit_no_dify_call(self, monkeypatch):
        """英文 DROP 命中 → rejected audit + Dify 不被调。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="DROP TABLE app.users",
            )
            # Dify 未被调
            mock_dify.assert_not_called()
            # rejected audit 落库
            assert result.audit.preview_safety_status == "rejected"
            assert result.audit.generated_sql is None
            assert result.audit.preview_safety_reason is not None
            assert "DROP" in result.audit.preview_safety_reason
            # layer1 标记
            assert getattr(result.audit, "_preview_layer1_blocked", False) is True
            assert getattr(result.audit, "_preview_layer1_keyword", None) == "DROP"

    def test_layer1_hit_cn_rejected_audit(self, monkeypatch):
        """中文「删除」命中 → rejected audit。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="把过期数据删除",
            )
            mock_dify.assert_not_called()
            assert result.audit.preview_safety_status == "rejected"
            assert "删除" in result.audit.preview_safety_reason

    def test_layer1_miss_calls_dify(self, monkeypatch):
        """未命中 → 正常进 Dify。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            mock_dify.return_value = {
                "workflow_run_id": "wf-1",
                "outputs": {"generated_sql": "SELECT id FROM app.users"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="查询活跃用户ID",
            )
            mock_dify.assert_called_once()
            assert result.audit.preview_safety_status == "passed"

    def test_layer1_disabled_calls_dify_even_on_hit(self, monkeypatch):
        """LAYER1_PRECHECK_ENABLED=False 时即使命中也调 Dify。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        # 关闭 layer1
        monkeypatch.setattr(AiSqlPreviewService, "LAYER1_PRECHECK_ENABLED", False)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            mock_dify.return_value = {
                "workflow_run_id": "wf-2",
                "outputs": {"generated_sql": "SELECT 1 FROM app.users"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="DROP TABLE x",  # 即使命中也调 Dify
            )
            mock_dify.assert_called_once()
            # passed audit（Dify 返回了合法 SQL）
            assert result.audit.preview_safety_status == "passed"


class TestCodeNodePayload:
    """C13 — Dify Code 节点结构化 JSON 解析测试。"""

    def test_structured_outputs_dict(self):
        """outputs 是 dict + generated_sql 字段 → structured 模式。"""
        resp = {
            "workflow_run_id": "wf-1",
            "outputs": {
                "generated_sql": "SELECT id FROM app.users",
                "warnings": ["敏感字段命中: email"],
                "confidence": 0.85,
                "table_refs": ["public.users"],
                "explanation": "查询用户ID",
            },
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "structured"
        assert result["generated_sql"] == "SELECT id FROM app.users"
        assert result["warnings"] == ["敏感字段命中: email"]
        assert result["confidence"] == 0.85
        assert result["table_refs"] == ["public.users"]
        assert result["explanation"] == "查询用户ID"

    def test_structured_outputs_string_json(self):
        """outputs 是字符串化的 JSON → 解析后 structured 模式。"""
        resp = {
            "workflow_run_id": "wf-2",
            "outputs": '{"generated_sql": "SELECT id FROM app.users", "warnings": []}',
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "structured"
        assert result["generated_sql"] == "SELECT id FROM app.users"

    def test_outputs_string_non_json_fallback(self):
        """outputs 是非 JSON 字符串 → fallback 到 plain text 提取。"""
        resp = {
            "workflow_run_id": "wf-3",
            "outputs": "```sql\nSELECT id FROM app.users\n```",
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "fallback_plain_text"
        assert "SELECT" in result["generated_sql"]

    def test_outputs_empty_fallback_to_answer(self):
        """outputs 为空 dict → fallback 到 answer 字段的 ```sql``` 块。"""
        resp = {
            "workflow_run_id": "wf-4",
            "outputs": {},
            "answer": "Here's the SQL:\n```sql\nSELECT id FROM app.users\n```",
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "fallback_plain_text"
        assert "SELECT" in result["generated_sql"]

    def test_outputs_missing_fallback_to_sql_key(self):
        """outputs 缺 + 顶层有 sql 字段 → fallback。"""
        resp = {
            "workflow_run_id": "wf-5",
            "outputs": {"foo": "bar"},  # 无 generated_sql
            "sql": "SELECT 1 FROM app.users",
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "fallback_plain_text"
        assert result["generated_sql"] == "SELECT 1 FROM app.users"

    def test_outputs_dict_missing_optional_fields(self):
        """structured 模式 + 缺 warnings / confidence / table_refs → 默认值。"""
        resp = {
            "workflow_run_id": "wf-6",
            "outputs": {"generated_sql": "SELECT id FROM app.users"},
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "structured"
        assert result["generated_sql"] == "SELECT id FROM app.users"
        assert result["warnings"] == []
        assert result["confidence"] is None
        assert result["table_refs"] == []
        assert result["explanation"] is None

    def test_empty_response_returns_missing(self):
        """空 dict → missing 模式。"""
        result = AiSqlPreviewService._parse_code_node_payload({})
        assert result["parse_mode"] == "missing"
        assert result["generated_sql"] is None

    def test_non_dict_response_returns_missing(self):
        """非 dict → missing 模式。"""
        result = AiSqlPreviewService._parse_code_node_payload(None)  # type: ignore[arg-type]
        assert result["parse_mode"] == "missing"
        result = AiSqlPreviewService._parse_code_node_payload("string")  # type: ignore[arg-type]
        assert result["parse_mode"] == "missing"

    def test_warnings_string_to_list(self):
        """warnings 是单字符串 → 列表化。"""
        resp = {
            "workflow_run_id": "wf-7",
            "outputs": {
                "generated_sql": "SELECT 1",
                "warnings": "敏感字段命中: password",
            },
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["warnings"] == ["敏感字段命中: password"]

    def test_nested_generated_sql_dict(self):
        """防御：generated_sql 是 dict（不正常但要 robust）。"""
        resp = {
            "workflow_run_id": "wf-8",
            "outputs": {
                "generated_sql": {"sql": "SELECT 1 FROM app.users", "extra": "ignored"},
            },
        }
        result = AiSqlPreviewService._parse_code_node_payload(resp)
        assert result["parse_mode"] == "structured"
        assert result["generated_sql"] == "SELECT 1 FROM app.users"


class TestCodeNodePayloadIntegration:
    """C13 — Code 节点 payload 解析与 audit 集成的端到端测试。"""

    def test_structured_warnings_merged_into_audit(self, monkeypatch):
        """Dify Code 节点返回 warnings → 合并到 audit._preview_warnings。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            mock_dify.return_value = {
                "workflow_run_id": "wf-int-1",
                "outputs": {
                    "generated_sql": "SELECT id FROM app.users",
                    "warnings": ["敏感字段命中: email"],  # Dify 提示
                    "table_refs": ["public.users"],
                },
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="查询用户列表",
            )
            # passed audit + warnings 合并（仅来自 Dify Code 节点）
            assert result.audit.preview_safety_status == "passed"
            warnings = getattr(result.audit, "_preview_warnings", [])
            assert "敏感字段命中: email" in warnings

    def test_no_warnings_returns_empty_list(self, monkeypatch):
        """Dify 不返回 warnings + AST 不命中 sensitive → 空 warnings 列表。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            mock_dify.return_value = {
                "workflow_run_id": "wf-int-2",
                "outputs": {"generated_sql": "SELECT id FROM app.users"},
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="查询用户ID",
            )
            assert result.audit.preview_safety_status == "passed"
            assert getattr(result.audit, "_preview_warnings", []) == []

    def test_dify_returns_no_sql_rejected_with_code_warnings(self, monkeypatch):
        """Dify 没生成 SQL 但带 warnings → rejected audit + warnings 保留。"""
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch)

        with patch.object(DifyService, "run_sql_workflow") as mock_dify:
            mock_dify.return_value = {
                "workflow_run_id": "wf-int-3",
                "outputs": {
                    # 没 generated_sql 字段
                    "warnings": ["Dify 内部警告: 模型不确定"],
                },
            }
            db = _FakeSession()
            _patch_instance(db, 1)
            _patch_chat_session(db)
            _patch_chat_session(db)
            result = AiSqlPreviewService.preview(
                db,
                session_id=1, client_request_id=TEST_CLIENT_REQUEST_ID, instance_id=1,
                database_name=None,
                user_question="查询用户列表",
            )
            assert result.audit.preview_safety_status == "rejected"
            assert result.audit.generated_sql is None
            warnings = getattr(result.audit, "_preview_warnings", [])
            assert "Dify 内部警告: 模型不确定" in warnings