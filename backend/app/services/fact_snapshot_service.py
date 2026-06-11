"""FactSnapshotService — create asset_fact_snapshot + asset_fact_value from collector results."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    AssetFactSnapshot,
    AssetFactValue,
    CollectorRunItem,
)


class FactSnapshotService:
    """Create fact snapshot and values from collector callback results."""

    # Fact collection check codes
    FACT_CHECK_CODES = {
        "OS_BASIC_FACT_COLLECTION",
        "DB_BASIC_FACT_COLLECTION",
        "DB_VERSION_FACT_COLLECTION",
        "DB_ROLE_FACT_COLLECTION",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def is_fact_collection(check_code: str) -> bool:
        """Return True if this check_code collects facts (not port check)."""
        return check_code in FactSnapshotService.FACT_CHECK_CODES

    @staticmethod
    def create_from_collector_result(
        db: Session,
        *,
        run_item: CollectorRunItem,
        raw_result: dict[str, Any],
    ) -> AssetFactSnapshot | None:
        """Create an asset_fact_snapshot and its fact_value rows.

        Args:
            db: Database session (caller manages transaction).
            run_item: The CollectorRunItem row.
            raw_result: The item's raw_result dict from the callback payload.

        Returns:
            The created AssetFactSnapshot, or None if no facts are present.
        """
        target_type = run_item.target_scope
        target_id = (
            int(run_item.db_instance_id)
            if target_type == "db_instance" and run_item.db_instance_id
            else int(run_item.server_id) if target_type == "server" and run_item.server_id
            else None
        )
        if target_id is None:
            return None

        facts = raw_result.get("facts") or []
        if not facts:
            return None

        now = datetime.utcnow()
        snapshot_id = FactSnapshotService._generate_snapshot_id()

        snapshot = AssetFactSnapshot(
            snapshot_id=snapshot_id,
            target_type=target_type,
            target_id=target_id,
            source_run_id=run_item.run_id,
            source_item_key=run_item.item_key,
            check_code=run_item.check_code,
            collected_at=now,
            fact_count=len(facts),
            raw_payload=raw_result,
            created_at=now,
        )
        db.add(snapshot)
        db.flush()  # get snapshot.id

        for fact in facts:
            fact_key = str(fact.get("fact_key", ""))
            fact_value = fact.get("fact_value")
            fact_type = str(fact.get("fact_type") or FactSnapshotService._infer_fact_type(fact_value))

            value = AssetFactValue(
                snapshot_id=int(snapshot.id),
                fact_key=fact_key,
                fact_value=fact_value,
                fact_type=fact_type,
                collected_at=now,
                created_at=now,
            )
            db.add(value)

        return snapshot

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_snapshot_id() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(4).upper()
        return f"SNAP-{timestamp}-{suffix}"

    @staticmethod
    def _infer_fact_type(value: Any) -> str:
        if value is None:
            return "string"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, (dict, list)):
            return "json"
        return "string"
