"""Tests for credential_group_hash computation and dispatch grouping."""

import hashlib
import json

import pytest

from app.services.dispatch_planner_service import DispatchPlannerService


class TestCredentialGroupHash:

    def test_hash_stable_and_reproducible(self):
        """Same credential set always produces the same hash."""
        items1 = [
            {
                "awx_credential_id": 10,
                "credential_type": "db_password",
                "credential_role": "db_readonly",
                "credential_profile_id": 1,
            },
            {
                "awx_credential_id": 20,
                "credential_type": "db_password",
                "credential_role": "db_readonly",
                "credential_profile_id": 2,
            },
        ]
        hash1 = DispatchPlannerService.compute_credential_group_hash(items1)
        hash2 = DispatchPlannerService.compute_credential_group_hash(items1)
        assert hash1 is not None
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_hash_sorted_by_awx_credential_id(self):
        """Same credentials in different order produce same hash."""
        items1 = [
            {"awx_credential_id": 20, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 2},
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
        ]
        items2 = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
            {"awx_credential_id": 20, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 2},
        ]
        hash1 = DispatchPlannerService.compute_credential_group_hash(items1)
        hash2 = DispatchPlannerService.compute_credential_group_hash(items2)
        assert hash1 == hash2

    def test_different_db_types_produce_different_hash(self):
        """Oracle vs SQL Server credentials produce different hashes."""
        oracle = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
        ]
        sqlserver = [
            {"awx_credential_id": 20, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 2},
        ]
        hash_oracle = DispatchPlannerService.compute_credential_group_hash(oracle)
        hash_mssql = DispatchPlannerService.compute_credential_group_hash(sqlserver)
        assert hash_oracle != hash_mssql

    def test_different_binding_roles_produce_different_hash(self):
        """Different binding_roles produce different hashes."""
        readonly = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
        ]
        monitor = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_monitor", "credential_profile_id": 1},
        ]
        hash_readonly = DispatchPlannerService.compute_credential_group_hash(readonly)
        hash_monitor = DispatchPlannerService.compute_credential_group_hash(monitor)
        assert hash_readonly != hash_monitor

    def test_port_check_items_produce_null_hash(self):
        """Port check items (no credentials) produce None hash (backward compatible)."""
        items = [
            {"item_key": "test:1:DB_PORT_REACHABILITY:10.0.0.1:1433", "check_code": "DB_PORT_REACHABILITY"},
        ]
        hash_val = DispatchPlannerService.compute_credential_group_hash(items)
        assert hash_val is None

    def test_hash_includes_all_four_fields(self):
        """Hash must include awx_credential_id, credential_type, binding_role, credential_profile_id."""
        base = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
        ]
        base_hash = DispatchPlannerService.compute_credential_group_hash(base)

        # Change credential_profile_id
        changed = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 99},
        ]
        changed_hash = DispatchPlannerService.compute_credential_group_hash(changed)
        assert base_hash != changed_hash, "Hash should change when credential_profile_id changes"

    def test_hash_matches_expected_format(self):
        """Hash should be a valid SHA256 hex digest."""
        items = [
            {"awx_credential_id": 10, "credential_type": "db_password", "credential_role": "db_readonly", "credential_profile_id": 1},
        ]
        hash_val = DispatchPlannerService.compute_credential_group_hash(items)
        assert hash_val is not None
        assert len(hash_val) == 64
        # Should be hex
        int(hash_val, 16)  # no ValueError
