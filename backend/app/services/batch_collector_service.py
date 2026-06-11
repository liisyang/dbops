from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dbops_assets import (
    CollectorBatchRun,
    CollectorDispatchRun,
    CollectorRun,
    CollectorRunItem,
    DbInstance,
    DbType,
    Server,
)
from app.schemas.collector import BatchRunCreateRequest, RetryFailedRequest
from app.services.awx_service import AwxService, AwxServiceError
from app.services.check_item_builder_registry import CheckItemBuilderRegistry
from app.services.dispatch_planner_service import DispatchPlannerService


class BatchCollectorService:
    """Orchestrate batch collector runs with dispatch grouping.

    IMPORTANT: This service MUST NOT contain `if check_code == ...` or
    `elif check_code == ...` branches. All item generation goes through
    CheckItemBuilderRegistry.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _generate_batch_code() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3).upper()  # 6-char hex
        return f"BATCH-{timestamp}-{suffix}"

    @staticmethod
    def _generate_dispatch_code(batch_suffix: str, group_seq: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # group_seq as letter: 0→A, 1→B, ...
        seq_letter = chr(ord("A") + group_seq) if group_seq < 26 else str(group_seq)
        return f"DISPATCH-{timestamp}-{batch_suffix}-{seq_letter}"

    @staticmethod
    def _generate_run_id(group_seq: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(2).upper()  # 4-char random for uniqueness
        return f"RUN-{timestamp}-{group_seq:03d}-{suffix}"

    # === Asset Resolution ===

    @staticmethod
    def resolve_assets(
        db: Session,
        target_scope: str,
        asset_ids: list[int] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve assets into a normalized list of dicts with keys:
        {id, target_scope, server_id?, extra_attrs?, ...}
        """
        if asset_ids:
            return BatchCollectorService._resolve_by_ids(db, target_scope, asset_ids)
        if filters is not None:
            return BatchCollectorService._resolve_by_filters(db, target_scope, filters)
        raise ValueError("必须提供 asset_ids 或 filters")

    @staticmethod
    def _resolve_by_ids(
        db: Session,
        target_scope: str,
        asset_ids: list[int],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if target_scope == "db_instance":
            rows = (
                db.query(DbInstance)
                .filter(DbInstance.id.in_(asset_ids))
                .all()
            )
            found_ids = {r.id for r in rows}
            missing = [aid for aid in asset_ids if aid not in found_ids]
            if missing:
                raise LookupError(f"实例不存在: {missing}")
            for row in rows:
                results.append(
                    {
                        "id": int(row.id),
                        "target_scope": "db_instance",
                        "server_id": int(row.server_id) if row.server_id else None,
                        "extra_attrs": row.extra_attrs or {},
                        "instance_name": row.instance_name or "",
                        "port": row.port,
                    }
                )
        elif target_scope == "server":
            rows = (
                db.query(Server)
                .filter(Server.id.in_(asset_ids))
                .all()
            )
            found_ids = {r.id for r in rows}
            missing = [aid for aid in asset_ids if aid not in found_ids]
            if missing:
                raise LookupError(f"服务器不存在: {missing}")
            for row in rows:
                results.append(
                    {
                        "id": int(row.id),
                        "target_scope": "server",
                        "extra_attrs": row.extra_attrs or {},
                        "hostname": row.hostname or "",
                        "ip_address": str(row.ip_address) if row.ip_address else "",
                    }
                )
        else:
            raise ValueError(f"不支持的 target_scope: {target_scope}")
        return results

    @staticmethod
    def _resolve_by_filters(
        db: Session,
        target_scope: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if target_scope == "db_instance":
            query = db.query(DbInstance)
            if filters.get("db_type_code"):
                query = query.join(DbType).filter(DbType.type_code == filters["db_type_code"])
            if filters.get("status"):
                query = query.filter(DbInstance.status == filters["status"])
            if filters.get("site_id"):
                query = query.join(Server).filter(Server.site_id == int(filters["site_id"]))
            rows = query.all()
            for row in rows:
                results.append(
                    {
                        "id": int(row.id),
                        "target_scope": "db_instance",
                        "server_id": int(row.server_id) if row.server_id else None,
                        "extra_attrs": row.extra_attrs or {},
                        "instance_name": row.instance_name or "",
                        "port": row.port,
                    }
                )
        elif target_scope == "server":
            query = db.query(Server)
            if filters.get("status"):
                query = query.filter(Server.status == filters["status"])
            if filters.get("site_id"):
                query = query.filter(Server.site_id == int(filters["site_id"]))
            rows = query.all()
            for row in rows:
                results.append(
                    {
                        "id": int(row.id),
                        "target_scope": "server",
                        "extra_attrs": row.extra_attrs or {},
                        "hostname": row.hostname or "",
                        "ip_address": str(row.ip_address) if row.ip_address else "",
                    }
                )
        else:
            raise ValueError(f"不支持的 target_scope: {target_scope}")
        return results

    @staticmethod
    def _parse_group_key(group_key: str) -> tuple[str, str, str]:
        """Parse a dispatch group key into (network_zone, awx_instance_group, credential_hash).

        Supported formats:
          IG                           → ("", "IG", "")
          IG|cred_hash                 → ("", "IG", "cred_hash")
          NZ|IG                        → ("NZ", "IG", "")
          NZ|IG|cred_hash              → ("NZ", "IG", "cred_hash")
        """
        parts = group_key.split("|")
        if len(parts) == 1:
            return "", parts[0], ""
        if len(parts) == 2:
            # Could be NZ|IG or IG|cred_hash
            # Heuristic: credential hashes are 16-char hex strings
            second = parts[1]
            if len(second) == 16 and all(c in "0123456789abcdef" for c in second):
                return "", parts[0], second
            return parts[0], parts[1], ""
        # len >= 3: NZ|IG|hash
        return parts[0], parts[1], parts[2] if len(parts) > 2 else ""

    # === Batch Creation ===

    @staticmethod
    def create_batch_run(
        db: Session,
        payload: BatchRunCreateRequest,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        # 1. Resolve assets
        assets = BatchCollectorService.resolve_assets(
            db,
            target_scope=payload.target_scope,
            asset_ids=payload.asset_ids,
            filters=payload.filters.model_dump(exclude_none=True) if payload.filters else None,
        )
        if not assets:
            raise ValueError("未匹配到任何资产")

        # 2. Generate batch_code and insert batch_run
        batch_code = BatchCollectorService._generate_batch_code()
        batch_suffix = batch_code.split("-")[-1]  # random6 part

        batch_run = CollectorBatchRun(
            batch_code=batch_code,
            run_type=payload.run_type,
            target_scope=payload.target_scope,
            status="dispatching",
            total_asset_count=len(assets),
            request_payload=payload.model_dump(mode="json"),
            created_by=requested_by,
            started_at=BatchCollectorService._now(),
        )
        db.add(batch_run)
        db.flush()

        # 3. Build items via CheckItemBuilderRegistry (NOT via check_code branches)
        options = {
            "timeout_seconds": payload.timeout_seconds,
            "include_related_server": payload.include_related_server,
        }
        all_items: list[dict[str, Any]] = []
        for check_code in payload.check_codes:
            built = CheckItemBuilderRegistry.build_items(
                db,
                check_code=check_code,
                assets=assets,
                options=options,
            )
            all_items.extend(built)

        # Deduplicate by item_key — multiple db_instances sharing the same
        # server can produce identical SSH/candidate items.
        seen_keys: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for it in all_items:
            key = it.get("item_key", "")
            if key and key not in seen_keys:
                seen_keys.add(key)
                deduped.append(it)
        all_items = deduped

        # Ensure every item has asset_id for AWX playbook compatibility.
        # Builders use db_instance_id / server_id; the playbook expects asset_id.
        for it in all_items:
            if not it.get("asset_id"):
                it["asset_id"] = it.get("db_instance_id") or it.get("server_id")

        if not all_items:
            batch_run.status = "failed"
            batch_run.error_message = "未生成任何可执行校验项"
            batch_run.finished_at = BatchCollectorService._now()
            db.commit()
            raise ValueError("未生成任何可执行校验项")

        batch_run.total_item_count = len(all_items)
        batch_run.pending_item_count = len(all_items)

        credential_skipped_items = [it for it in all_items if str(it.get("status") or "").lower() == "skipped"]
        dispatchable_items = [it for it in all_items if str(it.get("status") or "").lower() != "skipped"]

        batch_run.skipped_item_count = len(credential_skipped_items)
        batch_run.pending_item_count = len(dispatchable_items)

        if not dispatchable_items:
           batch_run.status = "failed"
           batch_run.error_message = (
               f"未生成任何可执行校验项，已跳过 {len(credential_skipped_items)} 项"
               if credential_skipped_items
               else "未生成任何可执行校验项"
           )
           batch_run.finished_at = BatchCollectorService._now()
           db.commit()
           raise ValueError(batch_run.error_message)

        # 4. Group items by dispatch target
        grouped = DispatchPlannerService.group_items_by_dispatch_target(
           db, dispatchable_items, payload.target_scope
        )

        dispatch_skipped_items = grouped.pop("__skipped__", [])
        if dispatch_skipped_items:
           batch_run.skipped_item_count += len(dispatch_skipped_items)
           batch_run.pending_item_count = max(
               0,
               batch_run.pending_item_count - len(dispatch_skipped_items),
           )

        # 5. Create dispatch_run + collector_run for each group × chunk
        callback_url = BatchCollectorService._resolve_callback_url()
        dispatches: list[dict[str, Any]] = []
        run_seq = 0  # monotonically increasing across all groups/chunks

        for group_key, group_items in sorted(grouped.items()):
            # Parse group_key → network_zone, awx_instance_group, credential_hash
            network_zone, awx_instance_group, cred_hash = BatchCollectorService._parse_group_key(group_key)

            max_items = payload.max_items_per_dispatch
            # Chunk: NEVER truncate — split into multiple dispatches
            chunks = [
                group_items[i : i + max_items]
                for i in range(0, len(group_items), max_items)
            ]

            for chunk_seq, chunk_items in enumerate(chunks):
                # Collect unique credential profile IDs for this chunk
                cred_profile_ids = sorted(set(
                    it["credential_profile_id"]
                    for it in chunk_items
                    if it.get("credential_profile_id")
                )) if chunk_items else []

                dispatch_code = BatchCollectorService._generate_dispatch_code(batch_suffix, run_seq)
                run_id = BatchCollectorService._generate_run_id(run_seq)
                now = BatchCollectorService._now()

                # Create collector_run
                collector_run = CollectorRun(
                    run_id=run_id,
                    target_scope=payload.target_scope,
                    status="pending",
                    requested_by=requested_by,
                    callback_url=callback_url,
                    batch_run_id=int(batch_run.id),
                    network_zone=network_zone or None,
                    awx_instance_group=awx_instance_group or None,
                    item_count=len(chunk_items),
                    request_payload=payload.model_dump(mode="json"),
                    extra_vars={
                        "schema_version": 1,
                        "run_id": run_id,
                        "run_type": payload.run_type,
                        "callback_url": callback_url,
                        "items": chunk_items,
                    },
                    job_type="ASSET_VERIFY_PORT",
                )
                db.add(collector_run)
                db.flush()

                # Create dispatch_run
                dispatch_run = CollectorDispatchRun(
                    dispatch_code=dispatch_code,
                    batch_run_id=int(batch_run.id),
                    collector_run_id=int(collector_run.id),
                    network_zone=network_zone or None,
                    awx_instance_group=awx_instance_group or None,
                    awx_job_template="JT_DBOPS_COLLECTOR_GENERIC",
                    credential_group_hash=cred_hash or None,
                    credential_profile_ids=cred_profile_ids or [],
                    status="pending",
                    item_count=len(chunk_items),
                    request_payload={"items": chunk_items},
                )
                db.add(dispatch_run)
                db.flush()

                # Update collector_run with dispatch_run_id
                collector_run.dispatch_run_id = int(dispatch_run.id)

                # Create collector_run_items
                for item_dict in chunk_items:
                    run_item = CollectorRunItem(
                        collector_run_id=int(collector_run.id),
                        run_id=run_id,
                        item_key=str(item_dict["item_key"]),
                        check_code=str(item_dict["check_code"]),
                        target_scope=str(item_dict["target_scope"]),
                        db_instance_id=item_dict.get("db_instance_id"),
                        server_id=item_dict.get("server_id"),
                        target_host=str(item_dict["target_host"]),
                        target_port=int(item_dict["target_port"]),
                        protocol=str(item_dict.get("protocol") or "tcp"),
                        endpoint_type=item_dict.get("endpoint_type"),
                        port_source=item_dict.get("port_source"),
                        is_required=bool(item_dict.get("is_required")),
                        timeout_seconds=int(item_dict.get("timeout_seconds") or 5),
                        status="pending",
                    )
                    db.add(run_item)

                dispatches.append(
                    {
                        "dispatch_run_id": int(dispatch_run.id),
                        "dispatch_code": dispatch_code,
                        "collector_run_id": int(collector_run.id),
                        "network_zone": network_zone or None,
                        "awx_instance_group": awx_instance_group or None,
                        "item_count": len(chunk_items),
                        "status": "pending",
                        "awx_job_id": None,
                    }
                )
                run_seq += 1

        batch_run.dispatch_count = len(dispatches)
        db.commit()

        # 6. Launch dispatches (each creates an AWX Job)
        dispatches = BatchCollectorService.launch_dispatches(db, int(batch_run.id))

        # 7. Refresh batch status after launch
        BatchCollectorService.refresh_batch_status(db, int(batch_run.id))

        # Persist skipped items so the UI can show explicit skip reasons.
        all_skipped_items = credential_skipped_items + dispatch_skipped_items
        if all_skipped_items and dispatches:
            first_dispatch = next((d for d in dispatches if d.get("collector_run_id")), None)
            if first_dispatch:
                collector_run = (
                    db.query(CollectorRun)
                    .filter(CollectorRun.id == int(first_dispatch["collector_run_id"]))
                    .first()
                )
                if collector_run:
                    skipped_run_items = []
                    for item_dict in all_skipped_items:
                        skipped_run_items.append(
                            CollectorRunItem(
                                collector_run_id=int(collector_run.id),
                                run_id=collector_run.run_id,
                                item_key=str(item_dict["item_key"]),
                                check_code=str(item_dict["check_code"]),
                                target_scope=str(item_dict["target_scope"]),
                                db_instance_id=item_dict.get("db_instance_id"),
                                server_id=item_dict.get("server_id"),
                                target_host=str(item_dict["target_host"]),
                                target_port=int(item_dict["target_port"]),
                                protocol=str(item_dict.get("protocol") or "tcp"),
                                endpoint_type=item_dict.get("endpoint_type"),
                                port_source=item_dict.get("port_source"),
                                is_required=bool(item_dict.get("is_required")),
                                timeout_seconds=int(item_dict.get("timeout_seconds") or 5),
                                status="skipped",
                                result_message=str(item_dict.get("result_message") or "SKIPPED"),
                                raw_result=item_dict.get("raw_result") or {},
                            )
                        )
                    for row in skipped_run_items:
                        db.add(row)
                    db.commit()

        db.refresh(batch_run)

        return {
            "batch_run_id": int(batch_run.id),
            "batch_code": batch_run.batch_code,
            "status": batch_run.status,
            "run_type": batch_run.run_type,
            "target_scope": batch_run.target_scope,
            "total_asset_count": batch_run.total_asset_count,
            "total_item_count": batch_run.total_item_count,
            "dispatch_count": batch_run.dispatch_count,
            "dispatches": dispatches,
        }

    @staticmethod
    def _resolve_callback_url() -> str:
        settings = get_settings()
        configured_url = settings.COLLECTOR_CALLBACK_URL.strip()
        if configured_url:
            return configured_url
        raise ValueError("COLLECTOR_CALLBACK_URL 未配置")

    # === Dispatch Launch ===

    @staticmethod
    def launch_dispatches(
        db: Session,
        batch_run_id: int,
    ) -> list[dict[str, Any]]:
        """Launch AWX jobs for all pending dispatches in a batch.

        Individual dispatch failure does NOT block others.
        """
        dispatches = (
            db.query(CollectorDispatchRun)
            .filter(
                CollectorDispatchRun.batch_run_id == batch_run_id,
                CollectorDispatchRun.status == "pending",
            )
            .all()
        )

        result: list[dict[str, Any]] = []
        for dispatch in dispatches:
            dispatch.status = "launching"
            db.flush()

            collector_run = (
                db.query(CollectorRun)
                .filter(CollectorRun.id == dispatch.collector_run_id)
                .first()
            )

            extra_vars = collector_run.extra_vars if collector_run else {"items": []}

            # Phase 3.3A: Extract unique AWX credential IDs from fact collection items
            credential_ids = BatchCollectorService._extract_credential_ids(extra_vars)

            try:
                launch_result = AwxService.launch_job(
                    extra_vars=extra_vars,
                    credentials=credential_ids if credential_ids else None,
                )
                dispatch.status = "launched"
                dispatch.awx_job_id = launch_result.get("awx_job_id")
                dispatch.awx_job_template_id = launch_result.get("awx_job_template_id")
                dispatch.launched_at = BatchCollectorService._now()

                if collector_run:
                    collector_run.status = "launched"
                    collector_run.awx_job_id = launch_result.get("awx_job_id")
                    collector_run.awx_job_url = launch_result.get("awx_job_url")
                    collector_run.awx_job_template_id = launch_result.get("awx_job_template_id")
                    collector_run.awx_job_template_name = launch_result.get("awx_job_template_name")
                    collector_run.started_at = BatchCollectorService._now()
            except (AwxServiceError, RuntimeError) as exc:
                dispatch.status = "failed"
                dispatch.error_message = str(exc)
                if collector_run:
                    collector_run.status = "failed"
                    collector_run.error_message = str(exc)
                    collector_run.finished_at = BatchCollectorService._now()

            db.flush()
            result.append(
                {
                    "dispatch_run_id": int(dispatch.id),
                    "dispatch_code": dispatch.dispatch_code,
                    "collector_run_id": int(dispatch.collector_run_id) if dispatch.collector_run_id else None,
                    "network_zone": dispatch.network_zone,
                    "awx_instance_group": dispatch.awx_instance_group,
                    "item_count": dispatch.item_count,
                    "status": dispatch.status,
                    "awx_job_id": dispatch.awx_job_id,
                    "awx_job_template_id": dispatch.awx_job_template_id,
                }
            )

        db.commit()
        return result

    @staticmethod
    def _extract_credential_ids(extra_vars: dict[str, Any]) -> list[int]:
        """Extract unique AWX credential IDs to pass at launch time.

        Fact collection items carry awx_credential_id; port-check items do not.
        Pre-bound credential IDs (e.g. callback token) from
        AWX_PREBOUND_CREDENTIAL_IDS are always merged so AWX doesn't reject
        the launch for removing them.

        Returns a sorted, deduplicated list, or empty list if there are no
        fact-collection credentials (letting AWX use template defaults).
        """
        items = extra_vars.get("items") or []

        # Collect fact collection credential IDs
        fact_cred_ids: set[int] = set()
        for item in items:
            awx_id = item.get("awx_credential_id")
            if awx_id is not None:
                fact_cred_ids.add(int(awx_id))

        # Merge pre-bound credential IDs from config.
        prebound_str = get_settings().AWX_PREBOUND_CREDENTIAL_IDS or ""
        for part in prebound_str.split(","):
            part = part.strip()
            if part:
                try:
                    fact_cred_ids.add(int(part))
                except ValueError:
                    pass

        # No fact credentials and no prebound credentials -> let AWX use template defaults.
        if not fact_cred_ids:
            return []

        return sorted(fact_cred_ids)

    # === Status Refresh ===

    @staticmethod
    def refresh_batch_status(db: Session, batch_run_id: int) -> None:
        """Aggregate all dispatch stats into the batch_run.

        Self-acquires FOR UPDATE lock to prevent concurrent stat overwrites.
        """
        batch_run = db.query(CollectorBatchRun).filter(
            CollectorBatchRun.id == batch_run_id
        ).with_for_update().first()
        if not batch_run:
            return

        dispatches = (
            db.query(CollectorDispatchRun)
            .filter(CollectorDispatchRun.batch_run_id == batch_run_id)
            .all()
        )

        total_success = 0
        total_failed = 0
        total_pending = 0
        total_running = 0
        all_failed = True
        all_success = True
        has_running = False

        for d in dispatches:
            total_success += d.success_item_count or 0
            total_failed += d.failed_item_count or 0
            if d.status not in ("success", "partial_success", "failed", "cancelled"):
                has_running = True
            if d.status != "success":
                all_success = False
            if d.status != "failed":
                all_failed = False

        # Count items directly
        collector_run_ids = [d.collector_run_id for d in dispatches if d.collector_run_id]
        if collector_run_ids:
            items = (
                db.query(CollectorRunItem)
                .filter(CollectorRunItem.collector_run_id.in_(collector_run_ids))
                .all()
            )
            total_pending = sum(1 for i in items if i.status == "pending")
            total_running = sum(1 for i in items if i.status == "running")

        batch_run.success_item_count = total_success
        batch_run.failed_item_count = total_failed
        batch_run.pending_item_count = total_pending
        batch_run.running_item_count = total_running

        if all_success and not has_running:
            batch_run.status = "success"
        elif all_failed and not has_running:
            batch_run.status = "failed"
        elif has_running or total_pending > 0:
            batch_run.status = "running"
        else:
            batch_run.status = "partial_success"

        db.flush()

    @staticmethod
    def handle_callback_post_process(db: Session, collector_run: CollectorRun) -> None:
        """Called inside CollectorService.handle_callback() transaction.

        After items are processed, refresh dispatch and batch status.
        The caller must have FOR UPDATE locks on the relevant rows.
        """
        if not collector_run.dispatch_run_id:
            return

        dispatch_run = (
            db.query(CollectorDispatchRun)
            .filter(CollectorDispatchRun.id == collector_run.dispatch_run_id)
            .with_for_update()
            .first()
        )
        if dispatch_run:
            dispatch_items = (
                db.query(CollectorRunItem)
                .filter(CollectorRunItem.collector_run_id == collector_run.id)
                .all()
            )
            dispatch_run.success_item_count = sum(1 for i in dispatch_items if i.status == "success")
            dispatch_run.failed_item_count = sum(
                1 for i in dispatch_items if i.status in ("failed", "timeout")
            )
            all_success = all(i.status == "success" for i in dispatch_items)
            any_success = any(i.status == "success" for i in dispatch_items)
            if all_success:
                dispatch_run.status = "success"
            elif any_success:
                dispatch_run.status = "partial_success"
            else:
                dispatch_run.status = "failed"
            dispatch_run.finished_at = BatchCollectorService._now()

        if collector_run.batch_run_id:
            BatchCollectorService.refresh_batch_status(db, int(collector_run.batch_run_id))

    # === Query ===

    @staticmethod
    def get_batch_run(db: Session, batch_run_id: int) -> dict[str, Any]:
        row = db.query(CollectorBatchRun).filter(CollectorBatchRun.id == batch_run_id).first()
        if not row:
            raise LookupError("batch_run_id 不存在")
        dispatches = (
            db.query(CollectorDispatchRun)
            .filter(CollectorDispatchRun.batch_run_id == batch_run_id)
            .order_by(CollectorDispatchRun.id)
            .all()
        )
        return {
            "id": int(row.id),
            "batch_code": row.batch_code,
            "run_type": row.run_type,
            "target_scope": row.target_scope,
            "status": row.status,
            "total_asset_count": row.total_asset_count,
            "total_item_count": row.total_item_count,
            "success_item_count": row.success_item_count,
            "failed_item_count": row.failed_item_count,
            "pending_item_count": row.pending_item_count,
            "running_item_count": row.running_item_count,
            "skipped_item_count": row.skipped_item_count,
            "dispatch_count": row.dispatch_count,
            "request_payload": row.request_payload or {},
            "error_message": row.error_message,
            "created_by": row.created_by,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "dispatches": [
                {
                    "id": int(d.id),
                    "dispatch_run_id": int(d.id),
                    "dispatch_code": d.dispatch_code,
                    "batch_run_id": int(d.batch_run_id),
                    "collector_run_id": int(d.collector_run_id) if d.collector_run_id else None,
                    "network_zone": d.network_zone,
                    "awx_instance_group": d.awx_instance_group,
                    "awx_job_template": d.awx_job_template,
                    "awx_job_template_id": d.awx_job_template_id,
                    "awx_job_id": d.awx_job_id,
                    "status": d.status,
                    "item_count": d.item_count,
                    "success_item_count": d.success_item_count,
                    "failed_item_count": d.failed_item_count,
                    "request_payload": d.request_payload or {},
                    "error_message": d.error_message,
                    "launched_at": d.launched_at,
                    "finished_at": d.finished_at,
                    "created_at": d.created_at,
                    "updated_at": d.updated_at,
                }
                for d in dispatches
            ],
        }

    @staticmethod
    def list_batch_runs(
        db: Session,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = db.query(CollectorBatchRun)
        if filters:
            if filters.get("status"):
                query = query.filter(CollectorBatchRun.status == filters["status"])
            if filters.get("run_type"):
                query = query.filter(CollectorBatchRun.run_type == filters["run_type"])
        rows = query.order_by(CollectorBatchRun.created_at.desc()).limit(limit).all()
        return [
            {
                "id": int(row.id),
                "batch_code": row.batch_code,
                "run_type": row.run_type,
                "target_scope": row.target_scope,
                "status": row.status,
                "total_asset_count": row.total_asset_count,
                "total_item_count": row.total_item_count,
                "success_item_count": row.success_item_count,
                "failed_item_count": row.failed_item_count,
                "dispatch_count": row.dispatch_count,
                "error_message": row.error_message,
                "created_by": row.created_by,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    @staticmethod
    def list_batch_dispatches(db: Session, batch_run_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(CollectorDispatchRun)
            .filter(CollectorDispatchRun.batch_run_id == batch_run_id)
            .order_by(CollectorDispatchRun.id)
            .all()
        )
        return [
            {
                "id": int(r.id),
                "dispatch_code": r.dispatch_code,
                "batch_run_id": int(r.batch_run_id),
                "collector_run_id": int(r.collector_run_id) if r.collector_run_id else None,
                "network_zone": r.network_zone,
                "awx_instance_group": r.awx_instance_group,
                "awx_job_template": r.awx_job_template,
                "awx_job_template_id": r.awx_job_template_id,
                "awx_job_id": r.awx_job_id,
                "status": r.status,
                "item_count": r.item_count,
                "success_item_count": r.success_item_count,
                "failed_item_count": r.failed_item_count,
                "request_payload": r.request_payload or {},
                "error_message": r.error_message,
                "launched_at": r.launched_at,
                "finished_at": r.finished_at,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]

    @staticmethod
    def list_batch_items(
        db: Session,
        batch_run_id: int,
        filters: dict[str, Any] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Get all dispatch collector_run_ids for this batch
        dispatch_run_ids = (
            db.query(CollectorDispatchRun.collector_run_id)
            .filter(
                CollectorDispatchRun.batch_run_id == batch_run_id,
                CollectorDispatchRun.collector_run_id.isnot(None),
            )
            .all()
        )
        collector_run_ids = [r[0] for r in dispatch_run_ids]
        if not collector_run_ids:
            return []

        query = db.query(CollectorRunItem).filter(
            CollectorRunItem.collector_run_id.in_(collector_run_ids)
        )

        if filters:
            if filters.get("status"):
                query = query.filter(CollectorRunItem.status == filters["status"])
            if filters.get("check_code"):
                query = query.filter(CollectorRunItem.check_code == filters["check_code"])
            if filters.get("target_scope"):
                query = query.filter(CollectorRunItem.target_scope == filters["target_scope"])
            if filters.get("asset_id"):
                asset_id = int(filters["asset_id"])
                query = query.filter(
                    (CollectorRunItem.db_instance_id == asset_id)
                    | (CollectorRunItem.server_id == asset_id)
                )

        rows = query.order_by(CollectorRunItem.created_at.asc()).offset(offset).limit(limit).all()

        # Build a map from collector_run_id → (network_zone, awx_instance_group, dispatch_run_id)
        dispatch_map: dict[int, tuple[str | None, str | None, int | None]] = {}
        all_dispatches = (
            db.query(CollectorDispatchRun)
            .filter(CollectorDispatchRun.batch_run_id == batch_run_id)
            .all()
        )
        for d in all_dispatches:
            if d.collector_run_id:
                dispatch_map[int(d.collector_run_id)] = (d.network_zone, d.awx_instance_group, int(d.id))

        return [
            {
                "id": int(item.id),
                "collector_run_id": int(item.collector_run_id),
                "run_id": item.run_id,
                "item_key": item.item_key,
                "check_code": item.check_code,
                "target_scope": item.target_scope,
                "server_id": item.server_id,
                "db_instance_id": item.db_instance_id,
                "target_host": item.target_host,
                "target_port": item.target_port,
                "protocol": item.protocol,
                "endpoint_type": item.endpoint_type,
                "port_source": item.port_source,
                "is_required": bool(item.is_required),
                "timeout_seconds": item.timeout_seconds,
                "status": item.status,
                "result_status": item.result_status,
                "result_message": item.result_message,
                "candidate_state": (item.raw_result or {}).get("candidate_state"),
                "raw_result": item.raw_result or {},
                "batch_run_id": batch_run_id,
                "dispatch_run_id": dispatch_map.get(int(item.collector_run_id), (None, None, None))[2],
                "network_zone": dispatch_map.get(int(item.collector_run_id), (None, None, None))[0],
                "awx_instance_group": dispatch_map.get(int(item.collector_run_id), (None, None, None))[1],
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in rows
        ]

    # === Retry ===

    @staticmethod
    def retry_failed_items(
        db: Session,
        batch_run_id: int,
        payload: RetryFailedRequest,
    ) -> dict[str, Any]:
        batch_run = db.query(CollectorBatchRun).filter(CollectorBatchRun.id == batch_run_id).first()
        if not batch_run:
            raise LookupError("batch_run_id 不存在")

        scope = payload.scope
        if scope == "failed":
            # Find failed/missing/callback_failed items
            items = BatchCollectorService._find_failed_items(db, batch_run_id)
        elif scope == "dispatch_failed":
            # Find all items from failed dispatches
            items = BatchCollectorService._find_dispatch_failed_items(db, batch_run_id)
        else:
            raise ValueError(f"不支持的 scope: {scope}")

        if not items:
            raise ValueError("没有需要重跑的失败项")

        # Group items by dispatch target
        target_scope = batch_run.target_scope
        grouped = DispatchPlannerService.group_items_by_dispatch_target(db, items, target_scope)

        # Create new dispatches with retry_origin recorded
        retry_dispatches: list[dict[str, Any]] = []
        original_item_keys = [item["item_key"] for item in items]
        batch_suffix = batch_run.batch_code.split("-")[-1] if "-" in batch_run.batch_code else "RETRY"
        retry_at = BatchCollectorService._now().isoformat()

        run_seq = 0
        # Use same max_items_per_dispatch as original batch, or default 100
        max_items = (batch_run.request_payload or {}).get("max_items_per_dispatch", 100)

        for group_key, group_items in sorted(grouped.items()):
            if group_key == "__skipped__":
                continue

            network_zone, awx_instance_group, _cred_hash = BatchCollectorService._parse_group_key(group_key)

            callback_url = BatchCollectorService._resolve_callback_url()

            # Chunk: NEVER truncate — split into multiple dispatches
            chunks = [
                group_items[i : i + max_items]
                for i in range(0, len(group_items), max_items)
            ]

            for chunk_seq, chunk_items in enumerate(chunks):
                # Compute credential info for this chunk
                retry_cred_hash = DispatchPlannerService._compute_credential_hash(chunk_items[0]) if chunk_items else ""
                retry_cred_profile_ids = sorted(set(
                    it.get("credential_profile_id")
                    for it in chunk_items
                    if it.get("credential_profile_id")
                )) if chunk_items else []

                dispatch_code = BatchCollectorService._generate_dispatch_code(batch_suffix, run_seq + 100)
                run_id = BatchCollectorService._generate_run_id(run_seq + 100)
                now = BatchCollectorService._now()

                # Build extra_vars with items
                extra_items = [
                    {
                        "item_key": it["item_key"],
                        "check_code": it["check_code"],
                        "target_scope": it["target_scope"],
                        "asset_id": it.get("db_instance_id") or it.get("server_id"),
                        "target_host": it["target_host"],
                        "target_port": it["target_port"],
                        "timeout_seconds": it.get("timeout_seconds", 5),
                        "endpoint_type": it.get("endpoint_type"),
                        "protocol": it.get("protocol", "tcp"),
                        "port_source": it.get("port_source", "unknown"),
                        "is_required": it.get("is_required", False),
                    }
                    for it in chunk_items
                ]

                collector_run = CollectorRun(
                    run_id=run_id,
                    target_scope=target_scope,
                    status="pending",
                    requested_by=batch_run.created_by,
                    callback_url=callback_url,
                    batch_run_id=int(batch_run.id),
                    network_zone=network_zone or None,
                    awx_instance_group=awx_instance_group or None,
                    item_count=len(chunk_items),
                    request_payload={"retry": True, "scope": scope},
                    extra_vars={
                        "schema_version": 1,
                        "run_id": run_id,
                        "run_type": batch_run.run_type,
                        "callback_url": callback_url,
                        "items": extra_items,
                    },
                    job_type="ASSET_VERIFY_PORT",
                )
                db.add(collector_run)
                db.flush()

                dispatch_run = CollectorDispatchRun(
                    dispatch_code=dispatch_code,
                    batch_run_id=int(batch_run.id),
                    collector_run_id=int(collector_run.id),
                    network_zone=network_zone or None,
                    awx_instance_group=awx_instance_group or None,
                    awx_job_template="JT_DBOPS_COLLECTOR_GENERIC",
                    credential_group_hash=retry_cred_hash or None,
                    credential_profile_ids=retry_cred_profile_ids or [],
                    status="pending",
                    item_count=len(chunk_items),
                    request_payload={
                        "items": extra_items,
                        "retry_origin": {
                            "original_batch_run_id": batch_run_id,
                            "original_item_keys": original_item_keys,
                            "retry_scope": scope,
                            "retry_at": retry_at,
                        },
                    },
                )
                db.add(dispatch_run)
                db.flush()

                collector_run.dispatch_run_id = int(dispatch_run.id)

                for item_dict in chunk_items:
                    run_item = CollectorRunItem(
                        collector_run_id=int(collector_run.id),
                        run_id=run_id,
                        item_key=str(item_dict["item_key"]),
                        check_code=str(item_dict["check_code"]),
                        target_scope=str(item_dict["target_scope"]),
                        db_instance_id=item_dict.get("db_instance_id"),
                        server_id=item_dict.get("server_id"),
                        target_host=str(item_dict["target_host"]),
                        target_port=int(item_dict["target_port"]),
                        protocol=str(item_dict.get("protocol") or "tcp"),
                        endpoint_type=item_dict.get("endpoint_type"),
                        port_source=item_dict.get("port_source"),
                        is_required=bool(item_dict.get("is_required")),
                        timeout_seconds=int(item_dict.get("timeout_seconds") or 5),
                        status="pending",
                    )
                    db.add(run_item)

                retry_dispatches.append(
                    {
                        "dispatch_run_id": int(dispatch_run.id),
                        "dispatch_code": dispatch_code,
                        "collector_run_id": int(collector_run.id),
                        "network_zone": network_zone or None,
                        "awx_instance_group": awx_instance_group or None,
                        "item_count": len(chunk_items),
                        "status": "pending",
                    }
                )
                run_seq += 1

        if not retry_dispatches:
            raise ValueError("所有失败项无法重新分组")

        batch_run.dispatch_count = (batch_run.dispatch_count or 0) + len(retry_dispatches)
        db.commit()

        # Launch the retry dispatches
        retry_dispatches = BatchCollectorService.launch_dispatches(db, int(batch_run.id))
        BatchCollectorService.refresh_batch_status(db, int(batch_run.id))

        return {
            "detail": "retry_launched",
            "batch_run_id": batch_run_id,
            "retry_dispatches": retry_dispatches,
        }

    @staticmethod
    def _find_failed_items(db: Session, batch_run_id: int) -> list[dict[str, Any]]:
        """Find items with status in (failed, timeout) across all dispatches."""
        dispatch_run_ids = (
            db.query(CollectorDispatchRun.collector_run_id)
            .filter(
                CollectorDispatchRun.batch_run_id == batch_run_id,
                CollectorDispatchRun.collector_run_id.isnot(None),
            )
            .all()
        )
        collector_run_ids = [r[0] for r in dispatch_run_ids]
        if not collector_run_ids:
            return []

        rows = (
            db.query(CollectorRunItem)
            .filter(
                CollectorRunItem.collector_run_id.in_(collector_run_ids),
                CollectorRunItem.status.in_(["failed", "timeout"]),
            )
            .all()
        )
        return [
            {
                "item_key": item.item_key,
                "check_code": item.check_code,
                "target_scope": item.target_scope,
                "db_instance_id": item.db_instance_id,
                "server_id": item.server_id,
                "target_host": item.target_host,
                "target_port": item.target_port,
                "protocol": item.protocol,
                "endpoint_type": item.endpoint_type,
                "port_source": item.port_source,
                "is_required": item.is_required,
                "timeout_seconds": item.timeout_seconds,
            }
            for item in rows
        ]

    @staticmethod
    def _find_dispatch_failed_items(db: Session, batch_run_id: int) -> list[dict[str, Any]]:
        """Find all items from dispatches with status=failed."""
        failed_dispatch_ids = (
            db.query(CollectorDispatchRun.collector_run_id)
            .filter(
                CollectorDispatchRun.batch_run_id == batch_run_id,
                CollectorDispatchRun.status == "failed",
                CollectorDispatchRun.collector_run_id.isnot(None),
            )
            .all()
        )
        collector_run_ids = [r[0] for r in failed_dispatch_ids]
        if not collector_run_ids:
            return []

        rows = (
            db.query(CollectorRunItem)
            .filter(CollectorRunItem.collector_run_id.in_(collector_run_ids))
            .all()
        )
        return [
            {
                "item_key": item.item_key,
                "check_code": item.check_code,
                "target_scope": item.target_scope,
                "db_instance_id": item.db_instance_id,
                "server_id": item.server_id,
                "target_host": item.target_host,
                "target_port": item.target_port,
                "protocol": item.protocol,
                "endpoint_type": item.endpoint_type,
                "port_source": item.port_source,
                "is_required": item.is_required,
                "timeout_seconds": item.timeout_seconds,
            }
            for item in rows
        ]
