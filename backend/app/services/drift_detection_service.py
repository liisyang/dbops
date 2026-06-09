"""Drift detection service — compares fact snapshots against formal asset fields.

Generates asset_drift_record for mismatches.
Optionally generates asset_change_proposal (reusing existing proposal system).

CRITICAL: NEVER auto-updates formal asset fields.
Changes only via approve + apply of proposals.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    AssetChangeProposal,
    AssetDriftRecord,
    AssetFactSnapshot,
    AssetFactValue,
    DbInstance,
    Server,
)
from app.services.asset_proposal_service import AssetProposalService


class DriftDetectionService:
    """Detect drifts between collected facts and formal asset fields.

    Reuses existing asset_change_proposal for proposals.
    Creates independent asset_drift_record for audit trail.
    NEVER auto-updates formal asset fields.
    """

    # Field mapping: fact_key → (target_type, formal_field_name, converter)
    # converter=None means direct comparison
    FIELD_MAPPING: dict[str, tuple[str, str, Any | None]] = {
        # Server fields
        "hostname": ("server", "hostname", None),
        "primary_ip": ("server", "ip_address", str),
        "cpu_cores": ("server", "cpu_cores", int),
        "memory_mb": ("server", "memory_mb_to_gb", None),  # special: MB→GB
        # DB Instance fields
        "instance_name": ("db_instance", "instance_name", None),
        "service_name": ("db_instance", "service_name", None),
        "server_port": ("db_instance", "port", int),
        "listener_port": ("db_instance", "port", int),
        "node_role": ("db_instance", "node_role", None),
        "database_role": ("db_instance", "node_role", None),
    }

    # Role mapping: connector-reported → DBOPS node_role enum
    ROLE_MAP_SQLSERVER = {
        "PRIMARY": "primary",
        "SECONDARY": "standby",
        "SINGLE": "single",
        "UNKNOWN": "unknown",
    }

    ROLE_MAP_ORACLE = {
        "PRIMARY": "primary",
        "PHYSICAL STANDBY": "standby",
        "LOGICAL STANDBY": "standby",
        "UNKNOWN": "unknown",
    }

    ROLE_MAP_POSTGRESQL = {
        "primary": "primary",
        "standby": "standby",
    }

    @staticmethod
    def detect_for_snapshot(
        db: Session,
        snapshot: AssetFactSnapshot,
    ) -> list[AssetDriftRecord]:
        """Detect drifts for a single fact snapshot.

        Compares fact values against formal asset fields.
        Generates drift records + change proposals.

        Returns list of created drift records.
        """
        drifts: list[AssetDriftRecord] = []

        # Get fact values for this snapshot
        fact_values = (
            db.query(AssetFactValue)
            .filter(AssetFactValue.snapshot_id == snapshot.id)
            .all()
        )

        if not fact_values:
            return drifts

        for fv in fact_values:
            drift = DriftDetectionService._check_fact_against_asset(
                db, snapshot, fv
            )
            if drift:
                db.add(drift)
                db.flush()
                drifts.append(drift)

                # Optionally create change proposal for significant drifts
                if drift.drift_type == "value_mismatch" and drift.severity in ("warning", "critical"):
                    DriftDetectionService._create_drift_proposal(db, drift)

        return drifts

    @staticmethod
    def _check_fact_against_asset(
        db: Session,
        snapshot: AssetFactSnapshot,
        fv: AssetFactValue,
    ) -> AssetDriftRecord | None:
        """Check a single fact value against the corresponding formal asset field.

        Returns a drift record if mismatch detected, None otherwise.
        """
        mapping = DriftDetectionService.FIELD_MAPPING.get(fv.fact_key)
        if mapping is None:
            return None  # No mapping defined for this fact key

        target_type, field_name, converter = mapping

        # Skip if the fact doesn't match the snapshot target type
        if target_type != snapshot.target_type:
            return None

        # Get the formal asset
        if target_type == "server":
            asset = db.query(Server).filter(Server.id == snapshot.target_id).first()
        elif target_type == "db_instance":
            asset = db.query(DbInstance).filter(DbInstance.id == snapshot.target_id).first()
        else:
            return None

        if not asset:
            return None

        actual_value = fv.fact_value

        # Special handling for memory_mb → memory_gb conversion
        if fv.fact_key == "memory_mb":
            expected_value = getattr(asset, "memory_gb", None)
            if expected_value is not None and actual_value is not None:
                try:
                    actual_gb = round(float(actual_value) / 1024.0, 2)
                    expected_gb = round(float(expected_value), 2)
                    if abs(actual_gb - expected_gb) > 0.5:  # 0.5 GB tolerance
                        return AssetDriftRecord(
                            snapshot_id=int(snapshot.id),
                            target_type=target_type,
                            target_id=snapshot.target_id,
                            field_path="memory_gb",
                            expected_value=expected_gb,
                            actual_value=actual_gb,
                            drift_type="value_mismatch",
                            severity="warning",
                        )
                except (ValueError, TypeError):
                    pass
            return None

        # Get expected value from formal asset
        if field_name == "ip_address" and target_type == "server":
            expected_value = str(asset.ip_address) if asset.ip_address else None
        else:
            expected_value = getattr(asset, field_name, None)

        # Apply converter to actual value if specified
        if converter and actual_value is not None:
            try:
                actual_value = converter(actual_value)
            except (ValueError, TypeError):
                pass

        # Role mapping for node_role / database_role
        if field_name == "node_role" and actual_value is not None:
            db_type = snapshot.db_type_code or ""
            actual_value = DriftDetectionService._map_role(db_type, str(actual_value))

        # Compare values
        if expected_value is not None and actual_value is not None:
            expected_str = str(expected_value)
            actual_str = str(actual_value)
            if expected_str != actual_str:
                return AssetDriftRecord(
                    snapshot_id=int(snapshot.id),
                    target_type=target_type,
                    target_id=snapshot.target_id,
                    field_path=field_name,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    drift_type="value_mismatch",
                    severity="warning",
                )
        elif actual_value is not None and expected_value is None:
            # Field exists in fact but not in formal asset — extra info
            return AssetDriftRecord(
                snapshot_id=int(snapshot.id),
                target_type=target_type,
                target_id=snapshot.target_id,
                field_path=field_name,
                expected_value=None,
                actual_value=actual_value,
                drift_type="extra",
                severity="info",
            )
        elif actual_value is None and expected_value is not None:
            # Field exists in formal asset but not in fact — missing
            return AssetDriftRecord(
                snapshot_id=int(snapshot.id),
                target_type=target_type,
                target_id=snapshot.target_id,
                field_path=field_name,
                expected_value=expected_value,
                actual_value=None,
                drift_type="missing",
                severity="info",
            )

        return None  # Match or both None

    @staticmethod
    def _map_role(db_type_code: str, fact_role: str) -> str:
        """Map connector-reported role to DBOPS node_role enum."""
        role = fact_role.upper() if fact_role else "UNKNOWN"
        db_type = db_type_code.lower()
        if db_type == "sqlserver":
            return DriftDetectionService.ROLE_MAP_SQLSERVER.get(role, "unknown")
        elif db_type == "oracle":
            return DriftDetectionService.ROLE_MAP_ORACLE.get(role, "unknown")
        elif db_type == "postgresql":
            return DriftDetectionService.ROLE_MAP_POSTGRESQL.get(
                fact_role.lower(), "unknown"
            )
        return "unknown"

    @staticmethod
    def _create_drift_proposal(
        db: Session,
        drift_record: AssetDriftRecord,
    ) -> AssetChangeProposal | None:
        """Reuse existing AssetProposalService to create a change proposal.

        Only creates proposal for value_mismatch drifts with confidence >= medium.
        Does NOT auto-apply — user must approve + apply.
        """
        if drift_record.drift_type != "value_mismatch":
            return None

        # Determine confidence based on field
        confidence = "medium"
        high_confidence_fields = {"port", "instance_name", "hostname", "primary_ip", "ip_address"}
        if drift_record.field_path in high_confidence_fields:
            confidence = "high"

        try:
            proposal_dict = AssetProposalService.create_proposal(
                db,
                target_type=drift_record.target_type,
                target_id=drift_record.target_id,
                proposal_type="FACT_DRIFT",
                field_path=drift_record.field_path,
                current_value=drift_record.expected_value,
                suggested_value=drift_record.actual_value,
                confidence=confidence,
                evidence={
                    "drift_record_id": int(drift_record.id),
                    "snapshot_id": int(drift_record.snapshot_id),
                    "drift_type": drift_record.drift_type,
                    "severity": drift_record.severity,
                },
                source_run_id=None,
                source_item_key=None,
                requested_by="drift_detection",
            )
            proposal = (
                db.query(AssetChangeProposal)
                .filter(AssetChangeProposal.id == proposal_dict["id"])
                .first()
            )
            if proposal:
                drift_record.proposal_id = int(proposal.id)
            return proposal
        except Exception:
            return None
