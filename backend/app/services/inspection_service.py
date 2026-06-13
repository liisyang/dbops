from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    CollectorBatchRun,
    CollectorRun,
    CollectorRunItem,
    InspectionItem,
    InspectionResult,
    InspectionTask,
)
from app.schemas.collector import BatchRunCreateRequest, BatchRunFiltersRequest, CollectorCallbackItem, CollectorInspectionCallbackItem
from app.schemas.inspection import InspectionItemCreateRequest, InspectionItemUpdateRequest, InspectionTaskCreateRequest
from app.services.batch_collector_service import BatchCollectorService
from app.services.check_item_builder_registry import CheckItemBuilderRegistry


class InspectionService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _generate_task_code() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3).upper()
        return f"INSP-{timestamp}-{suffix}"

    @staticmethod
    def _normalize_task_status(status: str | None) -> str:
        normalized = (status or "").strip().lower()
        mapping = {
            "pending": "pending",
            "dispatching": "running",
            "launching": "running",
            "launched": "running",
            "running": "running",
            "success": "success",
            "partial_success": "partial_success",
            "failed": "failed",
            "cancelled": "cancelled",
            "canceled": "cancelled",
        }
        return mapping.get(normalized, "pending")

    @staticmethod
    def _normalize_result_status(status: str | None) -> str:
        normalized = (status or "").strip().lower()
        if normalized in {"normal", "abnormal", "warning", "unknown"}:
            return normalized
        return "unknown"

    @staticmethod
    def _item_to_dict(item: InspectionItem) -> dict[str, Any]:
        return {
            "id": int(item.id),
            "item_code": item.item_code,
            "item_name": item.item_name,
            "check_code": item.check_code,
            "target_scope": item.target_scope,
            "severity": item.severity,
            "enabled": bool(item.enabled),
            "description": item.description,
            "rule_config": item.rule_config or {},
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _task_to_dict(task: InspectionTask) -> dict[str, Any]:
        return {
            "id": int(task.id),
            "task_code": task.task_code,
            "task_name": task.task_name,
            "run_type": task.run_type or "inspection",
            "target_scope": task.target_scope,
            "status": task.status,
            "schedule_id": task.schedule_id,
            "batch_run_id": task.batch_run_id,
            "check_codes": list(task.check_codes or []),
            "item_codes": list(task.item_codes or []),
            "asset_ids": list(task.asset_ids or []),
            "request_payload": task.request_payload or {},
            "created_by": task.created_by,
            "error_message": task.error_message,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    @staticmethod
    def _result_to_dict(result: InspectionResult, item_map: dict[int, InspectionItem]) -> dict[str, Any]:
        item = item_map.get(int(result.item_id)) if result.item_id is not None else None
        return {
            "id": int(result.id),
            "task_id": int(result.task_id),
            "item_id": result.item_id,
            "item_code": item.item_code if item else None,
            "item_name": item.item_name if item else None,
            "batch_run_id": result.batch_run_id,
            "collector_run_id": result.collector_run_id,
            "collector_run_item_id": result.collector_run_item_id,
            "target_type": result.target_type,
            "target_id": int(result.target_id),
            "result_code": result.result_code,
            "result_status": result.result_status,
            "severity": result.severity,
            "message": result.message,
            "evidence": result.evidence or {},
            "detected_at": result.detected_at,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
        }

    @staticmethod
    def ensure_default_items(db: Session) -> None:
        defaults = CheckItemBuilderRegistry.inspection_defaults()
        if not defaults:
            return

        existing = db.query(InspectionItem).all()
        existing_map = {row.item_code: row for row in existing}
        changed = False

        for row in defaults:
            current = existing_map.get(row["item_code"])
            if current is None:
                db.add(InspectionItem(**row))
                changed = True
                continue

            if not current.check_code:
                current.check_code = row["check_code"]
                changed = True
            if not current.target_scope:
                current.target_scope = row["target_scope"]
                changed = True
            if not current.severity:
                current.severity = row["severity"]
                changed = True

        if changed:
            db.commit()

    @staticmethod
    def list_items(db: Session, *, enabled: bool | None = None) -> list[dict[str, Any]]:
        InspectionService.ensure_default_items(db)
        query = db.query(InspectionItem)
        if enabled is not None:
            query = query.filter(InspectionItem.enabled == enabled)
        rows = query.order_by(InspectionItem.id.asc()).all()
        return [InspectionService._item_to_dict(row) for row in rows]

    @staticmethod
    def create_item(db: Session, *, payload: InspectionItemCreateRequest) -> dict[str, Any]:
        existing = db.query(InspectionItem).filter(InspectionItem.item_code == payload.item_code).first()
        if existing:
            raise ValueError(f"item_code 已存在: {payload.item_code}")

        row = InspectionItem(**payload.model_dump(mode="json"))
        db.add(row)
        db.commit()
        db.refresh(row)
        return InspectionService._item_to_dict(row)

    @staticmethod
    def update_item(db: Session, *, item_id: int, payload: InspectionItemUpdateRequest) -> dict[str, Any]:
        row = db.query(InspectionItem).filter(InspectionItem.id == item_id).first()
        if not row:
            raise LookupError(f"巡检项不存在: {item_id}")

        data = payload.model_dump(exclude_unset=True, mode="json")
        for key, value in data.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return InspectionService._item_to_dict(row)

    @staticmethod
    def create_task(
        db: Session,
        *,
        payload: InspectionTaskCreateRequest,
        requested_by: str | None,
    ) -> dict[str, Any]:
        InspectionService.ensure_default_items(db)

        requested_item_codes = sorted(set(code.strip() for code in payload.item_codes if code and code.strip()))
        if not requested_item_codes:
            raise ValueError("item_codes 不能为空")

        rows = (
            db.query(InspectionItem)
            .filter(InspectionItem.item_code.in_(requested_item_codes), InspectionItem.enabled == True)  # noqa: E712
            .all()
        )
        enabled_codes = {row.item_code for row in rows}
        missing = [code for code in requested_item_codes if code not in enabled_codes]
        if missing:
            raise ValueError(f"巡检项不存在或未启用: {missing}")

        check_codes = CheckItemBuilderRegistry.resolve_check_codes_for_inspection_items(requested_item_codes)
        if not check_codes:
            raise ValueError("无法为所选巡检项解析 check_codes")

        # Fleet-scan footgun guard (Phase 3.4):
        # if neither asset_ids nor db_type_code is provided, the batch layer
        # will fan out to every asset in the scope. Require an explicit opt-in
        # so an empty form cannot accidentally trigger a fleet-wide scan.
        if not (payload.asset_ids or payload.db_type_code):
            if not payload.confirm_fleet_scan:
                raise ValueError(
                    "未指定资产范围：请提供 asset_ids 或 db_type_code，或显式设置 confirm_fleet_scan=true 以执行全量巡检"
                )

        # Build filters when asset_ids is not provided
        batch_filters = None
        if not payload.asset_ids:
            batch_filters_dict: dict[str, Any] = {}
            if payload.db_type_code:
                batch_filters_dict["db_type_code"] = payload.db_type_code
            batch_filters = BatchRunFiltersRequest(**batch_filters_dict) if batch_filters_dict else None

        batch_payload = BatchRunCreateRequest(
            run_type="inspection",
            target_scope=payload.target_scope,
            asset_ids=payload.asset_ids,
            filters=batch_filters,
            check_codes=check_codes,
            include_related_server=payload.include_related_server,
            max_items_per_dispatch=payload.max_items_per_dispatch,
            timeout_seconds=payload.timeout_seconds,
        )
        batch = BatchCollectorService.create_batch_run(db, payload=batch_payload, requested_by=requested_by)
        task = InspectionTask(
            task_code=InspectionService._generate_task_code(),
            task_name=payload.task_name,
            schedule_id=payload.schedule_id,
            batch_run_id=int(batch["batch_run_id"]),
            run_type="inspection",
            target_scope=payload.target_scope,
            status=InspectionService._normalize_task_status(batch.get("status")),
            check_codes=check_codes,
            item_codes=requested_item_codes,
            asset_ids=payload.asset_ids or [],
            request_payload={
                "task_payload": payload.model_dump(mode="json"),
                "batch_payload": batch_payload.model_dump(mode="json"),
                "batch_result": batch,
                **(payload.request_payload or {}),
            },
            created_by=requested_by,
            started_at=InspectionService._now(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {
            "detail": "launched",
            "task_id": int(task.id),
            "task_code": task.task_code,
            "batch_run_id": int(task.batch_run_id),
            "status": task.status,
            "dispatch_count": int(batch.get("dispatch_count") or 0),
            "total_item_count": int(batch.get("total_item_count") or 0),
        }

    @staticmethod
    def _sync_task_status(task: InspectionTask, batch: CollectorBatchRun | None) -> bool:
        if batch is None:
            return False
        before_status = task.status
        task.status = InspectionService._normalize_task_status(batch.status)
        task.error_message = batch.error_message
        if task.started_at is None:
            task.started_at = batch.started_at or task.created_at
        if task.status in {"success", "partial_success", "failed", "cancelled"}:
            task.finished_at = batch.finished_at or InspectionService._now()
        return task.status != before_status

    @staticmethod
    def list_tasks(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.query(InspectionTask).order_by(InspectionTask.created_at.desc()).limit(limit).all()
        batch_ids = [int(row.batch_run_id) for row in rows if row.batch_run_id is not None]
        batch_map: dict[int, CollectorBatchRun] = {}
        if batch_ids:
            batches = db.query(CollectorBatchRun).filter(CollectorBatchRun.id.in_(batch_ids)).all()
            batch_map = {int(row.id): row for row in batches}

        changed = False
        for row in rows:
            if row.batch_run_id is None:
                continue
            changed = InspectionService._sync_task_status(row, batch_map.get(int(row.batch_run_id))) or changed
        if changed:
            db.commit()
        return [InspectionService._task_to_dict(row) for row in rows]

    @staticmethod
    def get_task(db: Session, *, task_id: int) -> dict[str, Any]:
        row = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
        if not row:
            raise LookupError(f"巡检任务不存在: {task_id}")
        if row.batch_run_id is not None:
            batch = db.query(CollectorBatchRun).filter(CollectorBatchRun.id == row.batch_run_id).first()
            if InspectionService._sync_task_status(row, batch):
                db.commit()
        return InspectionService._task_to_dict(row)

    @staticmethod
    def list_results(
        db: Session,
        *,
        task_id: int | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        result_status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = db.query(InspectionResult)
        if task_id is not None:
            query = query.filter(InspectionResult.task_id == task_id)
        if target_type:
            query = query.filter(InspectionResult.target_type == target_type)
        if target_id is not None:
            query = query.filter(InspectionResult.target_id == target_id)
        if result_status:
            query = query.filter(InspectionResult.result_status == result_status)

        rows = query.order_by(InspectionResult.detected_at.desc(), InspectionResult.id.desc()).limit(limit).all()
        item_ids = [int(row.item_id) for row in rows if row.item_id is not None]
        item_map: dict[int, InspectionItem] = {}
        if item_ids:
            items = db.query(InspectionItem).filter(InspectionItem.id.in_(item_ids)).all()
            item_map = {int(row.id): row for row in items}
        return [InspectionService._result_to_dict(row, item_map) for row in rows]

    @staticmethod
    def _resolve_task_by_run(db: Session, run: CollectorRun) -> InspectionTask | None:
        if run.batch_run_id is None:
            return None
        return (
            db.query(InspectionTask)
            .filter(InspectionTask.batch_run_id == run.batch_run_id)
            .order_by(InspectionTask.id.desc())
            .first()
        )

    @staticmethod
    def _merge_explicit_results(
        *,
        explicit: list[CollectorInspectionCallbackItem],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in explicit:
            rows.append(
                {
                    "item_code": row.item_code,
                    "result_code": row.result_code or row.item_code,
                    "result_status": row.result_status,
                    "target_scope": row.target_scope,
                    "asset_id": int(row.asset_id),
                    "severity": row.severity,
                    "message": row.message,
                    "check_code": row.check_code or "",
                    "evidence": row.evidence or {},
                }
            )
        return rows

    @staticmethod
    def _merge_derived_results(
        *,
        callback_items: list[CollectorCallbackItem],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for callback_item in callback_items:
            rows.extend(
                CheckItemBuilderRegistry.build_inspection_results_from_callback(
                    check_code=callback_item.check_code,
                    status=callback_item.status,
                    target_scope=callback_item.target_scope,
                    asset_id=int(callback_item.asset_id),
                    item_key=callback_item.item_key,
                    message=callback_item.message,
                    raw_result=callback_item.raw_result or {},
                )
            )
        return rows

    @staticmethod
    def save_callback_results(
        db: Session,
        *,
        run: CollectorRun,
        callback_items: list[CollectorCallbackItem],
        explicit_results: list[CollectorInspectionCallbackItem] | None = None,
    ) -> int:
        task = InspectionService._resolve_task_by_run(db, run)
        if task is None:
            return 0

        merged_results = (
            InspectionService._merge_explicit_results(explicit=explicit_results)
            if explicit_results
            else InspectionService._merge_derived_results(callback_items=callback_items)
        )
        if not merged_results:
            return 0

        item_codes = sorted(set(row["item_code"] for row in merged_results))
        items = db.query(InspectionItem).filter(InspectionItem.item_code.in_(item_codes)).all()
        item_map = {row.item_code: row for row in items}

        run_items = (
            db.query(CollectorRunItem)
            .filter(CollectorRunItem.collector_run_id == run.id)
            .all()
        )
        run_item_map = {row.item_key: row for row in run_items}

        saved = 0
        for row in merged_results:
            item = item_map.get(row["item_code"])
            if item is None:
                continue

            evidence = row.get("evidence") or {}
            collector_item_key = evidence.get("collector_item_key")
            collector_run_item = run_item_map.get(collector_item_key) if collector_item_key else None
            collector_run_item_id = int(collector_run_item.id) if collector_run_item is not None else None

            # Phase 3.4 audit policy: always INSERT a new row.
            # We intentionally do NOT upsert by (task_id, collector_run_item_id, result_code)
            # so retried callbacks and status transitions are preserved as separate rows.
            # Reports / dashboards can dedupe at the read layer (latest by detected_at).
            new_row = InspectionResult(
                task_id=int(task.id),
                item_id=int(item.id),
                batch_run_id=task.batch_run_id,
                collector_run_id=int(run.id),
                collector_run_item_id=collector_run_item_id,
                target_type=row["target_scope"],
                target_id=int(row["asset_id"]),
                result_code=row.get("result_code") or row["item_code"],
                result_status=InspectionService._normalize_result_status(row.get("result_status")),
                severity=row.get("severity") or item.severity,
                message=row.get("message"),
                evidence=evidence,
                detected_at=InspectionService._now(),
            )
            db.add(new_row)

            saved += 1

        return saved
