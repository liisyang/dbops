"""Tests for Phase 3.4 P0-4 (dispatch scheduler), P0-5 (timeout recovery), and P0-6 (batch cancel).

These tests cover the new behavior introduced by the working-tree diff for
batch verify 1000+ instances. They avoid hitting a real DB by stubbing
SessionLocal / AwxService and the settings used by the tasks.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.batch_collector_service import BatchCollectorService
from app.tasks import collector_tasks as collector_tasks_module


# ============================================================================
# P0-4: dispatch scheduler
# ============================================================================


class _StubSettings:
    COLLECTOR_AWX_LAUNCH_QPS = 0.0
    COLLECTOR_GLOBAL_MAX_RUNNING_DISPATCHES = 20
    COLLECTOR_BATCH_MAX_RUNNING_DISPATCHES = 10
    COLLECTOR_IG_MAX_RUNNING_DISPATCHES = 5
    COLLECTOR_NETWORK_ZONE_MAX_RUNNING_DISPATCHES = 3


def _make_dispatch(
    dispatch_id: int,
    batch_id: int | None,
    ig: str | None,
    nz: str | None,
    status: str = "pending",
):
    return SimpleNamespace(
        id=dispatch_id,
        batch_run_id=batch_id,
        awx_instance_group=ig,
        network_zone=nz,
        status=status,
    )


def test_quota_check_global_cap_blocks_launch():
    settings = _StubSettings()
    dispatch = _make_dispatch(1, 1, "IG_A", "NZ_A")
    allowed, reason = collector_tasks_module._quota_check(
        dispatch,
        settings,
        global_running=20,
        batch_running=0,
        ig_running=0,
        nz_running=0,
    )
    assert allowed is False
    assert "global cap" in reason


def test_quota_check_batch_cap_blocks_launch():
    settings = _StubSettings()
    dispatch = _make_dispatch(1, 42, "IG_A", "NZ_A")
    allowed, reason = collector_tasks_module._quota_check(
        dispatch,
        settings,
        global_running=5,
        batch_running=10,
        ig_running=0,
        nz_running=0,
    )
    assert allowed is False
    assert "batch cap" in reason


def test_quota_check_ig_cap_blocks_launch():
    settings = _StubSettings()
    dispatch = _make_dispatch(1, 1, "IG_A", None)
    allowed, reason = collector_tasks_module._quota_check(
        dispatch,
        settings,
        global_running=5,
        batch_running=0,
        ig_running=5,
        nz_running=0,
    )
    assert allowed is False
    assert "ig cap" in reason


def test_quota_check_nz_cap_blocks_launch():
    settings = _StubSettings()
    dispatch = _make_dispatch(1, 1, None, "NZ_A")
    allowed, reason = collector_tasks_module._quota_check(
        dispatch,
        settings,
        global_running=5,
        batch_running=0,
        ig_running=0,
        nz_running=3,
    )
    assert allowed is False
    assert "network_zone cap" in reason


def test_quota_check_allows_under_all_caps():
    settings = _StubSettings()
    dispatch = _make_dispatch(1, 1, "IG_A", "NZ_A")
    allowed, reason = collector_tasks_module._quota_check(
        dispatch,
        settings,
        global_running=5,
        batch_running=2,
        ig_running=2,
        nz_running=1,
    )
    assert allowed is True
    assert reason == ""


def test_precompute_running_counts_aggregates_by_group():
    """Single GROUP BY query replaces N*4 per-dispatch COUNT queries."""
    rows = [
        ("IG_A", "NZ_A", 1, 2),
        ("IG_A", "NZ_B", 1, 1),
        ("IG_B", None, 2, 3),
        (None, "NZ_A", None, 1),
    ]
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows
    ig_running, nz_running, batch_running, global_running = (
        collector_tasks_module._precompute_running_counts(fake_db)
    )
    assert global_running == 7
    assert ig_running == {"IG_A": 3, "IG_B": 3}
    assert nz_running == {"NZ_A": 3, "NZ_B": 1}
    assert batch_running == {1: 3, 2: 3}


# ============================================================================
# P0-5: timeout recovery — covers the make_interval parameterized cutoff
# ============================================================================


def test_timeout_recovery_uses_make_interval_not_string_interpolation(monkeypatch):
    """The cutoff MUST be parameterized, not f-string interpolated SQL.

    Regression: previously used `text(f\"interval '{n} minutes'\")` which
    is both fragile (quoting) and a SQL-injection smell even though the
    value comes from settings.
    """
    import sqlalchemy as sa
    src = open(collector_tasks_module.__file__, "r", encoding="utf-8").read()
    assert "make_interval" in src, "should use func.make_interval for the cutoff"
    assert "f\"interval '" not in src, "must not f-string-interpolate an interval literal"


# ============================================================================
# P0-6: batch cancel — idempotency + dispatch state transitions
# ============================================================================


def test_cancel_batch_run_terminal_returns_immediately():
    """If batch is already terminal, cancel is a no-op (idempotent)."""
    db = _FakeCancelDB(
        batch=SimpleNamespace(id=7, status="success", error_message=None),
        dispatch_ids=[],
        dispatch_queue=[],
    )

    result = BatchCollectorService.cancel_batch_run(db, batch_run_id=7, cancelled_by="alice")

    assert result["detail"] == "already_terminal"
    assert result["cancelled_dispatches"] == 0
    assert result["awx_cancel_requested"] == 0
    assert result["awx_cancel_failed"] == 0


class _FakeQuery:
    """Minimal SQLAlchemy query stub: records the last .filter() args
    so the caller can disambiguate the lookup shape (batch row vs
    candidate-id enumeration vs per-row dispatch lookup)."""

    def __init__(self, db, model):
        self._db = db
        self._model = model

    def filter(self, *args, **kwargs):
        self._db._last_filter_args = args
        return self

    def with_for_update(self, **kwargs):
        return self

    def first(self):
        self._db._calls.append(("first", self._model, self._db._last_filter_args))
        return self._db._next_first()

    def all(self):
        self._db._calls.append(("all", self._model, self._db._last_filter_args))
        return self._db._next_all()


class _FakeCancelDB:
    """Hand-rolled fake db.session for cancel_batch_run.

    Three call shapes appear in the real implementation:
      A. query(Batch).filter(id==).with_for_update().first()     -> batch
      B. query(Dispatch.id).filter(batch_run_id==).all()         -> [id, ...]
      C. query(Dispatch).filter(id==, status.notin_(...))
            .with_for_update(skip_locked=True).first()           -> dispatch

    The disambiguation is by call order: first()/all() is consumed from
    the appropriate queue.
    """

    def __init__(self, *, batch, dispatch_ids, dispatch_queue):
        self._batch = batch
        self._dispatch_ids = dispatch_ids
        self._dispatch_queue = list(dispatch_queue)
        self._last_filter_args: tuple = ()
        self._calls: list = []
        # Track which (model) is being queried
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.refresh = MagicMock()

    def query(self, model):
        return _FakeQuery(self, model)

    def _next_first(self):
        # Heuristic: when the per-row path runs, args contain two clauses
        # (id == X, status.notin_(...)). Use that to pop the dispatch queue.
        args = self._last_filter_args
        if len(args) >= 2:
            if self._dispatch_queue:
                return self._dispatch_queue.pop(0)
            return None
        # Single-arg filter on the batch row
        return self._batch

    def _next_all(self):
        return [SimpleNamespace(id=i) for i in self._dispatch_ids]


def test_cancel_batch_run_marks_pending_dispatch_cancelled_without_awx_call():
    batch = SimpleNamespace(id=7, status="running", error_message=None)
    pending = SimpleNamespace(
        id=100,
        batch_run_id=7,
        status="pending",
        awx_job_id=None,
        error_message=None,
    )
    db = _FakeCancelDB(batch=batch, dispatch_ids=[100], dispatch_queue=[pending])

    with patch.object(collector_tasks_module.AwxService, "cancel_job") as awx_cancel:
        result = BatchCollectorService.cancel_batch_run(db, batch_run_id=7, cancelled_by="alice")

    awx_cancel.assert_not_called()
    assert pending.status == "cancelled"
    # C6: cancel writes cancelled_at, not finished_at.
    assert pending.cancelled_at is not None
    assert batch.status == "cancelled"
    assert result["detail"] == "cancelled"
    assert result["cancelled_dispatches"] == 1
    assert result["awx_cancel_requested"] == 0
    assert result["awx_cancel_failed"] == 0


def test_cancel_batch_run_records_awx_cancel_failure_but_still_marks_cancelled():
    """A failed AWX cancel MUST NOT prevent the local 'cancelled' state."""
    from app.services.awx_service import AwxServiceError

    batch = SimpleNamespace(id=7, status="running", error_message=None)
    running = SimpleNamespace(
        id=200,
        batch_run_id=7,
        status="running",
        awx_job_id=9999,
        error_message=None,
    )
    db = _FakeCancelDB(batch=batch, dispatch_ids=[200], dispatch_queue=[running])

    with patch.object(
        collector_tasks_module.AwxService,
        "cancel_job",
        side_effect=AwxServiceError("AWX 405"),
    ):
        result = BatchCollectorService.cancel_batch_run(db, batch_run_id=7, cancelled_by="alice")

    assert running.status == "cancelled"
    assert "awx cancel failed" in (running.error_message or "")
    assert running.cancelled_at is not None
    assert batch.status == "cancelled"
    assert result["awx_cancel_failed"] == 1
    assert result["awx_cancel_requested"] == 1
    assert result["cancelled_dispatches"] == 1


def test_cancel_batch_run_preserves_existing_error_message():
    """If the batch already had an error_message (e.g. partial failure),
    cancel must NOT clobber it."""
    batch = SimpleNamespace(
        id=7,
        status="running",
        error_message="previous failure context",
    )
    db = _FakeCancelDB(batch=batch, dispatch_ids=[], dispatch_queue=[])

    BatchCollectorService.cancel_batch_run(db, batch_run_id=7, cancelled_by="alice")

    assert batch.error_message == "previous failure context"


# ============================================================================
# CollectorService idempotency at handle_callback — terminal-status guard
# ============================================================================


def test_handle_callback_skips_run_in_terminal_status(monkeypatch):
    """A second callback for an already-terminal run must be a no-op."""
    from app.services.collector_service import CollectorService

    db = MagicMock()
    run = SimpleNamespace(id=1, run_id="RID", status="canceled", dispatch_run_id=None, batch_run_id=None)
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = run

    payload = SimpleNamespace(run_id="RID", items=[])

    result = CollectorService.handle_callback(db, payload=payload)

    assert result["detail"] == "ok_already_processed"
    assert result["status"] == "canceled"


def test_run_terminal_statuses_set_matches_db_check_for_collector_run():
    """The terminal set must accept exactly the spellings the DB CHECK allows
    for collector_run.status (see dbops_awx_collector_phase2_refactor.sql)."""
    from app.services.collector_service import _RUN_TERMINAL_STATUSES

    assert "canceled" in _RUN_TERMINAL_STATUSES  # phase 2 refactor CHECK
    assert "cancelled" not in _RUN_TERMINAL_STATUSES  # batch/dispatch only
    for required in ("success", "failed", "partial_success", "callback_failed", "timeout"):
        assert required in _RUN_TERMINAL_STATUSES, f"missing terminal status: {required}"


# ============================================================================
# AwxService cancel_job + get_job_status
# ============================================================================


def test_awx_cancel_job_propagates_awx_405_error():
    """AWX returns 405 when cancelling an already-terminal job; AwxService
    must surface it as AwxServiceError so the caller can decide."""
    from app.services.awx_service import AwxService, AwxServiceError

    with patch.object(
        AwxService,
        "_request_json",
        side_effect=AwxServiceError("AWX API 请求失败: 405 job already finished"),
    ):
        with pytest.raises(AwxServiceError):
            AwxService.cancel_job(1)


def test_awx_get_job_status_marks_terminal_states():
    from app.services.awx_service import AwxService

    with patch.object(
        AwxService,
        "_request_json",
        return_value={"id": 1, "status": "successful"},
    ):
        out = AwxService.get_job_status(1)
    assert out["is_terminal"] is True

    with patch.object(
        AwxService,
        "_request_json",
        return_value={"id": 2, "status": "running"},
    ):
        out = AwxService.get_job_status(2)
    assert out["is_terminal"] is False
