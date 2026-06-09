from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import AssetChangeProposal, DbInstance
from app.services.asset_event_history_service import record_event


class AssetProposalService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _to_dict(row: AssetChangeProposal) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "target_type": row.entity_type,
            "target_id": int(row.entity_id),
            "proposal_type": row.proposal_type or row.change_type,
            "field_path": row.field_path,
            "current_value": row.current_value if row.current_value is not None else row.old_value,
            "suggested_value": row.suggested_value if row.suggested_value is not None else row.new_value,
            "confidence": row.confidence,
            "evidence": row.evidence or {},
            "source_run_id": row.source_run_id or row.evidence_run_id,
            "source_item_key": row.source_item_key,
            "status": row.status,
            "requested_by": row.requested_by,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at,
            "applied_at": row.applied_at,
            "rejected_by": row.rejected_by,
            "rejected_reason": row.rejected_reason,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def create_proposal(
        db: Session,
        *,
        target_type: str,
        target_id: int,
        proposal_type: str,
        field_path: str,
        current_value: Any,
        suggested_value: Any,
        confidence: str,
        evidence: dict[str, Any],
        source_run_id: str | None,
        source_item_key: str | None,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        proposal = AssetChangeProposal(
            entity_type=target_type,
            entity_id=target_id,
            change_type=proposal_type,
            proposal_type=proposal_type,
            field_path=field_path,
            old_value=current_value if isinstance(current_value, dict) else {"value": current_value},
            new_value=suggested_value if isinstance(suggested_value, dict) else {"value": suggested_value},
            current_value=current_value,
            suggested_value=suggested_value,
            confidence=confidence,
            evidence_run_id=source_run_id,
            source_run_id=source_run_id,
            source_item_key=source_item_key,
            evidence=evidence or {},
            status="pending",
            requested_by=requested_by,
        )
        db.add(proposal)
        db.flush()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def list_proposals(
        db: Session,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        proposal_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = db.query(AssetChangeProposal)
        if target_type:
            query = query.filter(AssetChangeProposal.entity_type == target_type)
        if target_id is not None:
            query = query.filter(AssetChangeProposal.entity_id == target_id)
        if status:
            query = query.filter(AssetChangeProposal.status == status)
        rows = query.order_by(AssetChangeProposal.created_at.desc()).all()
        if proposal_type:
            rows = [row for row in rows if (row.proposal_type or row.change_type) == proposal_type]
        return [AssetProposalService._to_dict(row) for row in rows]

    @staticmethod
    def approve_proposal(db: Session, *, proposal_id: int, operator: str) -> dict[str, Any]:
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status != "pending":
            raise ValueError("仅 pending 状态可 approve")

        proposal.status = "approved"
        proposal.approved_by = operator
        proposal.approved_at = AssetProposalService._now()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def reject_proposal(db: Session, *, proposal_id: int, operator: str, reason: str | None = None) -> dict[str, Any]:
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status not in {"pending", "approved"}:
            raise ValueError("仅 pending/approved 状态可 reject")

        proposal.status = "rejected"
        proposal.rejected_by = operator
        proposal.rejected_reason = reason
        proposal.updated_at = AssetProposalService._now()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def apply_proposal(db: Session, *, proposal_id: int, operator: str) -> dict[str, Any]:
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status != "approved":
            raise ValueError("apply 仅允许 approved 状态")

        field_path = (proposal.field_path or "").strip()
        if proposal.entity_type == "db_instance" and field_path == "port":
            instance = db.query(DbInstance).filter(DbInstance.id == proposal.entity_id).with_for_update().first()
            if instance is None:
                raise LookupError("proposal 目标实例不存在")

            before_port = instance.port
            before_trust_status = instance.trust_status
            before_reachability_status = instance.reachability_status
            suggested = proposal.suggested_value
            if isinstance(suggested, dict):
                suggested = suggested.get("value")
            instance.port = int(suggested) if suggested is not None else None
            instance.trust_status = "unverified"
            instance.reachability_status = "unknown"
            instance.verify_message = "PORT_CHANGED_PENDING_REVERIFY"
            instance.verify_detail = {
                "proposal_id": int(proposal.id),
                "proposal_type": proposal.proposal_type or proposal.change_type,
                "field_path": field_path,
                "before_port": before_port,
                "after_port": instance.port,
            }
            proposal.status = "applied"
            proposal.applied_at = AssetProposalService._now()

            record_event(
                db,
                asset_type="db_instance",
                asset_id=int(instance.id),
                event_type="ASSET_PROPOSAL_APPLIED",
                before_status=before_trust_status,
                after_status=instance.trust_status,
                changed_fields={
                    "field_path": field_path,
                    "before": before_port,
                    "after": instance.port,
                    "trust_status": instance.trust_status,
                    "reachability_status": instance.reachability_status,
                    "proposal_id": int(proposal.id),
                    "proposal_type": proposal.proposal_type or proposal.change_type,
                },
                reason="apply proposal",
                operator=operator,
            )
            return AssetProposalService._to_dict(proposal)

        raise ValueError("当前仅支持对 db_instance.port 执行 apply")
