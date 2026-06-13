from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.dbops_assets import (
    CollectorBatchRun,
    CollectorRun,
    CollectorRunItem,
    InspectionItem,
    InspectionResult,
    InspectionTask,
)
from app.schemas.collector import CollectorCallbackItem, CollectorInspectionCallbackItem
from app.schemas.inspection import InspectionTaskCreateRequest
from app.services.batch_collector_service import BatchCollectorService
from app.services.check_item_builder_registry import CheckItemBuilderRegistry
from app.services.inspection_service import InspectionService


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters: list[tuple[str, Any, str]] = []
        self._limit: int | None = None

    def filter(self, *conditions):
        for condition in conditions:
            operator_name = getattr(condition.operator, "__name__", "")
            key = getattr(condition.left, "key", None)
            value = getattr(condition.right, "value", condition.right)
            if key is not None:
                self.filters.append((key, value, operator_name))
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def _apply(self, rows):
        output = list(rows)
        for key, value, op in self.filters:
            if op == "eq":
                output = [row for row in output if getattr(row, key) == value]
            elif op == "in_op":
                target = set(value) if isinstance(value, (list, tuple, set)) else {value}
                output = [row for row in output if getattr(row, key) in target]
        if self._limit is not None:
            output = output[: self._limit]
        return output

    def all(self):
        rows = self.session.store.get(self.model, [])
        return self._apply(rows)

    def first(self):
        rows = self.all()
        return rows[0] if rows else None


class _FakeSession:
    def __init__(self):
        self.store: dict[Any, list[Any]] = {}
        self.next_ids: dict[Any, int] = {}

    def seed(self, *objects):
        for obj in objects:
            self._ensure_id(obj)
            self.store.setdefault(type(obj), []).append(obj)

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, obj):
        self._ensure_id(obj)
        self.store.setdefault(type(obj), []).append(obj)

    def commit(self):
        return None

    def flush(self):
        return None

    def refresh(self, obj):
        self._ensure_id(obj)

    def _ensure_id(self, obj):
        if getattr(obj, "id", None) is not None:
            return
        model = type(obj)
        self.next_ids.setdefault(model, 1)
        obj.id = self.next_ids[model]
        self.next_ids[model] += 1


def test_create_task_launches_inspection_batch(monkeypatch):
    db = _FakeSession()
    db.seed(
        InspectionItem(
            item_code="DB_VERSION_COLLECTED",
            item_name="数据库版本已采集",
            check_code="DB_VERSION_FACT_COLLECTION",
            target_scope="db_instance",
            severity="warning",
            enabled=True,
            created_at=datetime.utcnow(),
        ),
        InspectionItem(
            item_code="FACT_COLLECTION_FAILED",
            item_name="事实采集失败",
            check_code="DB_BASIC_FACT_COLLECTION",
            target_scope="db_instance",
            severity="critical",
            enabled=True,
            created_at=datetime.utcnow(),
        ),
    )

    monkeypatch.setattr(
        BatchCollectorService,
        "create_batch_run",
        staticmethod(
            lambda *_args, **_kwargs: {
                "batch_run_id": 91,
                "status": "running",
                "dispatch_count": 2,
                "total_item_count": 8,
            }
        ),
    )

    payload = InspectionTaskCreateRequest(
        task_name="每日巡检",
        target_scope="db_instance",
        asset_ids=[1, 2],
        item_codes=["DB_VERSION_COLLECTED", "FACT_COLLECTION_FAILED"],
        timeout_seconds=30,
        max_items_per_dispatch=100,
    )
    result = InspectionService.create_task(db, payload=payload, requested_by="admin")

    assert result["batch_run_id"] == 91
    assert result["status"] == "running"
    tasks = db.store.get(InspectionTask, [])
    assert len(tasks) == 1
    assert tasks[0].run_type == "inspection"
    # FACT_COLLECTION_FAILED maps to 4 check_codes; DB_VERSION_COLLECTED maps to DB_VERSION
    assert sorted(tasks[0].check_codes) == [
        "DB_BASIC_FACT_COLLECTION",
        "DB_ROLE_FACT_COLLECTION",
        "DB_VERSION_FACT_COLLECTION",
        "OS_BASIC_FACT_COLLECTION",
    ]


def test_list_tasks_syncs_status_from_batch():
    db = _FakeSession()
    task = InspectionTask(
        task_code="INSP-1",
        task_name="巡检任务",
        run_type="inspection",
        target_scope="db_instance",
        status="pending",
        batch_run_id=1,
        check_codes=[],
        item_codes=[],
        asset_ids=[],
        request_payload={},
        created_at=datetime.utcnow(),
    )
    batch = CollectorBatchRun(
        id=1,
        batch_code="BATCH-001",
        run_type="inspection",
        target_scope="db_instance",
        status="success",
        created_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.seed(task, batch)

    rows = InspectionService.list_tasks(db, limit=10)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"


def test_save_callback_results_from_explicit_payload():
    db = _FakeSession()
    task = InspectionTask(
        task_code="INSP-EXPLICIT",
        task_name="显式回调",
        run_type="inspection",
        target_scope="db_instance",
        status="running",
        batch_run_id=5,
        check_codes=[],
        item_codes=[],
        asset_ids=[],
        request_payload={},
        created_at=datetime.utcnow(),
    )
    item = InspectionItem(
        item_code="CONNECTIVITY_PORT_REACHABLE",
        item_name="端口连通性可达",
        check_code="DB_PORT_REACHABILITY",
        target_scope="db_instance",
        severity="critical",
        enabled=True,
        created_at=datetime.utcnow(),
    )
    run = CollectorRun(
        id=100,
        run_id="RUN-100",
        target_scope="db_instance",
        status="running",
        batch_run_id=5,
        created_at=datetime.utcnow(),
    )
    db.seed(task, item, run)

    explicit = [
        CollectorInspectionCallbackItem(
            item_code="CONNECTIVITY_PORT_REACHABLE",
            result_status="abnormal",
            target_scope="db_instance",
            asset_id=963,
            severity="critical",
            message="PORT_UNREACHABLE",
            evidence={"reason": "timeout"},
        )
    ]
    saved = InspectionService.save_callback_results(
        db,
        run=run,
        callback_items=[],
        explicit_results=explicit,
    )
    assert saved == 1
    rows = db.store.get(InspectionResult, [])
    assert len(rows) == 1
    assert rows[0].result_status == "abnormal"
    assert rows[0].target_id == 963


def test_save_callback_results_derived_from_callback_items():
    db = _FakeSession()
    task = InspectionTask(
        task_code="INSP-DERIVED",
        task_name="派生回调",
        run_type="inspection",
        target_scope="db_instance",
        status="running",
        batch_run_id=9,
        check_codes=[],
        item_codes=[],
        asset_ids=[],
        request_payload={},
        created_at=datetime.utcnow(),
    )
    db.seed(
        task,
        InspectionItem(
            item_code="FACT_COLLECTION_FAILED",
            item_name="事实采集失败",
            check_code="DB_BASIC_FACT_COLLECTION",
            target_scope="db_instance",
            severity="critical",
            enabled=True,
            created_at=datetime.utcnow(),
        ),
        InspectionItem(
            item_code="CREDENTIAL_AUTH_FAILED",
            item_name="凭证认证失败",
            check_code="DB_BASIC_FACT_COLLECTION",
            target_scope="db_instance",
            severity="critical",
            enabled=True,
            created_at=datetime.utcnow(),
        ),
    )

    run = CollectorRun(
        id=200,
        run_id="RUN-200",
        target_scope="db_instance",
        status="running",
        batch_run_id=9,
        created_at=datetime.utcnow(),
    )
    run_item = CollectorRunItem(
        id=300,
        collector_run_id=200,
        run_id="RUN-200",
        item_key="db:1",
        check_code="DB_BASIC_FACT_COLLECTION",
        target_scope="db_instance",
        db_instance_id=1,
        target_host="10.0.0.1",
        target_port=1521,
        status="failed",
        created_at=datetime.utcnow(),
    )
    db.seed(run, run_item)

    callback_items = [
        CollectorCallbackItem(
            item_key="db:1",
            check_code="DB_BASIC_FACT_COLLECTION",
            target_scope="db_instance",
            asset_id=1,
            target_host="10.0.0.1",
            target_port=1521,
            endpoint_type="DB_SERVICE_PORT",
            status="failed",
            message="ORA-01017",
            raw_result={"error_code": "AUTHENTICATION_FAILED"},
        )
    ]
    saved = InspectionService.save_callback_results(
        db,
        run=run,
        callback_items=callback_items,
    )
    assert saved >= 2
    rows = db.store.get(InspectionResult, [])
    statuses = sorted({row.result_status for row in rows})
    assert "abnormal" in statuses


def test_registry_contains_phase34_inspection_items():
    codes = CheckItemBuilderRegistry.inspection_item_codes()
    assert "CONNECTIVITY_PORT_REACHABLE" in codes
    assert "DB_VERSION_COLLECTED" in codes
    assert "DB_ROLE_COLLECTED" in codes
    assert "DB_ROLE_CHANGED" in codes
    assert "INSTANCE_PORT_DRIFT" in codes
    assert "FACT_COLLECTION_FAILED" in codes
    assert "CREDENTIAL_AUTH_FAILED" in codes
    assert "SERVER_OS_COLLECTED" in codes
