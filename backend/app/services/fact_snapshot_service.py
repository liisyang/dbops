"""Fact snapshot service — creates snapshots and fact values from collector results.

Called during callback processing when a fact collection item completes.
Writes asset_fact_snapshot + asset_fact_value rows.

NEVER auto-updates formal asset fields — drift detection is handled separately.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    AssetFactSnapshot,
    AssetFactValue,
    CollectorRunItem,
    CollectorRunResult,
)


class FactSnapshotService:

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _generate_snapshot_id() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3).upper()
        return f"SNAP-{timestamp}-{suffix}"

    @staticmethod
    def create_from_collector_result(
        db: Session,
        run_item: CollectorRunItem,
        result: CollectorRunResult,
        raw_result: dict[str, Any],
    ) -> AssetFactSnapshot:
        """Create snapshot + fact_value rows from callback raw_result.

        Args:
            db: Database session
            run_item: The CollectorRunItem being processed
            result: The CollectorRunResult being written
            raw_result: The raw_result dict from the callback

        Returns:
            The created AssetFactSnapshot
        """
        now = FactSnapshotService._now()
        snapshot_id = FactSnapshotService._generate_snapshot_id()

        # Determine target_type from item scope
        target_type = run_item.target_scope  # 'db_instance' or 'server'
        target_id = run_item.db_instance_id if target_type == "db_instance" else run_item.server_id
        if target_id is None:
            target_id = run_item.server_id or run_item.db_instance_id or 0

        # Determine snapshot status from raw_result
        result_status = raw_result.get("status", "ok")
        if result_status == "skipped":
            snapshot_status = "skipped"
        elif result_status == "partial":
            snapshot_status = "partial"
        elif result_status in ("failed", "error"):
            snapshot_status = "error"
        else:
            snapshot_status = "ok"

        snapshot = AssetFactSnapshot(
            snapshot_id=snapshot_id,
            run_id=run_item.run_id,
            collector_run_id=int(run_item.collector_run_id),
            item_key=run_item.item_key,
            check_code=run_item.check_code,
            target_type=target_type,
            target_id=int(target_id),
            target_host=run_item.target_host,
            target_port=run_item.target_port,
            db_type_code=raw_result.get("metadata", {}).get("db_type_code"),
            credential_profile_id=raw_result.get("metadata", {}).get("credential_profile_id"),
            snapshot_status=snapshot_status,
            error_code=raw_result.get("error_code"),
            raw_result=raw_result,
            collected_at=now,
        )
        db.add(snapshot)
        db.flush()

        # Create fact_value rows from facts array
        facts = raw_result.get("facts") or []
        for fact in facts:
            fact_value = AssetFactValue(
                snapshot_id=int(snapshot.id),
                fact_key=str(fact.get("key", "")),
                fact_value=fact.get("value"),
                fact_category=str(fact.get("category", "basic")),
                source_query=fact.get("source"),
                is_null=bool(fact.get("is_null", False)),
                collected_at=now,
            )
            db.add(fact_value)

        return snapshot
