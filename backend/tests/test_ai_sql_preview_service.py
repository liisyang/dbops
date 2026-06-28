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
        with pytest.raises(FeatureDisabledError):
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
            )


class TestInstanceNotFound:
    def test_missing_instance_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        # 不注入 DbInstance → _resolve_instance 抛 InstanceNotFoundError

        db = _FakeSession()
        with pytest.raises(InstanceNotFoundError):
            AiSqlPreviewService.preview(
                db, instance_id=999, database_name=None, user_question="q",
            )


class TestUnsupportedDbType:
    def test_oracle_unsupported_raises(self, monkeypatch):
        _patch_settings(monkeypatch, supported=["POSTGRESQL"])

        db = _FakeSession()
        _patch_instance(db, 1, db_type_code="ORACLE")
        with pytest.raises(UnsupportedDbTypeError):
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
            )


class TestSnapshotUnavailable:
    def test_no_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="no_snapshot")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "no_snapshot"

    def test_pending_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="snapshot_not_success")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "snapshot_not_success"

    def test_expired_snapshot_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=False, reason="snapshot_expired")
        _patch_dify_configured(monkeypatch)

        db = _FakeSession()
        _patch_instance(db, 1)
        with pytest.raises(SnapshotUnavailableError) as exc_info:
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
            )
        assert exc_info.value.reason == "snapshot_expired"


class TestDifyNotConfigured:
    def test_dify_client_not_initialized_raises(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_schema_context(monkeypatch, available=True)
        _patch_dify_configured(monkeypatch, configured=False)

        db = _FakeSession()
        _patch_instance(db, 1)
        with pytest.raises(DifyUnavailableError):
            AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
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
            with pytest.raises(DifyTimeoutError_):
                AiSqlPreviewService.preview(
                    db, instance_id=1, database_name=None, user_question="q",
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
            with pytest.raises(DifyWorkflowFailedError_):
                AiSqlPreviewService.preview(
                    db, instance_id=1, database_name=None, user_question="q",
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
            result = AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
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
            result = AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
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
            result = AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
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
            result = AiSqlPreviewService.preview(
                db, instance_id=1, database_name=None, user_question="q",
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
                r1 = AiSqlPreviewService.preview(
                    db1, instance_id=1, database_name=None, user_question="q",
                )
                db2 = _FakeSession()
                _patch_instance(db2, 1)
                r2 = AiSqlPreviewService.preview(
                    db2, instance_id=1, database_name=None, user_question="q",
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