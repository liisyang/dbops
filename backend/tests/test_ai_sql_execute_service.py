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
    AiChatMessage,
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
    AuditOwnershipError,
    AuditResultNotAvailableError,
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


def _eval_fake_update(stmt: Any, store: dict[str, list[Any]]) -> int:
    """评估 SQLAlchemy update() 语句对 fake store 的影响；返回受影响 row 数。

    仅支持形如：
        update(<Model>).where(<col> <op> <val>).where(...).values(<col>=<val>, ...)
    不支持 JOIN / 子查询；够覆盖 C16-F1 测试。

    通过 `stmt.compile(compile_kwargs={"literal_binds": True})` 渲染成
    字符串 SQL（如 `UPDATE dbops.ai_sql_audit SET awx_job_id=1234
    WHERE id = 100 AND awx_job_id IS NULL`），再字符串解析即可。
    """
    if not (hasattr(stmt, "_where_criteria") and hasattr(stmt, "_values") and hasattr(stmt, "table")):
        return 0
    from sqlalchemy.dialects import postgresql as _pg_dialect
    try:
        compiled = stmt.compile(dialect=_pg_dialect.dialect(), compile_kwargs={"literal_binds": True})
        sql_str = str(compiled).replace("\n", " ")
    except Exception:
        return 0
    table = stmt.table
    model_cls = getattr(table, "mapper", None)
    if model_cls is None:
        from app.models.ai import AiSqlAudit as _AuditMdl
        model_cls = _AuditMdl
    cls_name = model_cls.__name__
    items = store.get(cls_name, [])
    # 解析 SET 子句
    set_part, _, where_part = sql_str.partition(" WHERE ")
    set_dict: dict[str, Any] = {}
    for tok in set_part.split("SET ", 1)[-1].split(", "):
        if "=" in tok:
            col, val = tok.split("=", 1)
            col_key = col.strip().split(".")[-1]
            v = val.strip()
            if v.upper() == "NULL":
                set_dict[col_key] = None
            else:
                try:
                    set_dict[col_key] = int(v)
                except ValueError:
                    set_dict[col_key] = v.strip("'")
    # 解析 WHERE 子句（每个条件为 AND 分隔）
    matched_indexes: list[int] = []
    conds = [c.strip() for c in where_part.split(" AND ")] if where_part else []
    for idx, item in enumerate(items):
        ok = True
        for cond in conds:
            if " = " in cond and " IS " not in cond:
                col, val = cond.split(" = ", 1)
                col_key = col.strip().split(".")[-1]
                v = val.strip()
                if v.upper() == "NULL":
                    expected: Any = None
                else:
                    try:
                        expected = int(v)
                    except ValueError:
                        expected = v.strip("'")
                if getattr(item, col_key, None) != expected:
                    ok = False
                    break
            elif cond.endswith(" IS NULL"):
                col_key = cond[: -len(" IS NULL")].strip().split(".")[-1]
                if getattr(item, col_key, None) is not None:
                    ok = False
                    break
        if ok:
            matched_indexes.append(idx)
    for idx in matched_indexes:
        item = items[idx]
        for col_key, col_val in set_dict.items():
            setattr(item, col_key, col_val)
    return len(matched_indexes)


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
        rowcount = _eval_fake_update(stmt, self.store)
        return _FakeExecuteResult(rowcount=rowcount)

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
    user_id: Optional[Any] = None,
    session_id: Optional[int] = None,
) -> AiSqlAudit:
    if schema_policy_hash is None:
        schema_policy_hash = "a" * 64
    if approved_sql_hash is None:
        approved_sql_hash = SqlSafetyService.compute_sql_hash(approved_sql)

    audit = AiSqlAudit(
        instance_id=instance_id,
        db_type_code=db_type_code,
        user_question="q",
        user_id=user_id,
        session_id=session_id,
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


@dataclass
class _FakeRequester:
    """请求者：模拟 current_user（带 id 字段）。"""

    id: Any
    username: str = "tester"


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


def _make_chat_message(
    *,
    message_id: int = 888,
    session_id: int = 50,
    message_type: str = "sql_result",
    content: Optional[str] = None,
    user_id: Optional[Any] = None,
) -> AiChatMessage:
    """构造 ai_chat_message（用于 Result API 数据源 sql_result 落库）。"""
    msg = AiChatMessage(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        message_type=message_type,
        status="completed",
        content=content,
        parent_message_id=None,
        metadata_json={},
        attempt_count=0,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    msg.id = message_id
    return msg


def _make_run_item(
    *,
    run_item_id: int = 777,
    raw_result: Optional[dict[str, Any]] = None,
) -> Any:
    """构造 CollectorRunItem（用于 Result API fallback 数据源 raw_result）。"""
    from app.models.dbops_assets import CollectorRunItem as _CRI

    item = _CRI(
        collector_run_id=1,
        run_id="ai-sql-test",
        item_key="ai_sql:100:1",
        check_code="DB_READONLY_SQL_EXEC",
        target_scope="db_instance",
        server_id=1,
        db_instance_id=1,
        target_host="10.0.0.1",
        target_port=5432,
        status="verified",
        raw_result=raw_result if raw_result is not None else {},
    )
    item.id = run_item_id
    return item


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


# ---------------------------------------------------------------------------
# 9. C16-F1 — awx_job_id 回填
# ---------------------------------------------------------------------------
class TestAwxJobIdBackfill:
    """Phase 3.6 C16-F1：AWX launch 成功后回填 ai_sql_audit.awx_job_id。

    验证点：
    - 首次 launch：audit.awx_job_id 被写入；执行成功
    - 已存在不覆盖：audit.awx_job_id 已有值时（callback/重试场景），
      service 不应再覆盖（DB IS NULL guard + ORM 仅当 None 时刷新）
    """

    def test_awx_job_id_backfilled_on_first_launch(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=1234)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1, audit_id=100)
        assert audit.awx_job_id is None  # 前置条件：launch 前为 None
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # C16-F1: 首次 launch 应回填
        assert result.audit.awx_job_id == 1234
        assert audit.awx_job_id == 1234

    def test_awx_job_id_not_overwritten_when_exists(self, monkeypatch):
        """幂等：audit.awx_job_id 已有值（callback 重试场景）时不覆盖。

        前置：audit.awx_job_id = 9999（模拟已 callback 写入的值）
        操作：execute（force=True 跳过 pending/running 校验）
        期望：DB IS NULL guard 让 UPDATE 不生效（rowcount=0）；
              ORM 侧仅当原值为 None 时刷新 → 保留 9999。
        """
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=5555)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(
            schema_snapshot_id=1, audit_id=200, exec_status=AiSqlAuditExecutionStatus.RUNNING,
        )
        audit.awx_job_id = 9999  # 已存在的值（callback 重试场景）
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=True)
        # IS NULL guard 阻止 UPDATE；ORM 也保留原值
        assert result.audit.awx_job_id == 9999
        assert audit.awx_job_id == 9999

    def test_awx_job_id_none_when_launch_returns_none(self, monkeypatch):
        """AWX launch 返回 awx_job_id=None 时，不应回填（DB 与 ORM 均 None）。"""
        _patch_settings(monkeypatch)
        # 模拟 launch 返回的 dict 不含 awx_job_id
        def fake_launch_no_id(**kwargs):
            return {"awx_job_url": "http://awx/#/jobs/?"}  # 无 awx_job_id
        monkeypatch.setattr(svc_mod.AwxService, "launch_job", staticmethod(fake_launch_no_id))
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1, audit_id=300)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # launch 未返回 awx_job_id 时，跳过回填分支
        assert result.audit.awx_job_id is None
        assert audit.awx_job_id is None


# ---------------------------------------------------------------------------
# 10. C16-5 P0-4 — ownership 校验
# ---------------------------------------------------------------------------
class TestAuditOwnership:
    """C16-5 P0-4：audit.user_id / session.user_id 与 requested_by 不匹配 → 403。

    覆盖：
    - user 不匹配 → AuditOwnershipError
    - session 不匹配 → AuditOwnershipError
    - audit.user_id 匹配，无 session → 放行
    """

    def test_user_mismatch_raises_403(self, monkeypatch):
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        owner_uuid = "11111111-1111-1111-1111-111111111111"
        requester_uuid = "22222222-2222-2222-2222-222222222222"
        db = _FakeSession()
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=400,
            user_id=owner_uuid,
        )
        snap = _make_snapshot(snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]

        requester = _FakeRequester(id=requester_uuid)
        with pytest.raises(AuditOwnershipError) as exc_info:
            AiSqlExecuteService.execute(
                db, audit_id=audit.id, force=False, requested_by=requester,
            )
        assert "user_id" in str(exc_info.value)
        assert "1111" in str(exc_info.value)  # owner uuid (truncated)
        assert "2222" in str(exc_info.value)  # requester uuid (truncated)

    def test_session_mismatch_raises_403(self, monkeypatch):
        """audit.user_id=None 但 session.user_id 与 requested_by 不匹配 → 403。"""
        from app.models.ai import AiChatSession

        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        owner_uuid = "33333333-3333-3333-3333-333333333333"
        requester_uuid = "44444444-4444-4444-4444-444444444444"
        db = _FakeSession()
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=500,
            user_id=None,  # 无直接归属，依赖 session.user_id
            session_id=10,
        )
        snap = _make_snapshot(snapshot_id=1)
        chat_session = AiChatSession(id=10, user_id=owner_uuid)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        db.store["AiChatSession"] = [chat_session]

        requester = _FakeRequester(id=requester_uuid)
        with pytest.raises(AuditOwnershipError) as exc_info:
            AiSqlExecuteService.execute(
                db, audit_id=audit.id, force=False, requested_by=requester,
            )
        assert "session" in str(exc_info.value).lower()

    def test_owner_passes_through(self, monkeypatch):
        """audit.user_id 与 requested_by.id 一致 → 正常执行不抛 AuditOwnershipError。"""
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=999)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        owner_uuid = "55555555-5555-5555-5555-555555555555"
        db = _FakeSession()
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=600,
            user_id=owner_uuid,
        )
        snap = _make_snapshot(snapshot_id=1)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        requester = _FakeRequester(id=owner_uuid)
        result = AiSqlExecuteService.execute(
            db, audit_id=audit.id, force=False, requested_by=requester,
        )
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING


# ---------------------------------------------------------------------------
# 11. C16-5 P0-4 — PENDING 中间态
# ---------------------------------------------------------------------------
class TestPendingState:
    """C16-5 P0-4：audit 在 AWX launch 之前先写 PENDING，launch 成功后升 RUNNING。

    覆盖：
    - flush 期间 audit.execution_status == PENDING（中间态可见）
    - launch 失败时 PENDING 被 FAILED 覆盖（终态推进）
    - force=true 跳过 pending/running 校验，状态机重新走 pending → running
    """

    def test_audit_marked_pending_before_launch(self, monkeypatch):
        """audit.execution_status 在 launch 之前的 flush 期间等于 PENDING。"""
        _patch_settings(monkeypatch)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        # 包装 db.flush 捕获 audit 状态
        captured_states: list[str] = []
        db = _FakeSession()
        original_flush = db.flush

        def wrapped_flush() -> None:
            original_flush()
            # flush 后再读取 audit 状态（保证 ORM 已 sync）
            audit_list = db.store.get("AiSqlAudit", [])
            if audit_list:
                captured_states.append(audit_list[0].execution_status)

        db.flush = wrapped_flush  # type: ignore[method-assign]

        # launch 也要执行（PENDING 已经写入）
        _patch_awx_launch(monkeypatch, awx_job_id=700)

        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1, audit_id=700)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # 中间态：在某个 flush 时点必须是 PENDING（launch 前）
        assert AiSqlAuditExecutionStatus.PENDING in captured_states
        # 终态：commit 后必须是 RUNNING
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING

    def test_failed_state_overrides_pending_on_launch_failure(self, monkeypatch):
        """AWX launch 抛异常 → PENDING 被 FAILED 覆盖（终态推进）。"""
        _patch_settings(monkeypatch)
        _patch_awx_launch(
            monkeypatch,
            raise_exc=AwxServiceError("AWX 503 unreachable"),
        )
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        db = _FakeSession()
        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(schema_snapshot_id=1, audit_id=800)
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        with pytest.raises(AwxLaunchError):
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # 终态：FAILED（覆盖 PENDING 中间态）
        assert audit.execution_status == AiSqlAuditExecutionStatus.FAILED
        assert "AWX launch failed" in (audit.error_message or "")

    def test_force_rerun_walks_state_machine_again(self, monkeypatch):
        """audit 已在 running 状态时，force=true 触发完整状态机重走：running → pending → running。"""
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=1100)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        captured_transitions: list[str] = []
        db = _FakeSession()
        original_flush = db.flush

        def wrapped_flush() -> None:
            audit_list = db.store.get("AiSqlAudit", [])
            if audit_list:
                captured_transitions.append(audit_list[0].execution_status)
            return original_flush()

        db.flush = wrapped_flush  # type: ignore[method-assign]

        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=900,
            exec_status=AiSqlAuditExecutionStatus.RUNNING,  # 已 running
        )
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=True)
        # capture 序列解读（audit 初始 RUNNING，因为 force 重跑已有 running 审计）：
        #   - flush #1: RUNNING (initial, unchanged)
        #   - flush #2: RUNNING (still unchanged)
        #   - line 464 写入 PENDING + flush #3: PENDING (中间态)
        #   - line 522 写入 RUNNING + commit: 终态 RUNNING
        # 重要：PENDING 必须出现，且不作为首个捕获点（证明它是中间过渡态）。
        pending_indices = [
            i for i, s in enumerate(captured_transitions)
            if s == AiSqlAuditExecutionStatus.PENDING
        ]
        assert pending_indices, f"PENDING not in transitions: {captured_transitions}"
        # PENDING 必须出现在 flush #1 之后（不能是首个，因为首个捕获的是原状态）
        assert pending_indices[0] > 0, (
            f"PENDING must be intermediate, not first: {captured_transitions}"
        )
        # commit 后终态仍是 RUNNING（force 重新走完整个状态机后保持 RUNNING）
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING


# ---------------------------------------------------------------------------
# 12. C16-5 P0-4 — 状态机转换
# ---------------------------------------------------------------------------
class TestStateMachineTransition:
    """C16-5 P0-4：完整状态机 not_requested → pending → running → {success,failed}。

    覆盖：
    - not_requested → pending → running 成功路径
    - pending → failed 失败路径
    """

    def test_state_machine_pending_to_running_success(self, monkeypatch):
        """完整状态机：not_requested → pending（中间） → running（终态）。"""
        _patch_settings(monkeypatch)
        _patch_awx_launch(monkeypatch, awx_job_id=1200)
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        captured: list[str] = []
        db = _FakeSession()
        original_flush = db.flush

        def wrapped_flush() -> None:
            audit_list = db.store.get("AiSqlAudit", [])
            if audit_list:
                captured.append(audit_list[0].execution_status)
            return original_flush()

        db.flush = wrapped_flush  # type: ignore[method-assign]

        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=1100,
            exec_status=AiSqlAuditExecutionStatus.NOT_REQUESTED,
        )
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        result = AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # capture 序列解读（audit 初始 NOT_REQUESTED）：
        #   - flush #1: NOT_REQUESTED (initial)
        #   - flush #2: NOT_REQUESTED
        #   - line 464 写入 PENDING + flush #3: PENDING (中间态)
        #   - line 522 写入 RUNNING + commit: 终态 RUNNING
        assert AiSqlAuditExecutionStatus.PENDING in captured, (
            f"PENDING should be in transitions: {captured}"
        )
        # PENDING 必须出现在 NOT_REQUESTED 之后（不能是首个）
        pending_idx = captured.index(AiSqlAuditExecutionStatus.PENDING)
        assert pending_idx > 0, (
            f"PENDING must be intermediate (idx > 0): {captured}"
        )
        # 终态：commit 后是 RUNNING
        assert result.audit.execution_status == AiSqlAuditExecutionStatus.RUNNING

    def test_state_machine_pending_to_failed_on_launch_error(self, monkeypatch):
        """完整状态机：not_requested → pending（中间） → failed（终态，AWX 抛错）。"""
        _patch_settings(monkeypatch)
        _patch_awx_launch(
            monkeypatch,
            raise_exc=AwxServiceError("network timeout"),
        )
        _patch_credential_resolver(monkeypatch)
        _patch_safety(monkeypatch)

        captured: list[str] = []
        db = _FakeSession()
        original_flush = db.flush

        def wrapped_flush() -> None:
            audit_list = db.store.get("AiSqlAudit", [])
            if audit_list:
                captured.append(audit_list[0].execution_status)
            return original_flush()

        db.flush = wrapped_flush  # type: ignore[method-assign]

        snap = _make_snapshot(snapshot_id=1)
        audit = _make_audit(
            schema_snapshot_id=1,
            audit_id=1200,
            exec_status=AiSqlAuditExecutionStatus.NOT_REQUESTED,
        )
        db.store["AiSqlAudit"] = [audit]
        db.store["AiSchemaSnapshot"] = [snap]
        _inject_target(db, audit)

        with pytest.raises(AwxLaunchError):
            AiSqlExecuteService.execute(db, audit_id=audit.id, force=False)
        # 中间：PENDING（launch 前）
        assert AiSqlAuditExecutionStatus.PENDING in captured
        # 终态：FAILED（覆盖 PENDING）
        assert audit.execution_status == AiSqlAuditExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# C16-5 P0-3: get_execution_result — 独立 Result API（plan §21.3）
# ---------------------------------------------------------------------------
import json as _json_result  # noqa: E402


class TestExecutionResult:
    """测试 AiSqlExecuteService.get_execution_result（C16-5 P0-3）。

    6 cases：
      1. 成功读取（chat_message.content 有 JSON）
      2. 大结果分页（limit/offset + truncated=true）
      3. 列数校验（rows 列数 < columns → 返回全部 columns + 实际 rows）
      4. 空 rows（returned_rows=0）
      5. cell 长度截断（超长 cell → '...'）
      6. 敏感列掩码（denied_columns → cell='***' + masked_columns）
    """

    def _setup_success_audit(
        self,
        *,
        user_id: Any = None,
        session_id: Optional[int] = 50,
        result_message_id: Optional[int] = 888,
        schema_snapshot_id: int = 1,
        denied_columns: Optional[list[str]] = None,
        row_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
        collector_run_id: Optional[int] = 1,
        collector_run_item_id: Optional[int] = 777,
    ) -> tuple[_FakeSession, AiSqlAudit]:
        """构造一个 success audit + 可选 schema_snapshot + chat_message。

        Returns:
            (db, audit)
        """
        db = _FakeSession()
        audit = _make_audit(
            audit_id=100,
            instance_id=1,
            user_id=user_id,
            session_id=session_id,
            schema_snapshot_id=schema_snapshot_id,
            exec_status=AiSqlAuditExecutionStatus.SUCCESS,
        )
        audit.result_message_id = result_message_id
        audit.row_count = row_count
        audit.duration_ms = duration_ms
        audit.collector_run_id = collector_run_id
        audit.collector_run_item_id = collector_run_item_id
        audit.completed_at = datetime.now(tz=timezone.utc)
        audit.executed_at = datetime.now(tz=timezone.utc)
        db.store["AiSqlAudit"] = [audit]
        if schema_snapshot_id is not None:
            snap = _make_snapshot(
                snapshot_id=schema_snapshot_id,
                denied_columns=denied_columns,
            )
            db.store["AiSchemaSnapshot"] = [snap]
        return db, audit

    # ----- 1. 成功读取 -----
    def test_result_success_loads_from_chat_message(self):
        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-1").id,
            session_id=50,
            result_message_id=888,
            row_count=3,
            duration_ms=120,
        )
        payload = _json_result.dumps(
            {
                "columns": ["id", "name"],
                "rows": [[1, "alice"], [2, "bob"], [3, "carol"]],
                "row_count": 3,
                "duration_ms": 120,
                "status": "success",
                "error_message": None,
                "executed_at": "2026-07-07T10:00:00Z",
            },
            ensure_ascii=False,
        )
        chat_msg = _make_chat_message(
            message_id=888, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-1"),
        )
        assert result["audit_id"] == 100
        assert result["execution_status"] == AiSqlAuditExecutionStatus.SUCCESS
        assert result["columns"] == ["id", "name"]
        assert len(result["rows"]) == 3
        assert result["rows"][0] == [1, "alice"]
        assert result["returned_rows"] == 3
        assert result["truncated"] is False
        assert result["row_count"] == 3
        assert result["duration_ms"] == 120
        assert result["masked_columns"] == []

    # ----- 2. 大结果分页 -----
    def test_result_truncates_when_limit_exceeded(self):
        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-2").id,
            result_message_id=889,
            row_count=5,
        )
        payload = _json_result.dumps(
            {
                "columns": ["id"],
                "rows": [[1], [2], [3], [4], [5]],
            }
        )
        chat_msg = _make_chat_message(
            message_id=889, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-2"),
            limit=2, offset=0,
        )
        assert result["returned_rows"] == 2
        assert result["rows"] == [[1], [2]]
        assert result["truncated"] is True

        # offset=4 + limit=2 → 只返回 1 行 + truncated
        result2 = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-2"),
            limit=2, offset=4,
        )
        assert result2["returned_rows"] == 1
        assert result2["rows"] == [[5]]
        assert result2["truncated"] is False

    # ----- 3. 列数校验（rows 列数 != columns 长度 → 不强制截断）-----
    def test_result_passes_through_when_row_width_mismatches(self):
        """rows[0] 长度 < columns（不常见但真实存在）：
        service 不强制截断；返回原始 rows（前端负责列对齐）。"""
        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-3").id,
            result_message_id=890,
            row_count=2,
        )
        payload = _json_result.dumps(
            {
                "columns": ["id", "name", "status"],
                "rows": [[1, "alice"], [2, "bob"]],  # 短 1 列
            }
        )
        chat_msg = _make_chat_message(
            message_id=890, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-3"),
        )
        assert result["columns"] == ["id", "name", "status"]
        assert len(result["rows"]) == 2
        assert result["returned_rows"] == 2
        # rows 保持原始宽度（service 层不强制补 None / 截断）
        assert result["rows"][0] == [1, "alice"]

    # ----- 4. 空 rows -----
    def test_result_empty_rows(self):
        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-4").id,
            result_message_id=891,
            row_count=0,
        )
        payload = _json_result.dumps({"columns": ["id", "name"], "rows": []})
        chat_msg = _make_chat_message(
            message_id=891, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-4"),
        )
        assert result["columns"] == ["id", "name"]
        assert result["rows"] == []
        assert result["returned_rows"] == 0
        assert result["truncated"] is False

    # ----- 5. cell 长度截断 -----
    def test_result_truncates_long_cell(self, monkeypatch):
        """cell > AI_SQL_RESULT_MAX_CELL_CHARS → 截断 + '...'"""
        # 用 monkeypatch 调小 limit（避免 4000 字符 cell 让测试变慢）
        _patch_settings(monkeypatch)
        fake_settings = svc_mod.get_settings()

        class _FakeSettings:
            def __getattr__(self, name):
                if name == "AI_SQL_RESULT_MAX_CELL_CHARS":
                    return 20
                return getattr(fake_settings, name)

        monkeypatch.setattr(svc_mod, "get_settings", lambda: _FakeSettings())

        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-5").id,
            result_message_id=892,
            row_count=1,
        )
        long_cell = "x" * 100
        payload = _json_result.dumps(
            {"columns": ["id", "bio"], "rows": [[1, long_cell]]}
        )
        chat_msg = _make_chat_message(
            message_id=892, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-5"),
        )
        assert result["rows"][0][0] == 1
        bio = result["rows"][0][1]
        assert isinstance(bio, str)
        assert len(bio) <= 23  # 20 chars + '...'
        assert bio.endswith("...")

    # ----- 6. 敏感列掩码 -----
    def test_result_masks_denied_columns(self):
        """denied_columns=['password'] → password 列 cell='***' + masked_columns=['password']"""
        db, audit = self._setup_success_audit(
            user_id=_FakeRequester(id="u-6").id,
            result_message_id=893,
            row_count=2,
            schema_snapshot_id=2,
            denied_columns=["password", "secret_token"],
        )
        payload = _json_result.dumps(
            {
                "columns": ["id", "name", "password", "secret_token"],
                "rows": [
                    [1, "alice", "pwd_a", "tok_a"],
                    [2, "bob", "pwd_b", "tok_b"],
                ],
            }
        )
        chat_msg = _make_chat_message(
            message_id=893, session_id=50, content=payload,
        )
        db.store["AiChatMessage"] = [chat_msg]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=100, requested_by=_FakeRequester(id="u-6"),
        )
        # 保留列名 + 标记掩码
        assert result["columns"] == ["id", "name", "password", "secret_token"]
        assert sorted(result["masked_columns"]) == ["password", "secret_token"]
        # 敏感列 cell 已替换为 '***'
        assert result["rows"][0] == [1, "alice", "***", "***"]
        assert result["rows"][1] == [2, "bob", "***", "***"]
        # 非敏感列保持原值
        assert result["rows"][0][0] == 1
        assert result["rows"][0][1] == "alice"


class TestExecutionResultStatusGuards:
    """测试 get_execution_result 状态机守卫（409 + 404 + 403）。"""

    def test_result_404_when_audit_missing(self):
        db = _FakeSession()
        with pytest.raises(AuditNotFoundError) as exc_info:
            AiSqlExecuteService.get_execution_result(
                db, audit_id=999, requested_by=_FakeRequester(id="u-1"),
            )
        assert "999" in str(exc_info.value)

    def test_result_409_when_execution_not_success(self):
        db = _FakeSession()
        audit = _make_audit(
            audit_id=200,
            exec_status=AiSqlAuditExecutionStatus.RUNNING,
        )
        db.store["AiSqlAudit"] = [audit]
        with pytest.raises(AuditResultNotAvailableError) as exc_info:
            AiSqlExecuteService.get_execution_result(
                db, audit_id=200, requested_by=_FakeRequester(id="u-1"),
            )
        assert exc_info.value.current_status == AiSqlAuditExecutionStatus.RUNNING

    def test_result_403_when_user_mismatch(self):
        db = _FakeSession()
        audit = _make_audit(
            audit_id=300,
            user_id="other-user-id",
            session_id=None,
            exec_status=AiSqlAuditExecutionStatus.SUCCESS,
        )
        audit.result_message_id = None
        db.store["AiSqlAudit"] = [audit]
        with pytest.raises(AuditOwnershipError):
            AiSqlExecuteService.get_execution_result(
                db, audit_id=300, requested_by=_FakeRequester(id="u-1"),
            )

    def test_result_fallback_to_collector_run_item(self):
        """chat_message 缺失时 fallback 到 CollectorRunItem.raw_result。"""
        db = _FakeSession()
        audit = _make_audit(
            audit_id=400,
            user_id=_FakeRequester(id="u-7").id,
            session_id=50,
            exec_status=AiSqlAuditExecutionStatus.SUCCESS,
        )
        audit.result_message_id = None  # 无 chat_message
        audit.collector_run_id = 1
        audit.collector_run_item_id = 777
        audit.row_count = 2
        db.store["AiSqlAudit"] = [audit]
        run_item = _make_run_item(
            run_item_id=777,
            raw_result={
                "columns": ["id", "val"],
                "rows": [[10, "x"], [20, "y"]],
            },
        )
        db.store["CollectorRunItem"] = [run_item]

        result = AiSqlExecuteService.get_execution_result(
            db, audit_id=400, requested_by=_FakeRequester(id="u-7"),
        )
        assert result["columns"] == ["id", "val"]
        assert result["rows"] == [[10, "x"], [20, "y"]]
        assert result["returned_rows"] == 2
        assert result["truncated"] is False