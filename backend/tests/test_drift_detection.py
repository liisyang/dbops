"""Tests for DriftDetectionService — role mapping and field mapping."""

import pytest

from app.models.dbops_assets import (
    AssetDriftRecord,
)
from app.services.drift_detection_service import DriftDetectionService


class TestDriftDetectionService:

    def test_role_map_sqlserver(self):
        """SQL Server role mapping works correctly."""
        assert DriftDetectionService._map_role("sqlserver", "PRIMARY") == "primary"
        assert DriftDetectionService._map_role("sqlserver", "SECONDARY") == "standby"
        assert DriftDetectionService._map_role("sqlserver", "SINGLE") == "single"
        assert DriftDetectionService._map_role("sqlserver", "UNKNOWN") == "unknown"
        assert DriftDetectionService._map_role("sqlserver", "BOGUS") == "unknown"

    def test_role_map_oracle(self):
        """Oracle role mapping works correctly."""
        assert DriftDetectionService._map_role("oracle", "PRIMARY") == "primary"
        assert DriftDetectionService._map_role("oracle", "PHYSICAL STANDBY") == "standby"
        assert DriftDetectionService._map_role("oracle", "LOGICAL STANDBY") == "standby"
        assert DriftDetectionService._map_role("oracle", "UNKNOWN") == "unknown"

    def test_role_map_postgresql(self):
        """PostgreSQL role mapping works correctly."""
        assert DriftDetectionService._map_role("postgresql", "primary") == "primary"
        assert DriftDetectionService._map_role("postgresql", "standby") == "standby"
        assert DriftDetectionService._map_role("postgresql", "unknown") == "unknown"

    def test_role_map_case_insensitive_db_type(self):
        """Role mapping is case-insensitive for db_type_code."""
        assert DriftDetectionService._map_role("SQLSERVER", "PRIMARY") == "primary"
        assert DriftDetectionService._map_role("Oracle", "PRIMARY") == "primary"
        assert DriftDetectionService._map_role("PostgreSQL", "primary") == "primary"

    def test_field_mapping_has_server_fields(self):
        """Server-level fields are in FIELD_MAPPING."""
        server_keys = {
            k for k, (t, _, _) in DriftDetectionService.FIELD_MAPPING.items()
            if t == "server"
        }
        assert "hostname" in server_keys
        assert "primary_ip" in server_keys
        assert "cpu_cores" in server_keys

    def test_field_mapping_has_db_instance_fields(self):
        """DB instance-level fields are in FIELD_MAPPING."""
        db_keys = {
            k for k, (t, _, _) in DriftDetectionService.FIELD_MAPPING.items()
            if t == "db_instance"
        }
        assert "instance_name" in db_keys
        assert "service_name" in db_keys
        assert "server_port" in db_keys
        assert "node_role" in db_keys

    def test_drift_record_model_exists(self):
        """AssetDriftRecord model exists with expected columns."""
        cols = {c.name for c in AssetDriftRecord.__table__.columns}
        required = {
            "id", "snapshot_id", "proposal_id", "target_type", "target_id",
            "field_path", "expected_value", "actual_value", "drift_type",
            "severity", "resolved", "resolved_at",
        }
        for field in required:
            assert field in cols, f"AssetDriftRecord missing field: {field}"

    def test_drift_type_constraint(self):
        """Drift type constraint exists."""
        assert "drift_type" in AssetDriftRecord.__table__.columns
        # Verify the column is defined as non-nullable
        col = AssetDriftRecord.__table__.columns["drift_type"]
        assert not col.nullable, "drift_type must be NOT NULL"

    def test_memory_mb_converter_in_field_mapping(self):
        """Memory MB→GB conversion is in the field mapping."""
        assert "memory_mb" in DriftDetectionService.FIELD_MAPPING
        target_type, field_name, converter = DriftDetectionService.FIELD_MAPPING["memory_mb"]
        assert target_type == "server"
        assert field_name == "memory_mb_to_gb"
