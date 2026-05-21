from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import AssetEventHistory


def record_event(
    db: Session,
    *,
    asset_type: str,
    asset_id: int,
    event_type: str,
    before_status: str | None = None,
    after_status: str | None = None,
    changed_fields: dict[str, Any] | None = None,
    reason: str | None = None,
    operator: str | None = None,
    remark: str | None = None,
    operated_at: datetime | None = None,
) -> AssetEventHistory:
    event = AssetEventHistory(
        asset_type=asset_type,
        asset_id=asset_id,
        event_type=event_type,
        before_status=before_status,
        after_status=after_status,
        changed_fields=dict(changed_fields or {}),
        reason=reason,
        operator=operator,
        remark=remark,
        operated_at=operated_at or datetime.now(),
    )
    db.add(event)
    db.flush()
    return event


def list_events(db: Session, *, asset_type: str, asset_id: int) -> list[AssetEventHistory]:
    rows = db.query(AssetEventHistory).filter_by(asset_type=asset_type, asset_id=asset_id).all()
    return sorted(
        rows,
        key=lambda row: (
            row.operated_at or datetime.min,
            row.id or 0,
        ),
        reverse=True,
    )


def event_to_dict(event: AssetEventHistory) -> dict[str, Any]:
    return {
        "id": event.id,
        "asset_type": event.asset_type,
        "asset_id": event.asset_id,
        "event_type": event.event_type,
        "before_status": event.before_status,
        "after_status": event.after_status,
        "changed_fields": event.changed_fields or {},
        "reason": event.reason,
        "operator": event.operator,
        "operated_at": event.operated_at.isoformat() if event.operated_at else None,
        "remark": event.remark,
    }
