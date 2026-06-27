"""
One-shot backfill: insert missing inspection_task_target rows for tasks
created before batch_collector_service.create_batch_run() started returning
asset_ids, then trigger generate_report() so the Tasks list shows a report.

Usage:
    cd backend && .venv/bin/python -m scripts.one_shot_backfill_inspection_task_targets

Safe to re-run: existing task_targets are detected by UNIQUE(task_id, target_id)
and skipped; only missing rows are inserted.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from sqlalchemy import text

# Allow running from project root: ``.venv/bin/python backend/scripts/<this>.py``.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (_PROJECT_ROOT, _BACKEND_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.database import SessionLocal  # noqa: E402
from app.models.dbops_assets import (  # noqa: E402
    DbInstance,
    DbType,
    InspectionTask,
    InspectionTaskTarget,
    Server,
)
from app.services.inspection_service import InspectionService  # noqa: E402


def resolve_target_snapshot(db, instance: DbInstance) -> dict[str, Any]:
    server = db.query(Server).filter(Server.id == instance.server_id).first()
    db_type = (
        db.query(DbType).filter(DbType.id == instance.db_type_id).first()
        if instance.db_type_id
        else None
    )
    return {
        "target_type": "db_instance",
        "target_id": int(instance.id),
        "target_name_snapshot": instance.instance_name,
        "host_snapshot": str(server.ip_address) if server else None,
        "port_snapshot": int(instance.port) if instance.port else None,
        "db_type_code_snapshot": db_type.type_code if db_type else None,
        "asset_snapshot": {
            "instance_name": instance.instance_name,
            "db_version": instance.db_version.version_code if instance.db_version else None,
            "node_role": instance.node_role,
            "cluster_name": instance.cluster.cluster_name if instance.cluster else None,
            "business_system_id": instance.cluster.business_system_id if instance.cluster else None,
            "site_id": server.site_id if server else None,
        },
        "dispatch_status": "dispatched",
        "execution_status": "success",
    }


def main() -> int:
    db = SessionLocal()
    try:
        # Tasks that have ZERO task_targets and are NOT cancelled
        orphan_tasks = (
            db.query(InspectionTask)
            .filter(InspectionTask.status.in_(("success", "partial_success", "failed")))
            .all()
        )
        touched = 0
        for task in orphan_tasks:
            existing = (
                db.query(InspectionTaskTarget)
                .filter(InspectionTaskTarget.task_id == int(task.id))
                .count()
            )
            if existing > 0:
                continue

            # Find instance IDs from collector_run_item for this task's batch_run_id.
            if not task.batch_run_id:
                print(f"[skip] task {task.id} has no batch_run_id")
                continue
            rows = db.execute(
                text(
                    """
                    SELECT DISTINCT cri.db_instance_id
                    FROM dbops.collector_run_item cri
                    JOIN dbops.collector_run cr ON cr.id = cri.collector_run_id
                    WHERE cr.batch_run_id = :bid AND cri.db_instance_id IS NOT NULL
                    """
                ),
                {"bid": int(task.batch_run_id)},
            ).fetchall()
            instance_ids = [int(r[0]) for r in rows if r[0]]
            if not instance_ids:
                print(f"[skip] task {task.id} batch {task.batch_run_id} has no instance ids")
                continue

            instances = (
                db.query(DbInstance)
                .filter(DbInstance.id.in_(instance_ids))
                .all()
            )
            for inst in instances:
                snap = resolve_target_snapshot(db, inst)
                tt = InspectionTaskTarget(
                    task_id=int(task.id),
                    attempt_no=1,
                    **snap,
                )
                db.add(tt)
            db.commit()
            print(
                f"[backfill] task {task.id} ({task.task_code}) "
                f"→ {len(instances)} task_targets from batch {task.batch_run_id}"
            )
            touched += 1

            # Trigger report generation
            db.refresh(task)
            try:
                # generated_reason CHECK only allows auto/manual/regenerate.
                InspectionService.generate_report(
                    db, task, generated_reason="manual"
                )
                print(f"[report] task {task.id} → generated")
            except Exception as exc:  # noqa: BLE001
                print(f"[report] task {task.id} FAILED: {exc!r}")
                db.rollback()

        print(f"\nDone. Backfilled {touched} task(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
