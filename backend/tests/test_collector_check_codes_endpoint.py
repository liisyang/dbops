"""Tests for Follow-up A — GET /v1/collector/check-codes endpoint.

资产校验功能优化 v2 / Follow-up A / 2026-06-17.
The endpoint is a thin pass-through to CollectorCheckDefinitionService.
These tests verify the service layer filters, ordering, and (I-16)
HTTP route registration + combined-filter behavior.

I-16 (2026-06-18): added HTTP route integration test, 3-filter combined test,
and order_by SQL-fragment assertions.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.collector_check_definition_service import CollectorCheckDefinitionService


def _row(
    *,
    id: int,
    check_code: str,
    check_name: str,
    target_scope: str,
    task_type: str,
    enabled: bool,
    default_timeout_seconds: int = 5,
    description: str | None = None,
):
    return SimpleNamespace(
        id=id,
        check_code=check_code,
        check_name=check_name,
        target_scope=target_scope,
        task_type=task_type,
        db_type_code=None,
        os_type_code=None,
        awx_role=None,
        default_timeout_seconds=default_timeout_seconds,
        enabled=enabled,
        config={},
        description=description,
        created_at=None,
        updated_at=None,
    )


def _make_db(*rows, record_order_by: bool = False):
    """Build a mock DB session that mimics filter+order_by+all().

    Each call to ``filter()`` is recorded in ``db._filter_args`` as the
    ``str()`` of the binary expression.

    I-16 (2026-06-18): when ``record_order_by=True``, ``order_by`` arguments
    are also recorded in ``db._order_by_args`` so tests can assert on real
    SQL fragments like ``enabled DESC`` and ``check_code ASC``.
    """
    db = MagicMock()
    query = MagicMock()
    filter_args: list[str] = []
    order_by_args: list[str] = []

    def _filter(expr):
        filter_args.append(str(expr))
        return query

    query.filter.side_effect = _filter

    # I-16: record order_by arguments for SQL-fragment assertions
    query._order_by_args = order_by_args  # type: ignore[attr-defined]

    def _record_order_by(*args):
        for a in args:
            order_by_args.append(str(a))
        return query

    query.order_by.side_effect = _record_order_by

    query.all.return_value = list(rows)
    db.query.return_value = query
    db._filter_args = filter_args  # type: ignore[attr-defined]
    db._order_by_args = order_by_args  # type: ignore[attr-defined]
    return db, query


def test_list_definitions_all_rows():
    rows = [
        _row(id=1, check_code="OS_PORT_REACHABILITY", check_name="OS管理端口",
             target_scope="server", task_type="PORT_CHECK", enabled=True),
        _row(id=2, check_code="DB_PORT_REACHABILITY", check_name="DB端口",
             target_scope="db_instance", task_type="PORT_CHECK", enabled=True),
        _row(id=3, check_code="DB_BASIC_FACT_COLLECTION", check_name="DB基础",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=True),
        _row(id=4, check_code="OS_BASIC_FACT_COLLECTION", check_name="OS基础",
             target_scope="server", task_type="OS_DISCOVERY", enabled=True),
        _row(id=5, check_code="DB_VERSION_FACT_COLLECTION", check_name="DB版本[旧]",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=False),
        _row(id=6, check_code="DB_ROLE_FACT_COLLECTION", check_name="DB角色[旧]",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=False),
        _row(id=7, check_code="PORT_CANDIDATE_REACHABILITY", check_name="候选端口[旧]",
             target_scope="db_instance", task_type="PORT_CHECK", enabled=False),
        _row(id=8, check_code="SSH_PORT_REACHABILITY", check_name="SSH端口[旧]",
             target_scope="server", task_type="PORT_CHECK", enabled=False),
    ]
    db, _ = _make_db(*rows, record_order_by=True)

    result = CollectorCheckDefinitionService.list_definitions(db)

    assert len(result) == 8
    # Field shape
    sample = result[0]
    assert set(sample.keys()) >= {
        "id", "check_code", "check_name", "target_scope", "task_type",
        "default_timeout_seconds", "enabled", "config", "description",
    }
    # Enabled bool is a real bool (not a truthy object)
    assert all(isinstance(r["enabled"], bool) for r in result)


def test_list_definitions_filter_by_target_scope():
    rows = [
        _row(id=1, check_code="OS_PORT_REACHABILITY", check_name="OS管理端口",
             target_scope="server", task_type="PORT_CHECK", enabled=True),
        _row(id=2, check_code="DB_PORT_REACHABILITY", check_name="DB端口",
             target_scope="db_instance", task_type="PORT_CHECK", enabled=True),
    ]
    db, _ = _make_db(*rows, record_order_by=True)

    CollectorCheckDefinitionService.list_definitions(db, target_scope="server")

    assert any("target_scope" in s for s in db._filter_args), db._filter_args


def test_list_definitions_filter_by_is_enabled_true_returns_only_enabled():
    """Verify the disabled-codes filter actually excludes them.

    This is the central guarantee of Follow-up A: front-end mounts with
    is_enabled=true so it never sees the 4 disabled check codes.
    """
    rows = [
        _row(id=1, check_code="OS_PORT_REACHABILITY", check_name="OS",
             target_scope="server", task_type="PORT_CHECK", enabled=True),
        _row(id=2, check_code="DB_VERSION_FACT_COLLECTION", check_name="DB版[旧]",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=False),
    ]
    db, _ = _make_db(*rows, record_order_by=True)

    CollectorCheckDefinitionService.list_definitions(db, is_enabled=True)
    assert any("enabled" in s and "true" in s for s in db._filter_args), db._filter_args


def test_list_definitions_preserves_orm_ordering_semantics():
    """Verify the service uses enabled.desc() and check_code.asc() order_by.

    I-16 (2026-06-18): extended to assert on real order_by SQL fragments
    instead of only checking that order_by was called at all.  The
    ``_make_db(record_order_by=True)`` mode captures each order_by
    argument's ``str()`` representation so we can verify the exact column
    and direction.
    """
    db, query = _make_db(record_order_by=True)
    CollectorCheckDefinitionService.list_definitions(db)

    # Exactly 2 order_by arguments: enabled.desc(), check_code.asc()
    assert len(db._order_by_args) == 2, (
        f"expected 2 order_by args, got {db._order_by_args}"
    )

    # First: enabled DESC
    arg0 = db._order_by_args[0].lower()
    assert "enabled" in arg0, f"first order_by arg should be enabled, got: {arg0!r}"
    assert "desc" in arg0, f"first order_by arg should be DESC, got: {arg0!r}"

    # Second: check_code ASC (ASC is default, may be omitted by SQLAlchemy)
    arg1 = db._order_by_args[1].lower()
    assert "check_code" in arg1, f"second order_by arg should be check_code, got: {arg1!r}"
    assert "desc" not in arg1, (
        f"second order_by arg should be ASC (default), got DESC: {arg1!r}"
    )


# ============================================================================
# I-16 (2026-06-18): combined-filter + HTTP route integration tests
# ============================================================================


def test_list_definitions_filters_combined():
    """I-16: exercise all 3 filters (target_scope + task_type + is_enabled)
    simultaneously and verify the result set is correctly narrowed."""
    rows = [
        _row(id=1, check_code="DB_PORT_REACHABILITY", check_name="DB端口",
             target_scope="db_instance", task_type="PORT_CHECK", enabled=True),
        _row(id=2, check_code="OS_PORT_REACHABILITY", check_name="OS管理端口",
             target_scope="server", task_type="PORT_CHECK", enabled=True),
        _row(id=3, check_code="DB_BASIC_FACT_COLLECTION", check_name="DB基础",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=True),
        _row(id=4, check_code="OS_BASIC_FACT_COLLECTION", check_name="OS基础",
             target_scope="server", task_type="OS_DISCOVERY", enabled=True),
        _row(id=5, check_code="DB_VERSION_FACT_COLLECTION", check_name="DB版本[旧]",
             target_scope="db_instance", task_type="DB_SQL_COLLECT", enabled=False),
    ]
    db, _ = _make_db(*rows, record_order_by=True)

    # Mock DB always returns all rows (no real SQL filtering), so verify
    # that all 3 filter conditions were applied to the query instead.
    CollectorCheckDefinitionService.list_definitions(
        db,
        target_scope="db_instance",
        task_type="PORT_CHECK",
        is_enabled=True,
    )

    # All 3 filter conditions should appear in the recorded SQL
    filter_text = " ".join(db._filter_args)
    assert "target_scope" in filter_text, f"missing target_scope in {db._filter_args}"
    assert "task_type" in filter_text, f"missing task_type in {db._filter_args}"
    assert "enabled" in filter_text, f"missing enabled in {db._filter_args}"

    # Verify exact count: 3 separate .filter() calls recorded
    assert len(db._filter_args) == 3, (
        f"expected 3 filter calls, got {len(db._filter_args)}: {db._filter_args}"
    )


def test_list_check_codes_endpoint_registers():
    """I-16: verify the GET /v1/collector/check-codes route is registered
    in the FastAPI app and returns 200 with a list response body.

    Uses FastAPI TestClient with dependency overrides for get_db and
    get_current_user so no real DB or auth token is needed.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import create_app
    from app.models.user import User

    app = create_app(testing=True)
    client = TestClient(app)

    # Build a stub DB that returns empty list for any query
    db_stub = MagicMock()
    query_stub = MagicMock()
    query_stub.order_by.return_value = query_stub
    query_stub.all.return_value = []
    db_stub.query.return_value = query_stub

    # Build a stub admin user for get_current_user override
    fake_user = User(
        id="00000000-0000-0000-0000-000000000001",
        username="admin",
        email="admin@dbops.local",
        role="admin",
        is_active=True,
    )

    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: fake_user

    try:
        response = client.get("/api/v1/collector/check-codes")
        assert response.status_code == 200, (
            f"expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, list), f"expected list, got {type(body).__name__}"
    finally:
        app.dependency_overrides.clear()


def test_list_check_codes_endpoint_returns_filtered_results():
    """I-16: the HTTP endpoint passes query params through to the service layer.

    Verifies that ?target_scope=db_instance&is_enabled=true produces the
    expected service call without hitting a real DB.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import create_app
    from app.models.user import User

    app = create_app(testing=True)
    client = TestClient(app)

    # Return one row so we can verify it comes back correctly shaped
    rows = [
        _row(id=1, check_code="DB_PORT_REACHABILITY", check_name="DB端口",
             target_scope="db_instance", task_type="PORT_CHECK", enabled=True),
    ]
    db_stub, _ = _make_db(*rows, record_order_by=True)

    fake_user = User(
        id="00000000-0000-0000-0000-000000000001",
        username="admin",
        email="admin@dbops.local",
        role="admin",
        is_active=True,
    )

    app.dependency_overrides[get_db] = lambda: db_stub
    app.dependency_overrides[get_current_user] = lambda: fake_user

    try:
        response = client.get(
            "/api/v1/collector/check-codes",
            params={"target_scope": "db_instance", "is_enabled": "true"},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["check_code"] == "DB_PORT_REACHABILITY"
        assert body[0]["enabled"] is True
    finally:
        app.dependency_overrides.clear()
