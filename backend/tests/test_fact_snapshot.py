"""Tests for FactSnapshotService — model and logic verification."""

import pytest

from app.models.dbops_assets import (
    AssetFactSnapshot,
    AssetFactValue,
)
from app.services.fact_snapshot_service import FactSnapshotService


class TestFactSnapshotService:

    def test_models_exist_and_have_expected_fields(self):
        """AssetFactSnapshot and AssetFactValue models exist with expected columns."""
        snap_cols = {c.name for c in AssetFactSnapshot.__table__.columns}
        required_snap = {
            "id", "snapshot_id", "run_id", "collector_run_id", "item_key",
            "check_code", "target_type", "target_id", "target_host",
            "snapshot_status", "error_code", "raw_result",
        }
        for field in required_snap:
            assert field in snap_cols, f"AssetFactSnapshot missing field: {field}"

        val_cols = {c.name for c in AssetFactValue.__table__.columns}
        required_val = {
            "id", "snapshot_id", "fact_key", "fact_value",
            "fact_category", "source_query", "is_null",
        }
        for field in required_val:
            assert field in val_cols, f"AssetFactValue missing field: {field}"

    def test_snapshot_model_has_target_fields(self):
        """AssetFactSnapshot supports both server and db_instance targets."""
        assert "target_type" in AssetFactSnapshot.__table__.columns
        assert "target_port" in AssetFactSnapshot.__table__.columns
        assert "db_type_code" in AssetFactSnapshot.__table__.columns
        assert "credential_profile_id" in AssetFactSnapshot.__table__.columns

    def test_snapshot_status_constraint_values(self):
        """Snapshot status constraint allows expected values."""
        col = AssetFactSnapshot.__table__.columns["snapshot_status"]
        # Check constraint exists (server_default is text("'ok'"))
        assert col.server_default is not None
        assert "ok" in str(col.server_default.arg)

    def test_snapshot_id_generation_format(self):
        """_generate_snapshot_id produces SNAP-YYYYMMDDHHMMSS-RANDOM6 format."""
        snap_id = FactSnapshotService._generate_snapshot_id()
        assert snap_id.startswith("SNAP-")
        # Format: SNAP-YYYYMMDDHHMMSS-RANDOM6
        # After stripping SNAP-, we have YYYYMMDDHHMMSS-RANDOM6
        rest = snap_id[5:]  # strip "SNAP-"
        parts = rest.split("-")
        assert len(parts) == 2  # YYYYMMDDHHMMSS and RANDOM6
        # Timestamp part should be 14 digits
        assert len(parts[0]) == 14
        # Random part should be 6 chars (hex)
        assert len(parts[1]) == 6

    def test_snapshot_id_uniqueness(self):
        """Consecutive calls produce different snapshot IDs."""
        ids = {FactSnapshotService._generate_snapshot_id() for _ in range(10)}
        assert len(ids) == 10
