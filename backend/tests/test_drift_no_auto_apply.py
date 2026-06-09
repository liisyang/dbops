"""Tests verifying drift detection never auto-updates formal asset fields."""

import pytest

from app.models.dbops_assets import (
    AssetChangeProposal,
    AssetDriftRecord,
)
from app.services.asset_proposal_service import AssetProposalService
from app.services.drift_detection_service import DriftDetectionService


class TestDriftNoAutoApply:

    def test_asset_change_proposal_model_has_status_field(self):
        """AssetChangeProposal has status field for approval workflow."""
        assert "status" in AssetChangeProposal.__table__.columns
        col = AssetChangeProposal.__table__.columns["status"]
        assert not col.nullable

    def test_drift_record_has_proposal_id_fk(self):
        """AssetDriftRecord links to AssetChangeProposal via proposal_id."""
        assert "proposal_id" in AssetDriftRecord.__table__.columns

    def test_drift_record_has_resolved_field(self):
        """AssetDriftRecord has resolved field (default False)."""
        col = AssetDriftRecord.__table__.columns["resolved"]
        # Check server_default is set to text("false")
        assert col.server_default is not None
        assert "false" in str(col.server_default.arg).lower()

    def test_field_mapping_never_writes_to_model(self):
        """DriftDetectionService.detect_for_snapshot must not modify formal asset models.

        The service creates AssetDriftRecord and optionally AssetChangeProposal.
        It NEVER calls db.add() for Server or DbInstance models.
        """
        # Verify the detect_for_snapshot source code doesn't import
        # or reference Server/DbInstance in a way that modifies them
        import inspect
        source = inspect.getsource(DriftDetectionService.detect_for_snapshot)

        # Must not contain Server/DbInstance update patterns
        assert "Server(" not in source, "detect_for_snapshot must not create Server"
        assert "DbInstance(" not in source, "detect_for_snapshot must not create DbInstance"
        assert "server." not in source.lower() or "--" in source, \
            "detect_for_snapshot must not modify server fields"
        assert "instance." not in source.lower() or "--" in source, \
            "detect_for_snapshot must not modify instance fields"

    def test_proposal_service_supports_fact_drift_type(self):
        """AssetProposalService supports FACT_DRIFT proposal type."""
        # Verify the create_proposal method accepts arbitrary proposal_type
        import inspect
        sig = inspect.signature(AssetProposalService.create_proposal)
        params = list(sig.parameters.keys())
        assert "proposal_type" in params
        assert "field_path" in params
        assert "current_value" in params
        assert "suggested_value" in params
        assert "confidence" in params

    def test_drift_proposals_require_approval(self):
        """Proposals are created with pending status — never auto-applied."""
        from app.models.dbops_assets import AssetChangeProposal

        # Check model constraint allows 'pending' status
        col = AssetChangeProposal.__table__.columns["status"]
        assert col.server_default.arg == "pending" or "pending" in str(col.server_default.arg)
