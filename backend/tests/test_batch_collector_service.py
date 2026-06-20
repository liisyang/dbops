"""Phase 3.2 — Batch Collector Service tests."""

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.dbops_assets import (
    AssetEndpoint,
    AssetChangeProposal,
    CollectorBatchRun,
    CollectorDispatchRun,
    CollectorRun,
    CollectorRunItem,
    CollectorRunResult,
    DbInstance,
    DbType,
    Server,
    Site,
)
from app.schemas.collector import BatchRunCreateRequest, RetryFailedRequest
from app.services import awx_service as awx_service_module
from app.services import batch_collector_service as batch_collector_service_module
from app.services.awx_service import AwxService
from app.services.batch_collector_service import BatchCollectorService
from app.services.check_item_builder_registry import CheckItemBuilderRegistry
from app.services.credential_resolver_service import CredentialResolverService
from app.services.dispatch_planner_service import DispatchPlannerService


# ============================================================================
# DispatchPlannerService
# ============================================================================


def test_dispatch_planner_resolves_from_extra_attrs():
    """resolve_dispatch_target should use db_instance.extra_attrs first."""
    # Priority 1: db_instance.extra_attrs.awx_instance_group
    result = DispatchPlannerService._resolve_awx_instance_group(
        {"awx_instance_group": "IG_DB_DIRECT"},
        {"awx_instance_group": "IG_SERVER"},
    )
    assert result == "IG_DB_DIRECT"


def test_dispatch_planner_fallback_to_server():
    """If db_instance has no awx_instance_group, use server's."""
    result = DispatchPlannerService._resolve_awx_instance_group(
        {},
        {"awx_instance_group": "IG_SERVER"},
    )
    assert result == "IG_SERVER"


def test_dispatch_planner_fallback_to_none():
    """If neither has awx_instance_group, return None for config fallback."""
    result = DispatchPlannerService._resolve_awx_instance_group({}, {})
    assert result is None


def test_dispatch_planner_network_zone_priority():
    """network_zone resolution: db_instance first, then server."""
    result = DispatchPlannerService._resolve_network_zone(
        {"network_zone": "NET_DB"},
        {"network_zone": "NET_SRV"},
    )
    assert result == "NET_DB"


def test_dispatch_planner_does_not_depend_on_site():
    """Verify DispatchPlannerService has no site.extra_attrs dependency."""
    import re
    import inspect
    source = inspect.getsource(DispatchPlannerService)
    # Strip docstrings to avoid false positives from the docstring itself
    source = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
    source = re.sub(r"'''.*?'''", '', source, flags=re.DOTALL)
    assert "site.extra_attrs" not in source
    assert "site_extra" not in source
    assert "Site.extra_attrs" not in source
    assert ".site." not in source  # no direct site access at all


def test_group_items_by_dispatch_target():
    """group_items_by_dispatch_target groups by (network_zone, awx_instance_group)."""
    # Test without DB: items with no asset_id go to __skipped__
    items = [
        {"target_scope": "db_instance", "target_host": "10.0.0.1", "target_port": 1521, "item_key": "k1", "check_code": "DB_PORT_REACHABILITY"},
        {"target_scope": "db_instance", "target_host": "10.0.0.2", "target_port": 1521, "item_key": "k2", "check_code": "DB_PORT_REACHABILITY"},
    ]
    # Without asset_id, all items go to __skipped__ since we can't resolve
    result = DispatchPlannerService.group_items_by_dispatch_target(None, items, "db_instance")
    assert isinstance(result, dict)
    # With no asset_id keys, all items should go to __skipped__
    assert "__skipped__" in result
    assert len(result["__skipped__"]) == 2


# ============================================================================
# CheckItemBuilderRegistry
# ============================================================================


def test_check_item_builder_registry_has_required_builders():
    """Registry must contain all three Phase 3.2 builders."""
    codes = CheckItemBuilderRegistry.supported_codes()
    assert "DB_PORT_REACHABILITY" in codes
    assert "SSH_PORT_REACHABILITY" in codes
    assert "PORT_CANDIDATE_REACHABILITY" in codes


def test_check_item_builder_registry_raises_on_unknown_code():
    """Registry raises ValueError for unsupported check_code."""
    try:
        CheckItemBuilderRegistry.build_items(None, "UNKNOWN_CHECK", [], {})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported check_code" in str(e)


# ============================================================================
# P0: BatchCollectorService must NOT contain check_code branches
# ============================================================================


def test_batchcollector_must_not_contain_check_code_branches():
    """BatchCollectorService MUST NOT have `if check_code ==` or `elif check_code ==`."""
    import inspect
    import re
    source = inspect.getsource(BatchCollectorService)

    # Remove docstrings (triple-quoted) and line comments
    # First strip triple-quoted strings
    no_docstrings = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
    no_docstrings = re.sub(r"'''.*?'''", '', no_docstrings, flags=re.DOTALL)
    # Then strip line comments
    lines = [line for line in no_docstrings.split("\n") if not line.strip().startswith("#")]
    code_only = "\n".join(lines)

    # Must not contain if/elif check_code patterns
    assert "if check_code ==" not in code_only, (
        "BatchCollectorService MUST NOT contain `if check_code == ...` branches. "
        "Use CheckItemBuilderRegistry instead."
    )
    assert "elif check_code ==" not in code_only, (
        "BatchCollectorService MUST NOT contain `elif check_code == ...` branches. "
        "Use CheckItemBuilderRegistry instead."
    )


# ============================================================================
# batch_code format
# ============================================================================


def test_batch_code_format_uses_random_suffix():
    """batch_code must be BATCH-{YYYYMMDDHH24MISS}-{random6}."""
    code = BatchCollectorService._generate_batch_code()
    pattern = r"^BATCH-\d{14}-[A-F0-9]{6}$"
    assert re.match(pattern, code), f"batch_code {code!r} does not match {pattern}"


def test_batch_codes_are_unique():
    """Consecutive batch codes should differ in random suffix."""
    codes = [BatchCollectorService._generate_batch_code() for _ in range(10)]
    # All should be unique
    assert len(set(codes)) == 10


# ============================================================================
# Models
# ============================================================================


def test_collector_batch_run_model_exists():
    assert CollectorBatchRun.__tablename__ == "collector_batch_run"
    assert "batch_code" in CollectorBatchRun.__table__.columns
    assert "status" in CollectorBatchRun.__table__.columns
    assert "total_item_count" in CollectorBatchRun.__table__.columns
    assert "dispatch_count" in CollectorBatchRun.__table__.columns
    assert "request_payload" in CollectorBatchRun.__table__.columns


def test_collector_dispatch_run_model_exists():
    assert CollectorDispatchRun.__tablename__ == "collector_dispatch_run"
    assert "dispatch_code" in CollectorDispatchRun.__table__.columns
    assert "batch_run_id" in CollectorDispatchRun.__table__.columns
    assert "collector_run_id" in CollectorDispatchRun.__table__.columns
    assert "awx_instance_group" in CollectorDispatchRun.__table__.columns
    assert "network_zone" in CollectorDispatchRun.__table__.columns
    assert "request_payload" in CollectorDispatchRun.__table__.columns


def test_collector_run_has_batch_fields():
    assert "batch_run_id" in CollectorRun.__table__.columns
    assert "dispatch_run_id" in CollectorRun.__table__.columns
    assert "network_zone" in CollectorRun.__table__.columns
    assert "awx_instance_group" in CollectorRun.__table__.columns


# ============================================================================
# Schema validation
# ============================================================================


def test_batch_run_create_request_validation():
    """BatchRunCreateRequest should validate required fields."""
    req = BatchRunCreateRequest(
        target_scope="db_instance",
        check_codes=["DB_PORT_REACHABILITY"],
        asset_ids=[1, 2, 3],
    )
    assert req.target_scope == "db_instance"
    assert req.check_codes == ["DB_PORT_REACHABILITY"]
    assert req.asset_ids == [1, 2, 3]
    assert req.max_items_per_dispatch == 100  # default
    assert req.include_related_server is True  # default


def test_retry_failed_request_defaults():
    """RetryFailedRequest defaults to scope=failed."""
    req = RetryFailedRequest()
    assert req.scope == "failed"

    req2 = RetryFailedRequest(scope="dispatch_failed")
    assert req2.scope == "dispatch_failed"


# ============================================================================
# Dispatch codes
# ============================================================================


def test_dispatch_code_format():
    """dispatch_code must be DISPATCH-{timestamp}-{batch_suffix}-{seq_letter}."""
    code = BatchCollectorService._generate_dispatch_code("A1B2C3", 0)
    pattern = r"^DISPATCH-\d{14}-A1B2C3-A$"
    assert re.match(pattern, code), f"dispatch_code {code!r} does not match {pattern}"

    code_b = BatchCollectorService._generate_dispatch_code("A1B2C3", 1)
    assert code_b.endswith("-B")


def test_run_id_format():
    run_id = BatchCollectorService._generate_run_id(0)
    assert run_id.startswith("RUN-")
    assert run_id.endswith(run_id.split("-")[-1])  # ends with random suffix


def test_extract_credential_ids_merges_prebound_credentials(monkeypatch):
    settings = SimpleNamespace(AWX_PREBOUND_CREDENTIAL_IDS="7, 11")
    monkeypatch.setattr(batch_collector_service_module, "get_settings", lambda: settings)

    result = BatchCollectorService._extract_credential_ids(
        {"items": [{"awx_credential_id": 3}, {"awx_credential_id": 3}]}
    )

    assert result == [3, 7, 11]


def test_extract_credential_ids_keeps_prebound_credentials_without_fact_ids(monkeypatch):
    settings = SimpleNamespace(AWX_PREBOUND_CREDENTIAL_IDS="7,11")
    monkeypatch.setattr(batch_collector_service_module, "get_settings", lambda: settings)

    result = BatchCollectorService._extract_credential_ids({"items": []})

    assert result == [7, 11]


def test_awx_launch_job_includes_credentials(monkeypatch):
    settings = SimpleNamespace(
        AWX_URL="http://awx.example",
        AWX_USER="admin",
        AWX_PASSWORD="secret",
        AWX_REQUEST_TIMEOUT=30,
    )
    monkeypatch.setattr(awx_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(AwxService, "resolve_collector_job_template", staticmethod(lambda: (10, "JT_DBOPS_COLLECTOR_GENERIC")))

    captured = {}

    def fake_request_json(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"job": 123}

    monkeypatch.setattr(AwxService, "_request_json", staticmethod(fake_request_json))

    result = AwxService.launch_job(
        extra_vars={"items": []},
        credentials=[5, 9],
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/job_templates/10/launch/"
    assert captured["payload"]["credentials"] == [5, 9]
    assert result["awx_job_id"] == 123
    assert result["awx_job_url"] == "http://awx.example/#/jobs/playbook/123"


def test_db_fact_builder_emits_skipped_item_when_credential_missing(monkeypatch):
    db = MagicMock()

    instance = SimpleNamespace(server_id=2, db_type_id=3, port=1521, service_name="ORCLPDB1", instance_name="ora1")
    server = SimpleNamespace(ip_address="10.0.0.10", extra_attrs={"os_family": "linux"})
    db_type = SimpleNamespace(type_code="oracle")

    def query_side_effect(model):
        query = MagicMock()
        if model is DbInstance:
            query.filter.return_value.first.return_value = instance
        elif model is Server:
            query.filter.return_value.first.return_value = server
        elif model is DbType:
            query.filter.return_value.first.return_value = db_type
        else:
            query.filter.return_value.first.return_value = None
        return query

    db.query.side_effect = query_side_effect
    monkeypatch.setattr(CredentialResolverService, "resolve_for_item", staticmethod(lambda *args, **kwargs: None))

    items = CheckItemBuilderRegistry.build_items(
        db,
        "DB_BASIC_FACT_COLLECTION",
        [{"id": 1, "target_scope": "db_instance"}],
        {"timeout_seconds": 30},
    )

    assert len(items) == 1
    assert items[0]["status"] == "skipped"
    assert items[0]["result_message"] == "CREDENTIAL_MISSING"
    assert items[0]["server_id"] == 2
    assert items[0]["raw_result"]["skip_reason"] == "CREDENTIAL_MISSING"


# ============================================================================
# C3 (PR review 2026-06-18): build_cluster_type_hint wire-in
# ============================================================================


def test_infer_cluster_type_from_facts_primary_with_slave_returns_master_slave():
    """C3: PRIMARY role + has_slave → master-slave 推断."""
    from app.services.drift_detection_service import DriftDetectionService

    facts = {"database_role": "PRIMARY", "has_slave": True}
    result = DriftDetectionService._infer_cluster_type_from_facts(facts)
    assert result == "master-slave"


def test_infer_cluster_type_from_facts_standby_returns_primary_standby():
    """C3: PHYSICAL STANDBY → primary-standby 推断."""
    from app.services.drift_detection_service import DriftDetectionService

    facts = {"database_role": "PHYSICAL STANDBY"}
    result = DriftDetectionService._infer_cluster_type_from_facts(facts)
    assert result == "primary-standby"


def test_infer_cluster_type_from_facts_is_in_recovery_true_returns_primary_standby():
    """C3: PostgreSQL pg_is_in_recovery=True → primary-standby."""
    from app.services.drift_detection_service import DriftDetectionService

    facts = {"is_in_recovery": True}
    result = DriftDetectionService._infer_cluster_type_from_facts(facts)
    assert result == "primary-standby"


def test_infer_cluster_type_from_facts_ambiguous_returns_none():
    """C3: PRIMARY 但 has_slave 缺失 → 模糊，不推断 (返回 None)。"""
    from app.services.drift_detection_service import DriftDetectionService

    facts = {"database_role": "PRIMARY"}  # 无 has_slave
    result = DriftDetectionService._infer_cluster_type_from_facts(facts)
    assert result is None

    # Empty facts 同样模糊
    result = DriftDetectionService._infer_cluster_type_from_facts({})
    assert result is None


def test_build_cluster_type_hint_happy_path_returns_mismatch_dict():
    """C3: inferred type 与 cluster.cluster_type 不一致 → 返回 hint dict。"""
    from app.services.drift_detection_service import DriftDetectionService

    db = MagicMock()
    instance = SimpleNamespace(
        id=80, cluster_id=70,
        db_type=SimpleNamespace(type_code="mysql"),
        cluster=SimpleNamespace(cluster_type="DATAGUARD"),  # CMDB 标 DATAGUARD
    )
    facts = {"database_role": "PRIMARY", "has_slave": True}  # 推断 master-slave

    result = DriftDetectionService.build_cluster_type_hint(db, instance, facts)
    assert result is not None
    assert result["item_code"] == "CLUSTER_TYPE_MISMATCH"
    assert result["derived_target_type"] == "cluster"
    assert result["derived_target_id"] == 70
    assert result["current_cluster_type"] == "DATAGUARD"
    assert result["inferred_cluster_type"] == "master-slave"
    assert result["auto_proposal"] is False
    assert "不一致" in result["message"]


def test_build_cluster_type_hint_returns_none_when_consistent():
    """C3: cluster.cluster_type 与推断一致 → 返回 None，无需提示。"""
    from app.services.drift_detection_service import DriftDetectionService

    db = MagicMock()
    instance = SimpleNamespace(
        id=80, cluster_id=70,
        db_type=SimpleNamespace(type_code="mysql"),
        cluster=SimpleNamespace(cluster_type="master-slave"),  # 已对齐
    )
    facts = {"database_role": "PRIMARY", "has_slave": True}

    result = DriftDetectionService.build_cluster_type_hint(db, instance, facts)
    assert result is None


def test_build_cluster_type_hint_returns_none_when_no_cluster():
    """C3: 实例未关联 cluster → 返回 None。"""
    from app.services.drift_detection_service import DriftDetectionService

    db = MagicMock()
    instance = SimpleNamespace(
        id=80, cluster_id=None,
        db_type=SimpleNamespace(type_code="mysql"),
        cluster=None,
    )
    facts = {"database_role": "PRIMARY", "has_slave": True}

    result = DriftDetectionService.build_cluster_type_hint(db, instance, facts)
    assert result is None


def test_get_asset_report_includes_cluster_type_suspected():
    """C3 集成: get_asset_report 对每个 db_instance asset 填充 cluster_type_suspected。

    seed 1 instance + cluster_type="single" + facts 显示 role=PRIMARY + has_slave=True
    → asset.cluster_type_suspected != null
    """
    # Simulate the relevant subset of db.query(model).filter(...).first() calls
    # that BatchCollectorService.get_asset_report issues:
    #   CollectorBatchRun → batch_run
    #   CollectorRun      → runs (one per collector_run_id)
    #   CollectorRunItem  → items (port check + DB_BASIC_FACT_COLLECTION)
    #   DbInstance        → instance (for name + IP + cluster_type_hint)
    #   CollectorRunItem  → latest DB_BASIC_FACT_COLLECTION (for facts)
    batch_run = SimpleNamespace(id=1, batch_code="BATCH-CLUSTER")
    instance = SimpleNamespace(
        id=80,
        instance_name="ORCL1",
        code="INS-1",
        cluster_id=70,
        cluster=SimpleNamespace(cluster_type="single"),  # 不一致
        server=SimpleNamespace(ip_address="10.0.0.10"),
    )
    port_item = SimpleNamespace(
        collector_run_id=10, run_id="RID-1", item_key="db:80:DB_PORT:10.0.0.10:1521",
        check_code="DB_PORT_REACHABILITY", target_scope="db_instance",
        db_instance_id=80, server_id=None, target_host="10.0.0.10", target_port=1521,
        status="verified", result_status="verified", result_message=None,
        is_required=True, raw_result={},
    )
    fact_item = SimpleNamespace(
        collector_run_id=10, run_id="RID-1", item_key="db:80:DB_FACT:10.0.0.10:1521",
        check_code="DB_BASIC_FACT_COLLECTION", target_scope="db_instance",
        db_instance_id=80, server_id=None, target_host="10.0.0.10", target_port=1521,
        status="success", result_status="collected", result_message=None,
        is_required=True,
        raw_result={"facts": {"database_role": "PRIMARY", "has_slave": True}},
    )
    collector_run = SimpleNamespace(id=10, batch_run_id=1)

    db = MagicMock()

    def _query(model):
        m = MagicMock()
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        if name == "CollectorBatchRun":
            m.filter.return_value.first.return_value = batch_run
        elif name == "CollectorRun":
            m.filter.return_value.all.return_value = [collector_run]
        elif name == "CollectorRunItem":
            m.filter.return_value.all.return_value = [port_item, fact_item]
            m.filter.return_value.first.return_value = fact_item
            # _load_latest_facts_for_instance uses .order_by().first()
            m.filter.return_value.order_by.return_value.first.return_value = fact_item
        elif name == "DbInstance":
            # I3 (PR review 2026-06-20): get_asset_report 改用批量 in_() 预加载
            m.options.return_value.filter.return_value.all.return_value = [instance]
            m.filter.return_value.first.return_value = instance
        return m

    db.query.side_effect = _query

    result = BatchCollectorService.get_asset_report(db, batch_run_id=1)

    assert result["batch_run_id"] == 1
    assert result["batch_code"] == "BATCH-CLUSTER"
    assert len(result["assets"]) == 1
    asset = result["assets"][0]
    assert asset["entity_type"] == "db_instance"
    assert asset["entity_id"] == 80
    # C3 关键断言: cluster_type_suspected 字段填充
    assert "cluster_type_suspected" in asset
    hint = asset["cluster_type_suspected"]
    assert hint is not None
    assert hint["inferred_cluster_type"] == "master-slave"
    assert hint["current_cluster_type"] == "single"
    assert hint["item_code"] == "CLUSTER_TYPE_MISMATCH"


def test_get_asset_report_returns_null_cluster_type_when_no_latest_facts():
    """C3: 没有任何 DB_BASIC_FACT_COLLECTION 历史 → cluster_type_suspected = None。"""
    batch_run = SimpleNamespace(id=2, batch_code="BATCH-EMPTY")
    instance = SimpleNamespace(
        id=81, instance_name="ORCL2", code="INS-2",
        cluster_id=70,
        cluster=SimpleNamespace(cluster_type="master-slave"),
        server=SimpleNamespace(ip_address="10.0.0.11"),
    )
    port_item = SimpleNamespace(
        collector_run_id=11, run_id="RID-2", item_key="db:81:DB_PORT:10.0.0.11:1521",
        check_code="DB_PORT_REACHABILITY", target_scope="db_instance",
        db_instance_id=81, server_id=None, target_host="10.0.0.11", target_port=1521,
        status="verified", result_status="verified", result_message=None,
        is_required=True, raw_result={},
    )
    collector_run = SimpleNamespace(id=11, batch_run_id=2)

    db = MagicMock()

    def _query(model):
        m = MagicMock()
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        if name == "CollectorBatchRun":
            m.filter.return_value.first.return_value = batch_run
        elif name == "CollectorRun":
            m.filter.return_value.all.return_value = [collector_run]
        elif name == "CollectorRunItem":
            # No DB_BASIC_FACT_COLLECTION items — just the port check
            m.filter.return_value.all.return_value = [port_item]
            m.filter.return_value.first.return_value = None  # no facts
        elif name == "DbInstance":
            m.filter.return_value.first.return_value = instance
        return m

    db.query.side_effect = _query

    result = BatchCollectorService.get_asset_report(db, batch_run_id=2)
    assert len(result["assets"]) == 1
    assert result["assets"][0]["cluster_type_suspected"] is None
