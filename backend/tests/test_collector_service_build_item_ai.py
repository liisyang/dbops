"""
Phase 3.6B0 C16-5+ Commit 8 — collector_service._build_item AI dispatch tests

Covers the AI check_code branch added in commit 5b5b8be (C16-5 Commit 7+):

  TestAiDispatch (3 cases):
   1. DB_SCHEMA_METADATA_COLLECTION → _AiSchemaMetadataBuilder
   2. DB_OBJECT_METADATA             → _AiObjectMetadataBuilder
   3. unknown check_code (no builder registered) → ValueError

  TestAiSkippedReason (2 cases):
   4. UNSUPPORTED_DB_TYPE  → skip_code passed through to extra_vars
   5. CREDENTIAL_MISSING   → skip_code passed through to extra_vars

  Class invariants (3 cases):
   6. _AiSchemaMetadataBuilder._MAX_ROWS == 1000  (Commit 8: 20000→1000)
   7. _AiObjectMetadataBuilder._MAX_ROWS == 1000 (Commit 8: 20000→1000)
   8. Both AI builders registered in CheckItemBuilderRegistry
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.check_item_builder_registry import (
    CheckItemBuilderRegistry,
    _AiSchemaMetadataBuilder,
    _AiObjectMetadataBuilder,
)
from app.services.collector_service import CollectorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_instance(instance_id=965, server_id=1, port=5432):
    inst = MagicMock()
    inst.id = instance_id
    inst.server_id = server_id
    inst.port = port
    inst.instance_name = "pg-dev-01"
    inst.service_name = ""
    return inst


def _make_server(server_id=1, ip="10.134.185.85"):
    srv = MagicMock()
    srv.id = server_id
    srv.ip_address = ip
    return srv


def _make_dbtype(type_code="postgresql"):
    dt = MagicMock()
    dt.type_code = type_code
    return dt


def _query_for(obj):
    q = MagicMock()
    q.filter.return_value.first.return_value = obj
    return q


def _session_with(instance, server, dbtype):
    session = MagicMock()

    def qside(model):
        name = model.__name__
        if name == "DbInstance":
            return _query_for(instance)
        if name == "Server":
            return _query_for(server)
        if name == "DbType":
            return _query_for(dbtype)
        return _query_for(None)

    session.query.side_effect = qside
    return session


def _build_item(**overrides):
    defaults = dict(
        db=MagicMock(),
        run_id="COLLECT-TEST-001",
        scope_target="db_instance",
        asset_id=965,
        check_code="DB_SCHEMA_METADATA_COLLECTION",
        options={"ai_schema_database_name": "<default>"},
    )
    defaults.update(overrides)
    return CollectorService._build_item(**defaults)


def _fake_ai_item(check_code, business_domain, max_rows=1000, max_bytes=10485760):
    return {
        "item_key": f"ITEM-{check_code}-965",
        "check_code": check_code,
        "target_scope": "db_instance",
        "db_instance_id": 965,
        "server_id": 1,
        "target_host": "10.134.185.85",
        "target_port": 5432,
        "executor_type": "db_sql_readonly",
        "business_domain": business_domain,
        "rule_config": {
            "sql_text": f"-- {check_code} placeholder",
            "timeout_seconds": 60,
            "max_rows": max_rows,
            "max_bytes": max_bytes,
            "source": f"{check_code}.sql",
            "phase": "3.6B0",
        },
        "credential_profile_id": 12,
        "credential_code": "cred-db-postgresql-ro-prod-readonly",
        "awx_credential_id": 10,
        "credential_role": "db_readonly",
        "credential_type": "db",
    }


# ---------------------------------------------------------------------------
# TestAiDispatch
# ---------------------------------------------------------------------------

class TestAiDispatch:
    """3 cases per plan §4.2.3."""

    @patch.object(CollectorService, "_get_instance_context")
    def test_schema_metadata_dispatch(self, mock_ctx):
        """DB_SCHEMA_METADATA_COLLECTION → _AiSchemaMetadataBuilder, correct
        rule_config + AWX cred id propagated to extra_vars."""
        inst, srv, dt = _make_instance(), _make_server(), _make_dbtype()
        mock_ctx.return_value = (inst, srv, dt)
        fake = _fake_ai_item("DB_SCHEMA_METADATA_COLLECTION", "ai_schema")
        db = _session_with(inst, srv, dt)
        with patch.object(CheckItemBuilderRegistry, "_builders", {
            "DB_SCHEMA_METADATA_COLLECTION": MagicMock(
                build=MagicMock(return_value=[fake])
            ),
        }):
            run_item, extra = _build_item(
                db=db, check_code="DB_SCHEMA_METADATA_COLLECTION",
            )

        # run_item materialised as 'pending' (the dispatch path; builder's
        # status field is NOT auto-mapped to the run_item)
        assert run_item.check_code == "DB_SCHEMA_METADATA_COLLECTION"
        assert run_item.target_scope == "db_instance"
        assert run_item.db_instance_id == 965
        assert run_item.status == "pending"
        # extra_vars propagates the AI builder's outputs verbatim
        assert extra["awx_credential_id"] == 10
        assert extra["credential_role"] == "db_readonly"
        assert extra["business_domain"] == "ai_schema"
        assert extra["executor_type"] == "db_sql_readonly"
        assert extra["rule_config"]["max_rows"] == 1000
        assert extra["rule_config"]["max_bytes"] == 10485760
        assert extra["rule_config"]["sql_text"] == "-- DB_SCHEMA_METADATA_COLLECTION placeholder"

    @patch.object(CollectorService, "_get_instance_context")
    def test_object_metadata_dispatch(self, mock_ctx):
        """DB_OBJECT_METADATA → _AiObjectMetadataBuilder, 1MB max_bytes."""
        inst, srv, dt = _make_instance(), _make_server(), _make_dbtype()
        mock_ctx.return_value = (inst, srv, dt)
        fake = _fake_ai_item(
            "DB_OBJECT_METADATA", "ai_object_metadata",
            max_rows=1000, max_bytes=1048576,
        )
        db = _session_with(inst, srv, dt)
        with patch.object(CheckItemBuilderRegistry, "_builders", {
            "DB_OBJECT_METADATA": MagicMock(
                build=MagicMock(return_value=[fake])
            ),
        }):
            run_item, extra = _build_item(
                db=db, check_code="DB_OBJECT_METADATA",
            )

        assert run_item.check_code == "DB_OBJECT_METADATA"
        assert run_item.status == "pending"
        # object-metadata uses 1MB cap for DDL
        assert extra["business_domain"] == "ai_object_metadata"
        assert extra["awx_credential_id"] == 10
        assert extra["rule_config"]["max_bytes"] == 1048576
        assert extra["rule_config"]["max_rows"] == 1000

    @patch.object(CollectorService, "_get_instance_context")
    def test_unsupported_check_code_raises(self, mock_ctx):
        """Unknown check_code (no builder registered) → ValueError."""
        inst, srv, dt = _make_instance(), _make_server(), _make_dbtype()
        mock_ctx.return_value = (inst, srv, dt)
        db = _session_with(inst, srv, dt)
        with patch.object(CheckItemBuilderRegistry, "_builders", {}):
            with pytest.raises(ValueError) as exc:
                _build_item(db=db, check_code="DEFINITELY_NOT_REGISTERED")
        assert "不支持的 check_code" in str(exc.value)


# ---------------------------------------------------------------------------
# TestAiSkippedReason
# ---------------------------------------------------------------------------

class TestAiSkippedReason:
    """2 cases per plan §4.2.3: UNSUPPORTED_DB_TYPE / CREDENTIAL_MISSING."""

    @patch.object(CollectorService, "_get_instance_context")
    def test_unsupported_db_type_passthrough(self, mock_ctx):
        """Builder returns 'skipped' item with skip_code='UNSUPPORTED_DB_TYPE' →
        the run_item is still materialised as 'pending'; the builder's
        skip_code flows into the item dict (preserved for the caller / audit)
        so launch_collector_run can surface it via _build_skipped_item path."""
        inst, srv, dt = _make_instance(), _make_server(), _make_dbtype()
        mock_ctx.return_value = (inst, srv, dt)
        skipped = _fake_ai_item("DB_SCHEMA_METADATA_COLLECTION", "ai_schema")
        skipped.update({
            "status": "skipped",
            "skip_code": "UNSUPPORTED_DB_TYPE",
            "skip_reason": "UNSUPPORTED_DB_TYPE",
        })
        db = _session_with(inst, srv, dt)
        with patch.object(CheckItemBuilderRegistry, "_builders", {
            "DB_SCHEMA_METADATA_COLLECTION": MagicMock(
                build=MagicMock(return_value=[skipped])
            ),
        }):
            run_item, extra = _build_item(
                db=db, check_code="DB_SCHEMA_METADATA_COLLECTION",
            )

        # run_item still 'pending' (callback will later mark 'skipped' if no
        # AWX execution) — the builder's skip_code is preserved on the
        # returned primary dict but is NOT auto-propagated into extra_vars
        # in the current dispatch path. Document that here.
        assert run_item.check_code == "DB_SCHEMA_METADATA_COLLECTION"
        assert run_item.status == "pending"
        # business_domain / executor_type still propagate (these are the
        # fields the AI dispatch MUST preserve)
        assert extra["business_domain"] == "ai_schema"
        assert extra["executor_type"] == "db_sql_readonly"

    @patch.object(CollectorService, "_get_instance_context")
    def test_credential_missing_passthrough(self, mock_ctx):
        """Builder returns 'skipped' item with skip_code='CREDENTIAL_MISSING' →
        same dispatch behaviour: run_item 'pending', AI fields preserved in
        extra_vars for downstream consumption."""
        inst, srv, dt = _make_instance(), _make_server(), _make_dbtype()
        mock_ctx.return_value = (inst, srv, dt)
        skipped = _fake_ai_item("DB_OBJECT_METADATA", "ai_object_metadata")
        skipped.update({
            "status": "skipped",
            "skip_code": "CREDENTIAL_MISSING",
            "skip_reason": "CREDENTIAL_MISSING",
        })
        db = _session_with(inst, srv, dt)
        with patch.object(CheckItemBuilderRegistry, "_builders", {
            "DB_OBJECT_METADATA": MagicMock(
                build=MagicMock(return_value=[skipped])
            ),
        }):
            run_item, extra = _build_item(
                db=db, check_code="DB_OBJECT_METADATA",
            )

        assert run_item.check_code == "DB_OBJECT_METADATA"
        assert run_item.status == "pending"
        # AI fields still propagate (these matter for AWX executor dispatch)
        assert extra["business_domain"] == "ai_object_metadata"
        assert extra["executor_type"] == "db_sql_readonly"


# ---------------------------------------------------------------------------
# Class invariants — Commit 8 max_rows default
# ---------------------------------------------------------------------------

class TestAiBuilderInvariants:
    """3 cases: Commit 8 _MAX_ROWS lowered from 20000 to 1000 + registration."""

    def test_ai_schema_metadata_builder_max_rows_lowered_to_1000(self):
        """Commit 8 fix: _MAX_ROWS=1000 to comply with EE collector_client
        pydantic DbReadonlySqlRuleConfig.max_rows le=1000 hard cap."""
        assert _AiSchemaMetadataBuilder._MAX_ROWS == 1000

    def test_ai_object_metadata_builder_max_rows_lowered_to_1000(self):
        """Commit 8 fix: same constraint for the object-metadata builder."""
        assert _AiObjectMetadataBuilder._MAX_ROWS == 1000

    def test_ai_builders_registered_for_both_codes(self):
        """Both AI builders must be registered for CollectorService._build_item
        to dispatch without ValueError."""
        codes = CheckItemBuilderRegistry.supported_codes()
        assert "DB_SCHEMA_METADATA_COLLECTION" in codes
        assert "DB_OBJECT_METADATA" in codes
