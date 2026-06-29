"""Phase 3.6B1 C14 — SQL Execute API 端点测试.

覆盖 POST /v1/ai/sql/execute + GET /v1/ai/sql/audit/{id}/execution：
  - 401 未登录 → 401（FastAPI 自动）
  - 404 audit_id 不存在 → 404
  - 409 audit_not_passed → 409
  - 422 audit_unsafe_on_execute → 422
  - 503 feature_disabled → 503
  - 200 execute 成功 → 200 + audit_id
  - 200 status 成功 → 200 + execution_status

策略：直接构造 FastAPI app + include_router(ai_router, prefix='/api/v1/ai')，
      绕开 app.main 的传递性 import（docx / prometheus_client / redis）。
      每个 _make_client() 调用都创建新 app → overrides 不跨测试泄漏。
      mock AiSqlExecuteService.execute / get_execution_status 直接抛指定异常。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api import ai as ai_api
from app.api.ai import router as ai_router
from app.api.deps import get_current_user, get_db
from app.services.ai.ai_sql_execute_service import (
    AuditAlreadyRunningError,
    AuditNotFoundError,
    AuditNotPassedError,
    AuditUnsafeOnExecuteError,
    AwxLaunchError,
    FeatureDisabledError,
    SnapshotPolicyMismatchError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _FakeUser:
    id = 1
    username = "tester"
    is_active = True


def _make_test_app() -> FastAPI:
    """直接构造测试用 FastAPI app，绕开 app.main 的传递性 import。

    原因：app.main 会通过 app.api.{inspection,backup,...} 拉入 docx /
    prometheus_client / redis 等重依赖；测试只需要 ai_router 本身。
    """
    app = FastAPI()
    app.include_router(ai_router, prefix="/api/v1/ai")
    return app


def _make_client(*, db_session: Any = None) -> TestClient:
    """创建带依赖覆盖的 TestClient（每调用一个新 app）。"""
    if db_session is None:
        db_session = MagicMock()
    app = _make_test_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. POST /sql/execute — 404
# ---------------------------------------------------------------------------
class TestExecuteNotFound:
    def test_missing_audit_returns_404(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise AuditNotFoundError(f"audit {audit_id} not found")

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 999, "force": False})
        assert r.status_code == 404
        assert "999" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 2. POST /sql/execute — 409 AuditNotPassedError
# ---------------------------------------------------------------------------
class TestExecuteAuditNotPassed:
    def test_rejected_audit_returns_409(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise AuditNotPassedError("audit 100 preview_safety_status='rejected'")

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 409
        assert "rejected" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. POST /sql/execute — 409 SnapshotPolicyMismatchError（结构化 detail）
# ---------------------------------------------------------------------------
class TestExecuteSnapshotMismatch:
    def test_snapshot_mismatch_returns_409_with_code(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise SnapshotPolicyMismatchError(
                "snapshot hash mismatch", reason="policy_hash_mismatch",
            )

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 409
        body = r.json()["detail"]
        assert body["code"] == "snapshot_policy_mismatch"
        assert body["reason"] == "policy_hash_mismatch"


# ---------------------------------------------------------------------------
# 4. POST /sql/execute — 409 AuditAlreadyRunningError
# ---------------------------------------------------------------------------
class TestExecuteAlreadyRunning:
    def test_running_without_force_returns_409(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise AuditAlreadyRunningError(
                "audit 100 execution_status='running'; already in flight (use force=true to re-run)"
            )

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 409
        assert "use force=true" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 5. POST /sql/execute — 422 AuditUnsafeOnExecuteError
# ---------------------------------------------------------------------------
class TestExecuteUnsafe:
    def test_unsafe_sql_returns_422(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise AuditUnsafeOnExecuteError(
                "AST re-check failed", errors=["FOR UPDATE not allowed"],
            )

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 422
        body = r.json()["detail"]
        assert body["code"] == "audit_unsafe_on_execute"
        assert "FOR UPDATE" in body["errors"][0]


# ---------------------------------------------------------------------------
# 6. POST /sql/execute — 503 FeatureDisabledError
# ---------------------------------------------------------------------------
class TestExecuteFeatureDisabled:
    def test_disabled_returns_503(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise FeatureDisabledError("AI_SQL_EXECUTION_ENABLED=false")

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 503
        assert "AI_SQL_EXECUTION_ENABLED=false" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 7. POST /sql/execute — 502 AwxLaunchError
# ---------------------------------------------------------------------------
class TestExecuteAwxLaunchFailed:
    def test_awx_failure_returns_502(self, monkeypatch):
        client = _make_client()

        def fake_execute(db, *, audit_id, force, requested_by):
            raise AwxLaunchError("AWX launch failed: 503")

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 502
        assert "AWX" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 8. POST /sql/execute — 200 happy path
# ---------------------------------------------------------------------------
class TestExecuteHappyPath:
    def test_execute_returns_200_with_audit_id(self, monkeypatch):
        client = _make_client()

        audit = MagicMock()
        audit.id = 100
        audit.execution_status = "running"
        audit.collector_run_id = 555
        audit.collector_run_item_id = 777
        audit.executed_at = datetime.now(tz=timezone.utc)
        audit.error_message = None

        fake_result = MagicMock()
        fake_result.audit = audit

        def fake_execute(db, *, audit_id, force, requested_by):
            return fake_result

        monkeypatch.setattr(ai_api.AiSqlExecuteService, "execute", staticmethod(fake_execute))

        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 200
        body = r.json()
        assert body["audit_id"] == 100
        assert body["execution_status"] == "running"
        assert body["collector_run_id"] == 555
        assert body["collector_run_item_id"] == 777


# ---------------------------------------------------------------------------
# 9. GET /sql/audit/{id}/execution — 404
# ---------------------------------------------------------------------------
class TestExecutionStatusNotFound:
    def test_missing_audit_returns_404(self, monkeypatch):
        client = _make_client()

        def fake_status(db, *, audit_id):
            raise AuditNotFoundError(f"audit {audit_id} not found")

        monkeypatch.setattr(
            ai_api.AiSqlExecuteService, "get_execution_status", staticmethod(fake_status),
        )

        r = client.get("/api/v1/ai/sql/audit/999/execution")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 10. GET /sql/audit/{id}/execution — 200 happy path
# ---------------------------------------------------------------------------
class TestExecutionStatusHappyPath:
    def test_status_returns_200(self, monkeypatch):
        client = _make_client()

        audit = MagicMock()
        audit.id = 100
        audit.execution_status = "success"
        audit.row_count = 5
        audit.duration_ms = 120
        audit.completed_at = datetime.now(tz=timezone.utc)
        audit.error_message = None
        audit.collector_run_id = 555
        audit.executed_at = datetime.now(tz=timezone.utc)
        audit.result_message_id = 888
        audit.created_at = datetime.now(tz=timezone.utc)

        def fake_status(db, *, audit_id):
            return audit

        monkeypatch.setattr(
            ai_api.AiSqlExecuteService, "get_execution_status", staticmethod(fake_status),
        )

        r = client.get("/api/v1/ai/sql/audit/100/execution")
        assert r.status_code == 200
        body = r.json()
        assert body["audit_id"] == 100
        assert body["execution_status"] == "success"
        assert body["row_count"] == 5
        assert body["result_message_id"] == 888
        assert body["message_type"] == "sql_result"


# ---------------------------------------------------------------------------
# 11. POST /sql/execute — Pydantic 422 参数校验
# ---------------------------------------------------------------------------
class TestExecuteParamValidation:
    def test_negative_audit_id_returns_422(self):
        client = _make_client()
        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": -1, "force": False})
        assert r.status_code == 422

    def test_missing_audit_id_returns_422(self):
        client = _make_client()
        r = client.post("/api/v1/ai/sql/execute", json={"force": False})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 12. 未登录 → 401
# ---------------------------------------------------------------------------
class TestUnauthenticated:
    def test_execute_without_user_returns_401(self):
        client = TestClient(_make_test_app())
        r = client.post("/api/v1/ai/sql/execute", json={"audit_id": 100, "force": False})
        assert r.status_code == 401

    def test_status_without_user_returns_401(self):
        client = TestClient(_make_test_app())
        r = client.get("/api/v1/ai/sql/audit/100/execution")
        assert r.status_code == 401