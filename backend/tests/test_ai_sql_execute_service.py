"""Phase 3.6B1 C14 — AiSqlExecuteService 单元测试.

覆盖（plan §13 + C14 plan §11 错误码）：
  1. feature disabled (AI_SQL_EXECUTION_ENABLED=false) → FeatureDisabledError (503)
  2. audit_id 不存在 → AuditNotFoundError (404)
  3. audit.preview_safety_status=rejected → AuditNotPassedError (409)
  4. audit.approved_sql 为空 → AuditNotPassedError (409)
  5. audit.execution_status=running 且未 force → AuditAlreadyRunningError (409)
  6. snapshot 不存在 → SnapshotPolicyMismatchError (409)
  7. snapshot.status=pending → SnapshotPolicyMismatchError (409)
  8. snapshot.snapshot_hash 与 audit.schema_policy_hash 不一致 → SnapshotPolicyMismatchError (409)
  9. AST 二次校验拒绝 (FOR UPDATE) → AuditUnsafeOnExecuteError (422)
  10. AST 二次校验通过 + approved_sql_hash 一致 → 成功 launch
  11. approved_sql_hash 不一致 → AuditUnsafeOnExecuteError (422)
  12. AWX launch 成功 → audit.execution_status='running' + collector_run_id/item_id
  13. AWX launch 失败 → AwxLaunchError (502) + audit.execution_status='failed'
  14. get_execution_status: 不存在 → AuditNotFoundError
  15. get_execution_status: 存在 → 返回 audit 对象
  16. force=True 跳过 pending/running 校验 → 成功 launch

策略：FakeSession + monkeypatch AwxService.launch_job + SqlSafetyService，
      不连真实 DB / Dify / AWX。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings
from app.models.ai import (
    AiSchemaSnapshot,
    AiSchemaSnapshotStatus,
    AiSqlAudit,
    AiSqlAuditExecutionSafety,
    AiSqlAuditExecutionStatus,
    AiSqlAuditPreviewSafety,
)
from app.services.ai import ai_sql_execute_service as svc_mod
from app.services.ai.ai_sql_execute_service import (
    AiSqlExecuteService,
    AuditAlreadyRunningError,
    AuditNotFoundError,
    AuditNotPassedError,
    AuditUnsafeOnExecuteError,
    AwxLaunchError,
    FeatureDisabledError,
    SnapshotPolicyMismatchError,
)
from app.services.awx_service import AwxServiceError
from app.services.sql_safety_service import SqlSafetyService


# ---------------------------------------------------------------------------
# Fake session (与 test_ai_sql_preview_service.py 风格一致)
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

    def with_for_update(self) -> "_FakeQueryResult":
        return self

    def _matches(self, item: Any) -> bool:
        for f in self.filters:
            actual = getattr(item, f.field, None)
            if f.op == "==":
                if actual != f.value:
                    return False
        return True


@dataclass
class _FakeExecuteResult:
    rowcount: int = 0


@dataclass
class _FakeSession:
    """Fake DB session — supports add/query/commit/refresh/rollback/execute/flush."""

    store: dict[str, list[Any]] = field(default_factory=dict)
    commits: int = 0
    refreshes: int = 0
    flushes: int = 0
    _id_counter: int = 9000

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    def add(self, obj: Any) -> None:
        cls_name = type(obj).__name__
        self.store.setdefault(cls_name, []).append(obj)

    def query(self, model: Any) -> _FakeQueryResult:
        cls_name = model.__name__
        return _FakeQueryResult(items=list(self.store.get(cls_name, [])))

    def execute(self, stmt: Any) -> _FakeExecuteResult:
        return _FakeExecuteResult(rowcount=1)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def flush(self) -> None:
        self.flushes += 1
        # 给刚 add 的、没有 id 的对象分配 autoincrement id
        for items in self.store.values():
            for obj in items:
                if getattr(obj, "id", None) is None:
                    obj.id = self._next_id()

    def refresh(self, obj: Any) -> None:
        self.refreshes += 1
        if obj.id is None:
            obj.id = self._next_id()


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
    allowed_tables: Optional[list[str]] = None,
    allowed_columns: Optional[dict[str, list[str]]] = None,
    denied_columns: Optional[list[str]] = None,
    snapshot_hash: Optional[str] = None,
) -> AiSchemaSnapshot:
    now = datetime.now(tz=timezone.utc)
    snap = AiSchemaSnapshot(
        instance_id=instance_id,
        db_type_code=db_type_code,
        database_name="<default>",
        schema_name="public",
        status=status,
        allowed_schemas=["app"],
        allowed_tables=allowed_tables if allowed_tables is not None else ["app.users"],
        allowed_columns=allowed_columns
        if allowed_columns is not None
        else {"app.users": ["id", "name", "status"]},
        denied_columns=denied_columns if denied_columns is not None else [],
        is_current=is_current,
        snapshot_hash=snapshot_hash if snapshot_hash is not None else "a" * 64,
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


def _make_audit(
    *,
    audit_id: int = 100,
    instance_id: int = 1,
    db_type_code: str = "POSTGRESQL",
    approved_sql: str = "SELECT id FROM app.users",
    preview_status: str = AiSqlAuditPreviewSafety.PASSED,
    exec_status: str = AiSqlAuditExecutionStatus.NOT_REQUESTED,
    schema_snapshot_id: Optional[int] = 1,
    schema_policy_hash: Optional[str] = None,
    approved_sql_hash: Optional[str] = None,
) -> AiSqlAudit:
    if schema_policy_hash is None:
        schema_policy_hash = "a" * 64
    if approved_sql_hash is None:
        approved_sql_hash = SqlSafetyService.compute_sql_hash(approved_sql)

    audit = AiSqlAudit(
        instance_id=instance_id,
        db_type_code=db_type_code,
        user_question="q",
        generated_sql=approved_sql,
        generated_sql_hash=approved_sql_hash,
        approved_sql=approved_sql,
        approved_sql_hash=approved_sql_hash,
        preview_safety_status=preview_status,
        preview_safety_reason=None if preview_status == AiSqlAuditPreviewSafety.PASSED else "x",
        previewed_at=datetime.now(tz=timezone.utc),
        schema_snapshot_id=schema_snapshot_id,
        schema_policy_hash=schema_policy_hash,
        execution_status=exec_status,
        safety_policy_version="2026-06-28-v1",
        sql_workflow_version="2026-06-28-v1",
        created_at=datetime.now(tz=timezone.utc),
    )
    audit.id = audit_id
    return audit


def _patch_settings(monkeypatch, *, exec_enabled: bool = True):
    """monkeypatch get_settings 返回 enabled 设置。"""
    fake = Settings(
        SECRET_KEY="test",
        POSTGRES_PASSWORD="test",
        POSTGRES_USER="test",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="test",
        SQLALCHEMY_DATABASE_URI="postgresql://test:test@localhost:5432/test",
        AI_SQL_PREVIEW_ENABLED=True,
        AI_SQL_EXECUTION_ENABLED=exec_enabled,
        DIFY_SQL_WORKFLOW_VERSION="2026-06-28-v1",
        DIFY_SQL_TIMEOUT_SECONDS=60.0,
        DIFY_BASE_URL="http://localhost/v1",
        DIFY_SQL_WORKFLOW_KEY="test-key",
        AWX_URL="http://awx.local:30080",
        AWX_USER="admin",
        AWX_PASSWORD="x",
        AWX_COLLECTOR_JOB_TEMPLATE_ID=10,
        AWX_REQUEST_TIMEOUT=30,
        AWX_PREBOUND_CREDENTIAL_IDS="",
        COLLECTOR_CALLBACK_URL="http://localhost:60801/api/v1/collector/callback/",
    )
    monkeypatch.setattr(svc_mod, "get_settings", lambda: fake)


def _patch_awx_launch(monkeypatch, *, awx_job_id: int = 555, raise_exc: Optional[Exception] = None):
    """monkeypatch AwxService.launch_job。"""
    if raise_exc:
        def fake_launch(**kwargs):
            raise raise_exc
        monkeypatch.setattr(svc_mod.AwxService, "launch_job", staticmethod(fake_launch))
    else:
        def fake_launch(**kwargs):
            return {"awx_job_id": awx_job_id, "awx_job_url": f"http://awx/#/jobs/{awx_job_id}"}
        monkeypatch.setattr(svc_mod.AwxService, "launch_job", staticmethod(fake_launch))


def _patch_credential_resolver(monkeypatch, *, with_credential: bool = False):
    """monkeypatch CredentialResolverService.resolve_for_item。"""
    def fake_resolve(db, *, target_scope, asset, check_code):
        if with_credential:
            return {
                "credential_profile_id": 1,
                "profile_code": "TEST_DB",
                "awx_credential_id": 4,
                "binding_role": "primary",
                "credential_type": "ssh",
            }
        return None
    monkeypatch.setattr(svc_mod.CredentialResolverService, "resolve_for_item", staticmethod(fake_resolve))


def _patch_safety(monkeypatch, *, valid: bool = True, errors: Optional[list[str]] = None):
    """monkeypatch SqlSafetyService.validate_with_ast。"""
    def fake_validate(**kwargs):
        return {
            "valid": valid,
            "errors": errors if errors is not None else ([] if valid else ["FOR UPDATE not allowed"]),
            "warnings": [],
            "approved_sql": kwargs.get("sql_text"),
            "approved_sql_hash": "deadbeef" * 8,
        }
    monkeypatch.setattr(svc_mod.SqlSafetyService, "validate_with_ast", staticmethod(fake_validate))


def _inject_target(db: _FakeSession, audit: AiSqlAudit) -> None:
    """注入 server + instance 到 FakeSession（绕开 DB query）。"""
    from app.models.dbops_assets import DbInstance, Server
    server = Server(id=1, ip_address="10.0.0.1")
    instance = DbInstance(
        id=audit.instance_id, server_id=1, port=5432, db_type_id=1,
    )
    db.store["Server"] = [server]
    db.store["DbInstance"] = [instance]


# ---------------------------------------------------------------------------
# 1. FeatureDisabledError
# ---------------------------------------------------------------------------
class TestFeatureDisabled:
    def test_disabled_raises_503(self, monkeypatch):
        _patch_settings(monkeypatch, exec_enabled=False)

        db = _FakeSession()
        with pytest.raises(FeatureDisabledError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=100, force=False)
        assert "AI_SQL_EXECUTION_ENABLED=false" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. AuditNotFoundError
# ---------------------------------------------------------------------------
class TestAuditNotFound:
    def test_missing_audit_raises_404(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()  # no audit inserted
        with pytest.raises(AuditNotFoundError):
            AiSqlExecuteService.execute(db, audit_id=999, force=False)


# ---------------------------------------------------------------------------
# 3. AuditNotPassedError
# ---------------------------------------------------------------------------
class TestAuditNotPassed:
    def test_rejected_audit_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        audit = _make_audit(preview_status=AiSqlAuditPreviewSafety.REJECTED)
        db.store["AiSqlAudit"] = [audit]

        with pytest.raises(AuditNotPassedError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert "rejected" in str(exc_info.value).lower() or "only 'passed'" in str(exc_info.value)

    def test_empty_approved_sql_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        audit = _make_audit(approved_sql="   ")
        audit.approved_sql_hash = SqlSafetyService.compute_sql_hash("   ")
        db.store["AiSqlAudit"] = [audit]

        with pytest.raises(AuditNotPassedError):
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)


# ---------------------------------------------------------------------------
# 4. AuditAlreadyRunningError
# ---------------------------------------------------------------------------
class TestAuditAlreadyRunning:
    def test_running_without_force_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        audit = _make_audit(exec_status=AiSqlAuditExecutionStatus.RUNNING)
        db.store["AiSqlAudit"] = [audit]

        with pytest.raises(AuditAlreadyRunningError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert "use force=true" in str(exc_info.value)

    def test_running_with_force_proceeds(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=777)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        audit = _make_audit(exec_status=AiSqlAuditExecutionStatus.RUNNING)
        snap = _make_snapshot(snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=True)
        assert result.audit.id == audit.id
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING


# ---------------------------------------------------------------------------
# 5. SnapshotPolicyMismatchError
# ---------------------------------------------------------------------------
class TestSnapshotPolicyMismatch:
    def test_no_snapshot_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        audit = _make_audit(schema_snapshot_id=999, schema_policy_hash="a" * 64)
        db.store["AiSqlAudit"] = [audit]

        with pytest.raises(SnapshotPolicyMismatchError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert exc_info.value.reason == "snapshot_not_found"

    def test_snapshot_hash_mismatch_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1, snapshot_hash="b" * 64)
        audit = _make_audit(schema_snapshot_id=1, schema_policy_hash="a" * 64)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]

        with pytest.raises(SnapshotPolicyMismatchError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert exc_info.value.reason == "policy_hash_mismatch"

    def test_snapshot_pending_raises_409(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1, status=AiSchemaSnapshotStatus.PENDING)
        audit = _make_audit(schema_snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]

        with pytest.raises(SnapshotPolicyMismatchError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert exc_info.value.reason == "snapshot_not_usable"


# ---------------------------------------------------------------------------
# 6. AuditUnsafeOnExecuteError
# ---------------------------------------------------------------------------
class TestAuditUnsafeOnExecute:
    def test_ast_rejects_raises_422(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch, valid=False, errors=["FOR UPDATE not allowed"])

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]

        with pytest.raises(AuditUnsafeOnExecuteError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert exc_info.value.errors == ["FOR UPDATE not allowed"]
        assert audit.execution_safety_status == AiSqlAuditExecutionSafety.REJECTED
        assert audit.error_message is not None

    def test_approved_sql_hash_mismatch_raises_422(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch, valid=True)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1)
        audit.approved_sql_hash = "wrong_hash_00000000000000000000000000000000000000000000000000000000"
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]

        with pytest.raises(AuditUnsafeOnExecuteError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert "approved_sql_hash_mismatch" in exc_info.value.errors


# ---------------------------------------------------------------------------
# 7. Happy path — AWX launch 成功
# ---------------------------------------------------------------------------
class TestHappyPath:
    def test_awx_launch_success(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=888)
        _patch_credential_resolver(monkeypatch, with_credential=True)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert result.audit.id == audit.id
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING
        assert result.audit.collector_run_id is not None
        assert result.audit.collector_run_item_id is not None
        assert result.audit.executed_at is not None
        assert audit.execution_safety_status == AiSqlAuditExecutionSafety.PASSED

    def test_awx_launch_failure_marks_failed(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, raise_exc=AwxServiceError("AWX 503 unreachable"))
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        with pytest.raises(AwxLaunchError) as exc_info:
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        assert "AWX 503" in str(exc_info.value)
        assert audit.execution_status == AiSqlAuditExecutionStatus.FAILED
        assert "AWX launch failed" in (audit.error_message or "")


# ---------------------------------------------------------------------------
# 8. get_execution_status
# ---------------------------------------------------------------------------
class TestGetExecutionStatus:
    def test_missing_audit_raises_404(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        with pytest.raises(AuditNotFoundError):
            AiSqlExecuteService.get_execution_status(db, audit_id=999)

    def test_returns_audit(self, monkeypatch):
        _patch_settings(monkeypatch)
        db = _FakeSession()
        audit = _make_audit(exec_status=AiSqlAuditExecutionStatus.SUCCESS, audit_id=42)
        db.store["AiSqlAudit"] = [audit]
        result = AiSqlExecuteService.get_execution_status(db, audit_id=42)
        assert result.id == 42
        assert result.execution_status == AiSqlAuditExecutionStatus.SUCCESS