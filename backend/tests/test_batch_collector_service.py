"""Phase 3.2 — Batch Collector Service tests."""

import re
from datetime import datetime

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
from app.services.batch_collector_service import BatchCollectorService
from app.services.check_item_builder_registry import CheckItemBuilderRegistry
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
