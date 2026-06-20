"""C8 (PR review 2026-06-20): 3 个新端点 HTTP 集成测试。

覆盖：
- GET  /api/v1/collector/batch-runs/{batch_run_id}/asset-report (200, 404, 401)
- POST /api/v1/collector/proposals/{proposal_id}/apply-with-value (admin, 404, 422)
- POST /api/v1/collector/proposals/batch-action (admin, 404, 422)

仿照 test_collector_check_codes_endpoint.py 的 FastAPI TestClient 模式。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _make_admin_user():
    from app.models.user import User
    return User(
        id="00000000-0000-0000-0000-000000000001",
        username="admin",
        email="admin@dbops.local",
        role="admin",
        is_active=True,
    )


def _make_viewer_user():
    from app.models.user import User
    return User(
        id="00000000-0000-0000-0000-000000000002",
        username="viewer",
        email="viewer@dbops.local",
        role="viewer",
        is_active=True,
    )


# ============================================================================
# GET /collector/batch-runs/{batch_run_id}/asset-report
# ============================================================================


def test_asset_report_endpoint_returns_200_for_known_batch():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    fake_user = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: fake_user

    expected = {
        "batch_run_id": 1,
        "batch_code": "BATCH-1",
        "assets": [],
    }

    def _fake_get_asset_report(db, *, batch_run_id):
        return expected

    import app.api.collector as collector_api_module
    original = getattr(collector_api_module.BatchCollectorService, "get_asset_report", None)
    collector_api_module.BatchCollectorService.get_asset_report = staticmethod(_fake_get_asset_report)
    try:
        response = client.get("/api/v1/collector/batch-runs/1/asset-report")
        assert response.status_code == 200, f"got {response.status_code}: {response.text}"
        body = response.json()
        assert body["batch_run_id"] == 1
        assert body["batch_code"] == "BATCH-1"
        assert body["assets"] == []
    finally:
        if original is not None:
            collector_api_module.BatchCollectorService.get_asset_report = original
        app.dependency_overrides.clear()


def test_asset_report_endpoint_returns_404_for_unknown_batch():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    fake_user = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: fake_user

    def _raise_lookup(db, *, batch_run_id):
        raise LookupError(f"batch_run_id={batch_run_id} 不存在")

    import app.api.collector as collector_api_module
    original = getattr(collector_api_module.BatchCollectorService, "get_asset_report", None)
    collector_api_module.BatchCollectorService.get_asset_report = staticmethod(_raise_lookup)
    try:
        response = client.get("/api/v1/collector/batch-runs/99999/asset-report")
        assert response.status_code == 404, f"got {response.status_code}: {response.text}"
        assert "99999" in response.json()["detail"]
    finally:
        if original is not None:
            collector_api_module.BatchCollectorService.get_asset_report = original
        app.dependency_overrides.clear()


def test_asset_report_endpoint_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    # 没有 override get_current_user → 应该 401
    response = client.get("/api/v1/collector/batch-runs/1/asset-report")
    assert response.status_code == 401, f"got {response.status_code}: {response.text}"


# ============================================================================
# POST /collector/proposals/{proposal_id}/apply-with-value
# ============================================================================


def test_apply_with_value_endpoint_requires_admin():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    viewer = _make_viewer_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: viewer

    try:
        response = client.post(
            "/api/v1/collector/proposals/1/apply-with-value",
            json={"selected_value": 1521},
        )
        assert response.status_code == 403, f"got {response.status_code}: {response.text}"
    finally:
        app.dependency_overrides.clear()


def test_apply_with_value_endpoint_returns_404_on_missing_proposal():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    admin = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: admin

    def _raise_lookup(*args, **kwargs):
        raise LookupError("proposal 不存在")

    import app.services.asset_proposal_service as aps_module
    original = aps_module.AssetProposalService.apply_proposal
    aps_module.AssetProposalService.apply_proposal = staticmethod(_raise_lookup)
    try:
        response = client.post(
            "/api/v1/collector/proposals/99999/apply-with-value",
            json={"selected_value": 1521},
        )
        assert response.status_code == 404, f"got {response.status_code}: {response.text}"
        assert "proposal" in response.json()["detail"]
    finally:
        aps_module.AssetProposalService.apply_proposal = original
        app.dependency_overrides.clear()


def test_apply_with_value_endpoint_validates_selected_value_type():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    admin = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        response = client.post(
            "/api/v1/collector/proposals/1/apply-with-value",
            json={"selected_value": "not-an-int"},
        )
        assert response.status_code == 422, f"got {response.status_code}: {response.text}"
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# POST /collector/proposals/batch-action
# ============================================================================


def test_batch_action_endpoint_validates_empty_proposal_ids():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    admin = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        response = client.post(
            "/api/v1/collector/proposals/batch-action",
            json={"proposal_ids": [], "action": "approve"},
        )
        assert response.status_code == 422, f"got {response.status_code}: {response.text}"
    finally:
        app.dependency_overrides.clear()


def test_batch_action_endpoint_requires_admin():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    viewer = _make_viewer_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: viewer

    try:
        response = client.post(
            "/api/v1/collector/proposals/batch-action",
            json={"proposal_ids": [1], "action": "approve"},
        )
        assert response.status_code == 403, f"got {response.status_code}: {response.text}"
    finally:
        app.dependency_overrides.clear()


def test_batch_action_endpoint_returns_partial_failure_for_unknown_proposal():
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_db
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    db_stub = MagicMock()
    admin = _make_admin_user()
    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: admin

    def _fake_batch_action(*args, **kwargs):
        return {
            "action": "approve",
            "results": [
                {"id": 99999, "success": False, "error": "proposal 不存在"},
            ],
            "success_count": 0,
            "fail_count": 1,
        }

    import app.services.asset_proposal_service as aps_module
    original = aps_module.AssetProposalService.batch_action
    aps_module.AssetProposalService.batch_action = staticmethod(_fake_batch_action)
    try:
        response = client.post(
            "/api/v1/collector/proposals/batch-action",
            json={"proposal_ids": [99999], "action": "approve"},
        )
        # batch_action 是 partial-failure endpoint, 单条 fail 返回 200 + 详细结果
        assert response.status_code == 200, f"got {response.status_code}: {response.text}"
        body = response.json()
        assert body["fail_count"] == 1
        assert body["results"][0]["success"] is False
        assert "不存在" in body["results"][0]["error"]
    finally:
        aps_module.AssetProposalService.batch_action = original
        app.dependency_overrides.clear()
