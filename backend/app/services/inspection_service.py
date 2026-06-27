from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    CollectorBatchRun,
    CollectorRun,
    CollectorRunItem,
    CollectorRunResult,
    DbInstance,
    InspectionItem,
    InspectionResult,
    InspectionTask,
    InspectionTaskItem,
    InspectionTaskTarget,
    InspectionReport,
    InspectionInstanceReport,
    Server,
    DbType,
)
from app.schemas.collector import BatchRunCreateRequest, BatchRunFiltersRequest, CollectorCallbackItem, CollectorInspectionCallbackItem
from app.schemas.inspection import InspectionItemCreateRequest, InspectionItemUpdateRequest, InspectionTaskCreateRequest
from app.services.awx_service import AwxService, AwxServiceError
from app.services.batch_collector_service import BatchCollectorService
from app.services.check_item_builder_registry import CheckItemBuilderRegistry
from app.services.inspection_evaluator_service import InspectionEvaluatorService
from app.services.sql_safety_service import SqlSafetyService
from app.services import asset_event_history_service


class InspectionService:
    @staticmethod
    def _now() -> datetime:
        # M14 v3: use local time (Asia/Shanghai) to match PostgreSQL's naive
        # `now()` / triggers. Single source of truth is
        # app.utils.datetime.now_local.
        from app.utils.datetime import now_local
        return now_local()

    @staticmethod
    def _generate_task_code() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3).upper()
        return f"INSP-{timestamp}-{suffix}"

    # ------------------------------------------------------------------
    # Plan §5.6 / §2.2/§2.6: canonical JSON → SHA-256 helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _stable_hash(payload: Any) -> str:
        return hashlib.sha256(InspectionService._canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _compute_sql_hash(sql_text: str) -> str:
        return InspectionService._stable_hash({"sql": (sql_text or "").strip()})

    @staticmethod
    def _compute_rule_hash(check_code: str, executor_type: str, rule_config: dict[str, Any], applicability: dict[str, Any] | None) -> str:
        return InspectionService._stable_hash({
            "check_code": check_code or "",
            "executor_type": executor_type or "",
            "rule_config_snapshot": rule_config or {},
            "applicability_snapshot": applicability or {},
        })

    @staticmethod
    def _compute_source_data_hash(
        task_items: list[InspectionTaskItem],
        task_targets: list[InspectionTaskTarget],
        results: list[InspectionResult],
    ) -> str:
        """Plan §5.6: source_data_hash over (task_items, task_targets, results)."""
        items_payload = sorted(
            (
                {
                    "id": int(ti.id),
                    "item_code": ti.item_code,
                    "rule_hash": ti.rule_hash or "",
                    "check_order": int(ti.check_order or 0),
                }
                for ti in task_items
            ),
            key=lambda x: x["id"],
        )
        targets_payload = sorted(
            (
                {
                    "id": int(tt.id),
                    "target_type": tt.target_type,
                    "target_id": int(tt.target_id),
                    "dispatch_status": tt.dispatch_status,
                    "execution_status": tt.execution_status,
                    "attempt_no": int(tt.attempt_no or 0),
                }
                for tt in task_targets
            ),
            key=lambda x: x["id"],
        )
        results_payload = sorted(
            (
                {
                    "task_target_id": int(r.task_target_id),
                    "task_item_id": int(r.task_item_id),
                    "attempt_no": int(r.attempt_no or 0),
                    "execution_status": r.execution_status,
                    "evaluation_status": r.evaluation_status,
                    "message": r.message or "",
                    "findings": ((r.evidence or {}).get("findings") or []),
                    "error_code": (r.evidence or {}).get("error_code"),
                    "sql_hash": (r.evidence or {}).get("sql_hash"),
                    "truncated": bool((r.evidence or {}).get("truncated", False)),
                }
                for r in results
            ),
            key=lambda x: (x["task_target_id"], x["task_item_id"]),
        )
        return InspectionService._stable_hash({
            "task_items": items_payload,
            "task_targets": targets_payload,
            "results": results_payload,
        })

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
            "executor_type": item.executor_type,
            "target_scope": item.target_scope,
            "db_type_code": item.db_type_code,
            "category": item.category,
            "inspection_type": item.inspection_type,
            "item_kind": item.item_kind,
            "evaluator_type": item.evaluator_type,
            "severity": item.severity,
            "weight": int(item.weight or 10),
            "rule_version": item.rule_version,
            "rule_config": item.rule_config or {},
            "applicability": item.applicability or {},
            "enabled": bool(item.enabled),
            "description": item.description,
            "sql_hash": item.sql_hash,
            "rule_hash": item.rule_hash,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _task_to_dict(task: InspectionTask) -> dict[str, Any]:
        report = task.report
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
            "report_status": report.report_status if report else None,
            "health_level": report.health_level if report else None,
            "report_id": int(report.id) if report else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    @staticmethod
    def _result_to_dict(result: InspectionResult) -> dict[str, Any]:
        item = result.task_item
        target = result.task_target
        return {
            "id": int(result.id),
            "task_id": int(result.task_id),
            "task_item_id": int(result.task_item_id),
            "task_target_id": int(result.task_target_id),
            "collector_run_id": result.collector_run_id,
            "collector_run_item_id": result.collector_run_item_id,
            "target_type": result.target_type,
            "target_id": int(result.target_id),
            "result_code": result.result_code,
            "execution_status": result.execution_status,
            "evaluation_status": result.evaluation_status,
            "message": result.message,
            "evidence": result.evidence or {},
            "attempt_no": int(result.attempt_no or 1),
            "received_at": result.received_at,
            "detected_at": result.detected_at,
            "created_at": result.created_at,
            "item_code": item.item_code if item else None,
            "item_name": item.item_name if item else None,
            "item_kind": item.item_kind if item else None,
            "category": item.category if item else None,
            "inspection_type": item.inspection_type if item else None,
            "target_name": target.target_name_snapshot if target else None,
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
    def list_items(db: Session, *, enabled: bool | None = None, db_type_code: str | None = None, source: str | None = None, inspection_type: str | None = None) -> list[dict[str, Any]]:
        InspectionService.ensure_default_items(db)
        query = db.query(InspectionItem)
        if enabled is not None:
            query = query.filter(InspectionItem.enabled == enabled)
        if db_type_code:
            query = query.filter(InspectionItem.db_type_code == db_type_code)
        if inspection_type:
            query = query.filter(InspectionItem.inspection_type == inspection_type)
        if source == "custom":
            query = query.filter(InspectionItem.check_code == "DB_READONLY_SQL_EXEC")
        elif source == "batch_verify":
            query = query.filter(InspectionItem.check_code != "DB_READONLY_SQL_EXEC")
        rows = query.order_by(InspectionItem.id.asc()).all()
        return [InspectionService._item_to_dict(row) for row in rows]

    @staticmethod
    def list_inspection_types(db: Session) -> list[str]:
        rows = (
            db.query(InspectionItem.inspection_type)
            .filter(InspectionItem.inspection_type.isnot(None))
            .filter(InspectionItem.inspection_type != "")
            .distinct()
            .order_by(InspectionItem.inspection_type)
            .all()
        )
        return [r[0] for r in rows]

    @staticmethod
    def create_item(db: Session, *, payload: InspectionItemCreateRequest) -> dict[str, Any]:
        existing = db.query(InspectionItem).filter(InspectionItem.item_code == payload.item_code).first()
        if existing:
            raise ValueError(f"item_code 已存在: {payload.item_code}")

        # Phase 3.5: SQL safety gate for DB_READONLY_SQL_EXEC items.
        InspectionService._validate_sql_item_payload(payload.check_code, payload.rule_config, payload.db_type_code)

        data = payload.model_dump(mode="json")
        row = InspectionItem(**data)
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
        # Re-run SQL safety if check_code/rule_config/db_type_code changes
        # touch a DB_READONLY_SQL_EXEC item.
        effective_check = data.get("check_code") or row.check_code
        if effective_check == "DB_READONLY_SQL_EXEC" and (
            "rule_config" in data or "db_type_code" in data
        ):
            rule = data.get("rule_config") or row.rule_config or {}
            db_type = data.get("db_type_code") or row.db_type_code
            InspectionService._validate_sql_item_payload(
                effective_check, rule, db_type
            )

        for key, value in data.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return InspectionService._item_to_dict(row)

    @staticmethod
    def batch_disable_items(db: Session, *, item_ids: list[int]) -> dict[str, Any]:
        """Phase 3.5: batch soft-disable inspection items."""
        rows = db.query(InspectionItem).filter(InspectionItem.id.in_(item_ids)).all()
        if not rows:
            raise LookupError("未找到匹配的巡检项")
        disabled: list[int] = []
        skipped: list[int] = []
        for row in rows:
            if row.enabled:
                row.enabled = False
                disabled.append(int(row.id))
            else:
                skipped.append(int(row.id))
        db.commit()
        return {"disabled": disabled, "skipped": skipped, "total": len(rows)}

    @staticmethod
    def disable_item(db: Session, *, item_id: int) -> dict[str, Any]:
        """P0: disable an item (soft-delete) instead of hard-deleting.

        Inspection items are referenced by inspection_task.item_codes and
        inspection_result rows; hard-deleting would break history.
        """
        row = db.query(InspectionItem).filter(InspectionItem.id == item_id).first()
        if not row:
            raise LookupError(f"巡检项不存在: {item_id}")
        row.enabled = False
        db.commit()
        db.refresh(row)
        return InspectionService._item_to_dict(row)

    @staticmethod
    def _validate_sql_item_payload(
        check_code: str,
        rule_config: dict[str, Any] | None,
        db_type_code: str | None,
    ) -> None:
        """Validate that a DB_READONLY_SQL_EXEC item has a safe SQL payload.

        Raises ``ValueError`` with a user-readable message when the
        payload is invalid. The caller converts that to HTTP 400.
        """
        if (check_code or "").strip().upper() != "DB_READONLY_SQL_EXEC":
            return
        if not db_type_code:
            raise ValueError("DB_READONLY_SQL_EXEC 巡检项必须指定 db_type_code")
        if not rule_config or not rule_config.get("sql_text"):
            raise ValueError("DB_READONLY_SQL_EXEC 巡检项必须提供 rule_config.sql_text")
        executor_type = (rule_config.get("executor_type") or "db_sql_readonly").strip()
        if executor_type != "db_sql_readonly":
            raise ValueError(
                f"DB_READONLY_SQL_EXEC 巡检项的 executor_type 必须是 db_sql_readonly（当前: {executor_type}）"
            )
        check = SqlSafetyService.validate_rule_config(rule_config, db_type_code)
        if not check["valid"]:
            raise ValueError("SQL 安全校验未通过: " + "; ".join(check["errors"]))

    @staticmethod
    def validate_sql(db: Session, *, db_type_code: str, sql_text: str) -> dict[str, Any]:
        """Phase 3.5: pure SQL safety check, no DB connection."""
        return SqlSafetyService.validate_sql_readonly(sql_text, db_type_code)

    @staticmethod
    def verify_sql(
        db: Session,
        *,
        instance_ids: list[int],
        db_type_code: str,
        sql_text: str,
        timeout_seconds: int,
        max_rows: int,
        requested_by: str | None,
    ) -> dict[str, Any]:
        """Phase 3.5: AWX async SQL verify via one-shot Collector EE job.

        Supports batch verify: one AWX job per instance, all launched
        under a single request.
        """
        check = SqlSafetyService.validate_sql_readonly(sql_text, db_type_code)
        if not check["valid"]:
            raise ValueError("SQL 安全校验未通过: " + "; ".join(check["errors"]))

        from app.services.credential_resolver_service import CredentialResolverService
        from app.config import get_settings

        settings = get_settings()
        base = settings.COLLECTOR_CALLBACK_URL
        if not base:
            raise ValueError("COLLECTOR_CALLBACK_URL 未配置，无法发起 verify-sql")
        callback_url = base.rstrip("/") + "/"

        verify_run_ids: list[int] = []
        collector_run_ids: list[str] = []
        awx_job_id: int | None = None
        overall_status = "launched"

        for instance_id in instance_ids:
            instance = db.query(DbInstance).filter(DbInstance.id == instance_id).first()
            if not instance:
                raise LookupError(f"实例不存在: {instance_id}")
            server = db.query(Server).filter(Server.id == instance.server_id).first()
            if not server:
                raise LookupError(f"实例关联服务器不存在: {instance_id}")
            db_type = db.query(DbType).filter(DbType.id == instance.db_type_id).first()
            actual_db_type = (db_type.type_code or "").lower() if db_type else db_type_code.lower()
            if actual_db_type != (db_type_code or "").lower():
                raise ValueError(
                    f"实例 db_type 与请求 db_type_code 不一致: instance={instance_id} actual={actual_db_type} request={db_type_code}"
                )
            target_host = str(server.ip_address)
            target_port = int(instance.port or 0)
            if target_port < 1 or target_port > 65535:
                raise ValueError(f"实例端口无效: instance={instance_id} port={target_port}")

            credential = CredentialResolverService.resolve_for_item(
                db,
                target_scope="db_instance",
                asset={"id": int(instance.id), "server_id": int(instance.server_id)},
                check_code="DB_READONLY_SQL_EXEC",
            )

            run_id = f"verify-{secrets.token_hex(6)}"
            item_key = f"inspection_verify:{run_id}:{instance_id}"
            item: dict[str, Any] = {
                "item_key": item_key,
                "check_code": "DB_READONLY_SQL_EXEC",
                "executor_type": "db_sql_readonly",
                "business_domain": "inspection_verify",
                "target_scope": "db_instance",
                "asset_id": int(instance.id),
                "target_host": target_host,
                "target_port": target_port,
                "db_type_code": db_type_code.lower(),
                "database_name": "master",
                "service_name": instance.service_name,
                "timeout_seconds": int(timeout_seconds),
                "rule_config": {
                    "sql_text": sql_text,
                    "timeout_seconds": int(timeout_seconds),
                    "max_rows": int(max_rows),
                    "severity": "warning",
                },
                "task_id": None,
                "inspection_item_id": None,
                "item_code": None,
            }
            if credential:
                item.update(
                    {
                        "credential_profile_id": credential["credential_profile_id"],
                        "credential_code": credential["profile_code"],
                        "awx_credential_id": credential["awx_credential_id"],
                        "credential_role": credential["binding_role"],
                        "credential_type": credential["credential_type"],
                    }
                )

            run = CollectorRun(
                run_id=run_id,
                db_instance_id=int(instance.id),
                server_id=int(instance.server_id),
                job_type="SQL_VERIFY",
                target_scope="db_instance",
                target_host=target_host,
                target_port=target_port,
                request_payload={
                    "run_type": "sql_verify",
                    "business_domain": "inspection_verify",
                    "check_codes": ["DB_READONLY_SQL_EXEC"],
                    "items": [item],
                    "sql_text": sql_text,
                    "sql_hash": check["sql_hash"],
                    "db_type_code": db_type_code.lower(),
                    "instance_id": int(instance.id),
                    "requested_by": requested_by,
                },
                extra_vars={"items": [item]},
                status="pending",
                created_at=InspectionService._now(),
            )
            db.add(run)
            db.flush()

            # Create a CollectorRunItem so the callback handler can find it
            from app.models.dbops_assets import CollectorRunItem
            run_item = CollectorRunItem(
                collector_run_id=int(run.id),
                run_id=run_id,
                item_key=item_key,
                check_code="DB_READONLY_SQL_EXEC",
                target_scope="db_instance",
                server_id=int(instance.server_id),
                db_instance_id=int(instance.id),
                target_host=target_host,
                target_port=target_port,
                timeout_seconds=int(timeout_seconds),
                status="pending",
            )
            db.add(run_item)
            db.commit()
            db.refresh(run)

            try:
                creds: list[int] = []
                if credential and credential.get("awx_credential_id"):
                    creds.append(int(credential["awx_credential_id"]))
                # merge pre-bound credential ids (e.g. callback token) so
                # AWX doesn't reject the launch for removing them
                prebound_str = (settings.AWX_PREBOUND_CREDENTIAL_IDS or "").strip()
                if prebound_str:
                    for p in prebound_str.split(","):
                        try:
                            pid = int(p.strip())
                            if pid not in creds:
                                creds.append(pid)
                        except ValueError:
                            pass
                launch = AwxService.launch_job(
                    extra_vars={
                        "schema_version": 1,
                        "run_id": run_id,
                        "run_type": "sql_verify",
                        "callback_url": callback_url,
                        "items": [item],
                    },
                    credentials=creds if creds else None,
                )
                awx_job_id = launch.get("awx_job_id")
                run.awx_job_id = awx_job_id
                run.status = "launched"
                db.commit()
            except AwxServiceError as exc:
                run.status = "failed"
                run.error_message = str(exc)
                db.commit()
                overall_status = "partial_failed"

            verify_run_ids.append(int(run.id))
            collector_run_ids.append(run_id)

        return {
            "verify_run_ids": verify_run_ids,
            "collector_run_ids": collector_run_ids,
            "status": overall_status,
            "awx_job_id": awx_job_id,
        }

    @staticmethod
    def get_verify_sql_result(db: Session, *, verify_run_id: int) -> dict[str, Any]:
        """Phase 3.5: poll endpoint for an in-flight SQL verify run."""
        run = db.query(CollectorRun).filter(CollectorRun.id == verify_run_id).first()
        if not run:
            raise LookupError(f"verify run 不存在: {verify_run_id}")
        run_type = (run.request_payload or {}).get("run_type") or ""
        if run_type != "sql_verify":
            raise ValueError("该 run 不是 sql_verify 类型")

        # Pull the latest result row for this run.
        result_row = (
            db.query(CollectorRunResult)
            .filter(CollectorRunResult.run_id == run.run_id)
            .order_by(CollectorRunResult.id.desc())
            .first()
        )
        raw = (result_row.raw_result if result_row else {}) or {}
        columns = raw.get("columns") or []
        rows = raw.get("rows") or []

        if run.status in {"pending", "launched", "running"}:
            status = "running"
            verified = False
            success = False
        elif run.status == "failed":
            status = "failed"
            verified = False
            success = False
        else:
            status = run.status
            verified = bool(columns or rows)
            success = verified

        return {
            "success": success,
            "verified": verified,
            "status": status,
            "sql_hash": raw.get("sql_hash"),
            "duration_ms": raw.get("duration_ms"),
            "columns": columns,
            "rows": rows,
            "message": run.error_message or raw.get("message"),
            "error_code": raw.get("error_code"),
            "connector": raw.get("connector"),
        }

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

        # Plan v5.1 (post-verification 2026-06-26): reject item_codes whose
        # db_type_code does not match the target instance db_type set.
        # Without this, Oracle instances end up running MSSQL SQLs
        # (parse_failed / connection_failed), and vice versa.
        # Skip only when the user explicitly opts into a full fleet scan.
        target_db_types = InspectionService._resolve_target_db_types(
            db, asset_ids=payload.asset_ids, db_type_code=payload.db_type_code
        )
        InspectionService._validate_item_codes_db_type(
            rows, target_db_types, allow_mixed=bool(payload.confirm_fleet_scan)
        )

        check_codes = CheckItemBuilderRegistry.resolve_check_codes_for_inspection_items(requested_item_codes, db=db)
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
            # Phase 3.5: only the user-selected inspection items should be
            # dispatched, NOT every enabled DB_READONLY_SQL_EXEC row.
            inspection_item_codes=requested_item_codes,
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
        db.flush()

        # v5.1: Create task_item snapshots
        for idx, item in enumerate(rows):
            rule_config_snapshot = item.rule_config or {}
            sql_text = rule_config_snapshot.get("sql_text") or ""
            task_item = InspectionTaskItem(
                task_id=int(task.id),
                inspection_item_id=int(item.id),
                item_code=item.item_code,
                item_name=item.item_name,
                check_code=item.check_code,
                executor_type=item.executor_type,
                target_scope=item.target_scope,
                db_type_code=item.db_type_code,
                category=item.category,
                inspection_type=item.inspection_type,
                item_kind=item.item_kind,
                evaluator_type=item.evaluator_type,
                severity=item.severity,
                weight=int(item.weight or 10),
                rule_version=item.rule_version,
                rule_config_snapshot=rule_config_snapshot,
                applicability_snapshot=item.applicability or {},
                enabled_snapshot=bool(item.enabled),
                description_snapshot=item.description,
                sql_hash=item.sql_hash or InspectionService._compute_sql_hash(sql_text),
                rule_hash=item.rule_hash or InspectionService._compute_rule_hash(
                    item.check_code, item.executor_type, rule_config_snapshot, item.applicability
                ),
                check_order=idx,
            )
            db.add(task_item)

        # v5.1: Create task_target snapshots from batch result assets
        asset_ids_list: list[int] = list(batch.get("asset_ids") or []) or (payload.asset_ids or [])
        if asset_ids_list:
            instances = db.query(DbInstance).filter(DbInstance.id.in_(asset_ids_list)).all()
            instance_map = {int(i.id): i for i in instances}
            servers = db.query(Server).filter(Server.id.in_([i.server_id for i in instances])).all()
            server_map = {int(s.id): s for s in servers}
            db_types = db.query(DbType).filter(DbType.id.in_([i.db_type_id for i in instances])).all()
            db_type_map = {int(dt.id): dt for dt in db_types}

            # Bug 4 fix 2026-06-26: BatchCollectorService.create_batch_run has
            # already returned, which means the dispatch has been kicked off
            # (either an AWX launch or DB_READONLY_SQL_EXEC in-band exec).
            # plan §2.3 says dispatch_status moves pending → dispatched once
            # the dispatch has been initiated. The "skipped" path is reserved
            # for assets the batch layer explicitly chose to skip (e.g.
            # CREDENTIAL_MISSING) — those are surfaced in batch["skipped"].
            skipped_asset_ids: set[int] = set(
                int(a.get("asset_id") or 0) for a in (batch.get("skipped") or [])
                if int(a.get("asset_id") or 0) > 0
            )
            batch_status = (batch.get("status") or "").strip().lower()
            # When the entire batch failed to launch (e.g. AWX down), mark
            # every target as dispatch_failed. Otherwise the in-flight
            # dispatch is "dispatched".
            if batch_status == "failed":
                initial_dispatch_status = "dispatch_failed"
            elif batch_status in {"dispatch_failed", "partial_failed"}:
                # Per-asset split: skipped ids get "skipped", others "dispatched".
                initial_dispatch_status = None  # decide per-asset below
            else:
                initial_dispatch_status = "dispatched"

            for asset_id in asset_ids_list:
                instance = instance_map.get(asset_id)
                if not instance:
                    continue
                server = server_map.get(int(instance.server_id))
                db_type = db_type_map.get(int(instance.db_type_id)) if instance.db_type_id else None
                if initial_dispatch_status is None:
                    asset_dispatch = "skipped" if asset_id in skipped_asset_ids else "dispatched"
                else:
                    asset_dispatch = initial_dispatch_status
                task_target = InspectionTaskTarget(
                    task_id=int(task.id),
                    target_type="db_instance",
                    target_id=asset_id,
                    target_name_snapshot=instance.instance_name,
                    host_snapshot=str(server.ip_address) if server else None,
                    port_snapshot=int(instance.port) if instance.port else None,
                    db_type_code_snapshot=db_type.type_code if db_type else None,
                    asset_snapshot={
                        "instance_name": instance.instance_name,
                        "db_version": instance.db_version.version_code if instance.db_version else None,
                        "node_role": instance.node_role,
                        "cluster_name": instance.cluster.cluster_name if instance.cluster else None,
                        "business_system_id": instance.cluster.business_system_id if instance.cluster else None,
                        "site_id": server.site_id if server else None,
                    },
                    dispatch_status=asset_dispatch,
                    execution_status="pending",
                )
                db.add(task_target)

        db.commit()
        db.refresh(task)

        # plan §9.2: inspection.task.created audit event
        asset_event_history_service.record_event(
            db,
            asset_type="inspection_task",
            asset_id=int(task.id),
            event_type="inspection.task.created",
            reason=f"item_codes={requested_item_codes}",
            operator=requested_by,
            changed_fields={
                "task_code": task.task_code,
                "status": task.status,
                "total_item_count": int(batch.get("total_item_count") or 0),
            },
        )
        db.commit()

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
    def _resolve_target_db_types(
        db: Session,
        *,
        asset_ids: list[int] | None,
        db_type_code: str | None,
    ) -> set[str]:
        """Resolve the set of db_type_codes implied by the task's asset scope.

        Used by create_task to validate that every selected inspection item
        actually applies to the target db_type. Returns a lowercase set so
        callers can do simple `in` checks.
        """
        if asset_ids:
            instances = (
                db.query(DbInstance).filter(DbInstance.id.in_(asset_ids)).all()
            )
            db_type_ids = {int(i.db_type_id) for i in instances if i.db_type_id}
            if not db_type_ids:
                return set()
            rows = db.query(DbType).filter(DbType.id.in_(db_type_ids)).all()
            return {(r.type_code or "").lower() for r in rows if r.type_code}
        if db_type_code:
            return {db_type_code.lower()}
        return set()

    @staticmethod
    def _validate_item_codes_db_type(
        rows: list[InspectionItem],
        target_db_types: set[str],
        *,
        allow_mixed: bool,
    ) -> None:
        """Reject item_codes whose db_type_code is outside the target set.

        Plan v5.1 post-verification (2026-06-26): Oracle instances were
        dispatching MSSQL SQLs (parse_failed / connection_failed). Each
        InspectionItem has a db_type_code (oracle / mssql / null for
        db-type-agnostic). When the user has picked a single db_type, all
        items must belong to that db_type; when the user has explicitly
        opted into a fleet scan (allow_mixed=True) we skip the check because
        mixed runs are intentional and the v5.1 expected-matrix logic in
        generate_report will backfill missing results.
        """
        if not target_db_types or allow_mixed:
            return
        mismatched: list[str] = []
        for row in rows:
            item_db_type = (row.db_type_code or "").lower() or None
            if item_db_type is None:
                # db-type-agnostic items (e.g. connectivity) run on any target
                continue
            if item_db_type not in target_db_types:
                mismatched.append(f"{row.item_code}({item_db_type})")
        if mismatched:
            sorted_targets = ", ".join(sorted(target_db_types))
            raise ValueError(
                "巡检项与目标 db_type 不一致："
                f"{mismatched} 不可在 [{sorted_targets}] 实例上执行；"
                "请取消勾选不匹配的巡检项，或勾选同 db_type 的实例。"
            )

    @staticmethod
    def _is_task_item_applicable(
        task_item: InspectionTaskItem, task_target: InspectionTaskTarget
    ) -> bool:
        """Decide whether a task_item was expected to run on a task_target.

        Used by generate_report's expected-matrix loop. Mirrors the dispatch
        filter in _DbReadonlySqlExecBuilder.build: a SQL inspection item
        applies only when its db_type_code is NULL (db-type-agnostic) or
        matches the target instance's db_type_code_snapshot. Items that
        don't apply are simply excluded from the matrix — they do not get
        placeholder rows and do not affect health scoring.

        Post-verification 2026-06-26: this guard is what stops Oracle
        instances from showing up as "ran MSSQL items" in the report.
        """
        item_db_type = (getattr(task_item, "db_type_code", None) or "").lower() or None
        target_db_type = (getattr(task_target, "db_type_code_snapshot", None) or "").lower() or None
        if item_db_type is None:
            # db-type-agnostic items (e.g. connectivity) apply to every target
            return True
        if target_db_type is None:
            # target has no db_type snapshot → treat as inapplicable (we
            # cannot tell, so don't manufacture expected results)
            return False
        return item_db_type == target_db_type

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
            normalized_check = (callback_item.check_code or "").strip().upper()
            # Phase 3.5: DB_READONLY_SQL_EXEC results carry their business
            # identity at the TOP LEVEL of the callback item (task_id /
            # inspection_item_id / item_code / business_domain). Build the
            # inspection_result row directly from those fields instead of
            # routing through the generic check_code→item mapping, which
            # does not understand SQL-backed items.
            if normalized_check == "DB_READONLY_SQL_EXEC":
                rows.extend(
                    InspectionService._build_sql_readonly_result_row(callback_item)
                )
                continue
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
    def _build_sql_readonly_result_row(
        callback_item: CollectorCallbackItem,
    ) -> list[dict[str, Any]]:
        """Build inspection_result rows for a single DB_READONLY_SQL_EXEC callback item.

        Uses the explicit business fields at the top level of the callback
        item (``task_id``, ``inspection_item_id``, ``item_code``,
        ``business_domain``). Falls back to ``item_code`` parsed from the
        evidence payload if the top-level fields are missing (defensive —
        should never happen with the Phase 3.5 AWX playbook).
        """
        raw = dict(callback_item.raw_result or {})
        item_code = callback_item.item_code or raw.get("item_code")
        inspection_item_id = callback_item.inspection_item_id or raw.get("inspection_item_id")
        severity = raw.get("severity") or "warning"
        result_status = InspectionService._normalize_result_status(
            raw.get("result_status") or "unknown"
        )
        # Empty rows → caller passed valid SQL that returned nothing → normal.
        if not raw.get("rows") and result_status == "unknown":
            result_status = "normal"
        message = (
            raw.get("message")
            or callback_item.message
            or "no abnormal rows"
        )
        evidence = {
            "collector_item_key": callback_item.item_key,
            "columns": raw.get("columns") or [],
            "rows": raw.get("rows") or [],
            "duration_ms": raw.get("duration_ms"),
            "sql_hash": raw.get("sql_hash"),
            "connector": raw.get("connector"),
            "stderr": (raw.get("stderr") or "")[:4000],
            "rc": raw.get("rc"),
            "raw_result": raw,
        }
        return [
            {
                "item_code": item_code or "SQL_READONLY",
                "result_code": item_code or callback_item.check_code,
                "result_status": result_status,
                "target_scope": callback_item.target_scope,
                "asset_id": int(callback_item.asset_id),
                "severity": severity,
                "message": message,
                "check_code": callback_item.check_code,
                "evidence": evidence,
            }
        ]

    @staticmethod
    def save_callback_results(
        db: Session,
        *,
        run: CollectorRun,
        callback_items: list[CollectorCallbackItem],
        explicit_results: list[CollectorInspectionCallbackItem] | None = None,
    ) -> int:
        """v5.1: Save callback results with evaluator rule engine.

        For each callback item:
        1. Parse collector return value
        2. Normalize execution_status
        3. Run evaluator → evaluation_status + evidence
        4. UPSERT inspection_result (attempt_no comparison)
        5. Update task_target state
        """
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

        # Resolve task items and targets
        task_items = db.query(InspectionTaskItem).filter(
            InspectionTaskItem.task_id == int(task.id)
        ).all()
        task_items_by_code = {ti.item_code: ti for ti in task_items}

        task_targets = db.query(InspectionTaskTarget).filter(
            InspectionTaskTarget.task_id == int(task.id)
        ).all()
        task_targets_by_asset = {tt.target_id: tt for tt in task_targets}

        run_items = (
            db.query(CollectorRunItem)
            .filter(CollectorRunItem.collector_run_id == run.id)
            .all()
        )
        run_item_map = {ri.item_key: ri for ri in run_items}

        saved = 0
        now = InspectionService._now()

        for row in merged_results:
            task_item = task_items_by_code.get(row["item_code"])
            if task_item is None:
                continue
            task_target = task_targets_by_asset.get(int(row["asset_id"]))
            if task_target is None:
                continue

            # Determine execution_status from collector result
            evidence = row.get("evidence") or {}
            raw_result = evidence.get("raw_result") or {}
            raw_status = (raw_result.get("status") or row.get("result_status") or "success").strip().lower()
            execution_status = InspectionService._normalize_execution_status(raw_status)

            # Run evaluator
            columns = evidence.get("columns") or []
            rows = evidence.get("rows") or []
            rule_config = task_item.rule_config_snapshot or {}

            try:
                eval_result = InspectionEvaluatorService.evaluate(
                    rule_config, columns, rows, execution_status=execution_status
                )
            except Exception:
                eval_result = {
                    "evaluation_status": "unknown",
                    "findings": [],
                    "message": "evaluator error",
                }

            evaluation_status = eval_result["evaluation_status"]

            # Standard evidence structure
            standard_evidence = {
                "schema_version": 1,
                "columns": columns,
                "rows": rows[:200],  # max 200 stored rows
                "findings": eval_result.get("findings") or [],
                "source_severity": row.get("severity") or "warning",
                "connector": raw_result.get("connector"),
                "duration_ms": raw_result.get("duration_ms"),
                "sql_hash": raw_result.get("sql_hash"),
                "rc": raw_result.get("rc"),
                "stderr": (raw_result.get("stderr") or "")[:4000],
                "truncated": len(rows) > 200,
                "original_row_count": len(rows),
                "stored_row_count": min(len(rows), 200),
                "attempt_no": 1,
                "previous_attempt_count": 0,
            }

            attempt_no = 1
            collector_item_key = evidence.get("collector_item_key")
            collector_run_item = run_item_map.get(collector_item_key) if collector_item_key else None

            # v5.1: UPSERT by (task_id, task_item_id, task_target_id)
            existing = db.query(InspectionResult).filter(
                InspectionResult.task_id == int(task.id),
                InspectionResult.task_item_id == int(task_item.id),
                InspectionResult.task_target_id == int(task_target.id),
            ).first()

            if existing:
                if attempt_no > (existing.attempt_no or 0):
                    # Overwrite with newer attempt
                    existing.execution_status = execution_status
                    existing.evaluation_status = evaluation_status
                    existing.message = row.get("message") or eval_result.get("message")
                    existing.evidence = standard_evidence
                    existing.attempt_no = attempt_no
                    existing.collector_run_id = int(run.id)
                    existing.received_at = now
                    existing.detected_at = now
                # else: old attempt, skip
            else:
                new_result = InspectionResult(
                    task_id=int(task.id),
                    task_item_id=int(task_item.id),
                    task_target_id=int(task_target.id),
                    collector_run_id=int(run.id),
                    collector_run_item_id=int(collector_run_item.id) if collector_run_item else None,
                    target_type=row["target_scope"],
                    target_id=int(row["asset_id"]),
                    result_code=row.get("result_code") or row["item_code"],
                    execution_status=execution_status,
                    evaluation_status=evaluation_status,
                    message=row.get("message") or eval_result.get("message"),
                    evidence=standard_evidence,
                    attempt_no=attempt_no,
                    received_at=now,
                    detected_at=now,
                )
                db.add(new_result)

            # Update task_target state
            if task_target.execution_status in ("pending", "running"):
                task_target.execution_status = "success" if execution_status == "success" else execution_status
                task_target.last_callback_at = now
                if task_target.execution_status in ("success", "partial_success", "failed", "cancelled"):
                    task_target.finished_at = now

            saved += 1

        if saved > 0:
            db.commit()

            # v5.1: Attempt auto report generation after callback
            InspectionService._try_auto_generate_report(db, task)

        return saved

    @staticmethod
    def _normalize_execution_status(raw: str) -> str:
        """Map collector statuses to execution_status enum."""
        status = raw.strip().lower()
        if status in ("success", "ok", "completed"):
            return "success"
        if status in ("timeout", "timed_out"):
            return "timeout"
        if status in ("permission_denied", "access_denied", "auth_failed"):
            return "permission_denied"
        if status in ("connection_failed", "connect_error", "host_unreachable"):
            return "connection_failed"
        if status in ("parse_failed", "parse_error", "invalid_result"):
            return "parse_failed"
        if status in ("skipped", "not_applicable"):
            return "skipped"
        if status in ("failed", "error"):
            return "failed"
        return "failed" if "fail" in status or "error" in status else "success"

    # =====================================================================
    # v5.1 Report Generation
    # =====================================================================

    @staticmethod
    def _try_auto_generate_report(db: Session, task: InspectionTask) -> None:
        """Attempt auto report generation after callback if all targets are terminal."""
        if not InspectionService._all_targets_terminal(db, task):
            return

        # Check if report already exists
        existing = db.query(InspectionReport).filter(
            InspectionReport.task_id == int(task.id)
        ).first()
        if existing and existing.report_status == "ready":
            return

        try:
            InspectionService.generate_report(db, task, generated_reason="auto")
        except Exception:
            # Auto-generation failure should not break callback
            pass

    @staticmethod
    def _all_targets_terminal(db: Session, task: InspectionTask) -> bool:
        """Check if all task targets have reached terminal state."""
        if not task.task_targets:
            return False
        terminal = {"success", "partial_success", "failed", "cancelled", "dispatch_failed", "skipped"}
        for tt in task.task_targets:
            exec_terminal = tt.execution_status in terminal
            dispatch_terminal = tt.dispatch_status in ("dispatch_failed", "skipped")
            if not exec_terminal and not dispatch_terminal:
                return False
        return True

    @staticmethod
    def generate_report(
        db: Session,
        task: InspectionTask,
        *,
        generated_reason: str = "auto",
        generated_by: str | None = None,
    ) -> dict[str, Any]:
        """Generate (or regenerate) a report from saved inspection_results.

        Steps:
        1. Compute expected matrix (task_targets × task_items)
        2. Fill missing results with placeholder rows
        3. Aggregate instance reports per task_target
        4. Aggregate overall report
        5. UPSERT inspection_report + inspection_instance_report
        """
        now = InspectionService._now()
        task_id = int(task.id)

        task_items = db.query(InspectionTaskItem).filter(
            InspectionTaskItem.task_id == task_id
        ).order_by(InspectionTaskItem.check_order).all()

        task_targets = db.query(InspectionTaskTarget).filter(
            InspectionTaskTarget.task_id == task_id
        ).all()

        existing_results = db.query(InspectionResult).filter(
            InspectionResult.task_id == task_id
        ).all()
        result_key = {(r.task_item_id, r.task_target_id): r for r in existing_results}

        # Expected matrix: fill missing results
        all_evaluable = [ti for ti in task_items if ti.item_kind != "information"]
        instance_healths: list[dict[str, Any]] = []
        total_counts = {
            "normal": 0, "warning": 0, "critical": 0,
            "unknown": 0, "not_evaluated": 0,
            "collection_failed": 0, "missing": 0,
        }
        total_targets = len(task_targets)

        for tt in task_targets:
            instance_results: list[dict[str, Any]] = []

            for ti in task_items:
                # Post-verification 2026-06-26: do NOT count inapplicable
                # task_items toward the expected matrix. Without this guard,
                # an Oracle instance's task_target ends up with placeholder
                # rows for every MSSQL item in the task (because the
                # _DbReadonlySqlExecBuilder skipped them at dispatch time on
                # db_type mismatch, so no real result ever arrived). Those
                # placeholders polluted the health score (penalty 0.2 each)
                # and made the UI list the wrong inspection items under the
                # wrong instance.
                if not InspectionService._is_task_item_applicable(ti, tt):
                    continue

                r = result_key.get((int(ti.id), int(tt.id)))
                if r is None:
                    # Missing result → placeholder
                    placeholder = InspectionService._create_missing_result(
                        db, task_id, int(ti.id), int(tt.id), ti, tt, now
                    )
                    instance_results.append({
                        "evaluation_status": "unknown",
                        "weight": int(ti.weight or 10),
                        "item_kind": ti.item_kind,
                        "execution_status": "skipped",
                    })
                    total_counts["missing"] += 1
                    total_counts["collection_failed"] += 1
                else:
                    # v5.1: re-evaluate on regenerate so evaluator bug fixes
                    # take effect without re-executing the collector.
                    InspectionService._re_evaluate_result(r, ti)
                    instance_results.append({
                        "evaluation_status": r.evaluation_status,
                        "weight": int(ti.weight or 10),
                        "item_kind": ti.item_kind,
                        "execution_status": r.execution_status,
                    })
                    status = r.evaluation_status or "not_evaluated"
                    if status in total_counts:
                        total_counts[status] += 1
                    if r.execution_status != "success":
                        total_counts["collection_failed"] += 1

            # Compute instance health
            instance_health = InspectionEvaluatorService.compute_instance_health(instance_results)
            instance_healths.append(instance_health)

            # UPSERT instance_report
            irep = db.query(InspectionInstanceReport).filter(
                InspectionInstanceReport.report_id == (
                    db.query(InspectionReport.id).filter(
                        InspectionReport.task_id == task_id
                    ).scalar_subquery()
                ),
                InspectionInstanceReport.task_target_id == int(tt.id),
            ).first() if db.query(InspectionReport).filter(
                InspectionReport.task_id == task_id
            ).first() is not None else None

            if irep:
                irep.health_level = instance_health["health_level"]
                irep.health_score = instance_health["health_score"]
                irep.normal_count = instance_health.get("normal_count", 0)
                irep.warning_count = instance_health.get("warning_count", 0)
                irep.critical_count = instance_health.get("critical_count", 0)
                irep.unknown_count = instance_health.get("unknown_count", 0)
                irep.not_evaluated_count = instance_health.get("not_evaluated_count", 0)
                irep.collection_failed_count = sum(
                    1 for r in instance_results if r.get("execution_status") != "success"
                )
                irep.generated_at = now
            else:
                irep = InspectionInstanceReport(
                    task_id=task_id,
                    task_target_id=int(tt.id),
                    target_type=tt.target_type,
                    target_id=int(tt.target_id),
                    health_level=instance_health["health_level"],
                    health_score=instance_health["health_score"],
                    normal_count=instance_health.get("normal_count", 0),
                    warning_count=instance_health.get("warning_count", 0),
                    critical_count=instance_health.get("critical_count", 0),
                    unknown_count=instance_health.get("unknown_count", 0),
                    not_evaluated_count=instance_health.get("not_evaluated_count", 0),
                    collection_failed_count=sum(
                        1 for r in instance_results if r.get("execution_status") != "success"
                    ),
                    generated_at=now,
                )

        # Compute overall health
        report_health = InspectionEvaluatorService.compute_report_health(instance_healths)

        # Overall counts
        healthy_count = sum(1 for h in instance_healths if h["health_level"] == "healthy")
        warning_count = sum(1 for h in instance_healths if h["health_level"] == "warning")
        critical_count = sum(1 for h in instance_healths if h["health_level"] == "critical")
        unknown_count = sum(1 for h in instance_healths if h["health_level"] == "unknown")
        not_assessed_count = sum(1 for h in instance_healths if h["health_level"] == "not_assessed")

        # UPSERT report
        report = db.query(InspectionReport).filter(
            InspectionReport.task_id == task_id
        ).first()

        report_code = report.report_code if report else InspectionService._generate_report_code()

        # Plan §5.6: compute source_data_hash from canonical (items, targets, results).
        # Use saved results + placeholders we just inserted so hash reflects the
        # final report content. Fetch again to pick up the just-added placeholders.
        all_results = db.query(InspectionResult).filter(
            InspectionResult.task_id == task_id
        ).all()
        source_data_hash = InspectionService._compute_source_data_hash(
            task_items, task_targets, all_results
        )

        # Build report-level summary JSONB
        report_summary = InspectionService._build_report_summary(
            db,
            task_id=task_id,
            task_items=task_items,
            total_counts=total_counts,
            instance_healths=instance_healths,
        )

        if report:
            report.report_status = "ready"
            report.health_level = report_health["health_level"]
            report.health_score = report_health["health_score"]
            report.total_target_count = total_targets
            report.healthy_count = healthy_count
            report.warning_count = warning_count
            report.critical_count = critical_count
            report.unknown_count = unknown_count
            report.not_assessed_count = not_assessed_count
            report.normal_item_count = total_counts["normal"]
            report.warning_item_count = total_counts["warning"]
            report.critical_item_count = total_counts["critical"]
            report.unknown_item_count = total_counts["unknown"]
            report.collection_failed_count = total_counts["collection_failed"]
            report.missing_result_count = total_counts["missing"]
            report.rule_engine_version = InspectionEvaluatorService.RULE_ENGINE_VERSION
            report.source_data_hash = source_data_hash
            report.source_result_count = len(existing_results)
            report.summary = report_summary
            report.generated_reason = generated_reason
            report.generated_by = generated_by
            report.generated_at = now
            report.updated_at = now
        else:
            report = InspectionReport(
                report_code=report_code,
                summary=report_summary,
                task_id=task_id,
                report_status="ready",
                health_level=report_health["health_level"],
                health_score=report_health["health_score"],
                total_target_count=total_targets,
                healthy_count=healthy_count,
                warning_count=warning_count,
                critical_count=critical_count,
                unknown_count=unknown_count,
                not_assessed_count=not_assessed_count,
                normal_item_count=total_counts["normal"],
                warning_item_count=total_counts["warning"],
                critical_item_count=total_counts["critical"],
                unknown_item_count=total_counts["unknown"],
                collection_failed_count=total_counts["collection_failed"],
                missing_result_count=total_counts["missing"],
                rule_engine_version=InspectionEvaluatorService.RULE_ENGINE_VERSION,
                source_data_hash=source_data_hash,
                source_result_count=len(existing_results),
                generated_reason=generated_reason,
                generated_by=generated_by,
                generated_at=now,
            )
            db.add(report)

        db.flush()

        # Link instance_reports to report
        for irep_data in []:  # already handled above
            pass
        # Batch upsert instance reports (Bug 5 fix 2026-06-26: populate
        # summary JSONB with the target's db_type/host/port and the
        # top abnormal findings so the DOCX export and the InstanceReport
        # page can surface at-a-glance triage context).
        ireps_to_save: list[InspectionInstanceReport] = []
        for tt, ih in zip(task_targets, instance_healths):
            instance_summary = InspectionService._build_instance_summary(
                db, task_id=task_id, task_target=tt, instance_health=ih, now=now
            )
            existing_irep = db.query(InspectionInstanceReport).filter(
                InspectionInstanceReport.report_id == int(report.id),
                InspectionInstanceReport.task_target_id == int(tt.id),
            ).first()
            if existing_irep:
                existing_irep.health_level = ih["health_level"]
                existing_irep.health_score = ih["health_score"]
                existing_irep.normal_count = ih.get("normal_count", 0)
                existing_irep.warning_count = ih.get("warning_count", 0)
                existing_irep.critical_count = ih.get("critical_count", 0)
                existing_irep.unknown_count = ih.get("unknown_count", 0)
                existing_irep.not_evaluated_count = ih.get("not_evaluated_count", 0)
                existing_irep.summary = instance_summary
                existing_irep.generated_at = now
            else:
                ireps_to_save.append(InspectionInstanceReport(
                    report_id=int(report.id),
                    task_id=task_id,
                    task_target_id=int(tt.id),
                    target_type=tt.target_type,
                    target_id=int(tt.target_id),
                    health_level=ih["health_level"],
                    health_score=ih["health_score"],
                    normal_count=ih.get("normal_count", 0),
                    warning_count=ih.get("warning_count", 0),
                    critical_count=ih.get("critical_count", 0),
                    unknown_count=ih.get("unknown_count", 0),
                    not_evaluated_count=ih.get("not_evaluated_count", 0),
                    summary=instance_summary,
                    generated_at=now,
                ))
        for irep in ireps_to_save:
            db.add(irep)

        db.commit()
        db.refresh(report)

        return InspectionService._report_to_dict(report)

    @staticmethod
    def _build_instance_summary(
        db: Session,
        *,
        task_id: int,
        task_target: InspectionTaskTarget,
        instance_health: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        """Build a structured summary for an InspectionInstanceReport row.

        Bug 5 fix 2026-06-26: previously the report was always saved with
        summary = {} because generate_report never assigned this column.
        The DOCX export and the InstanceReport page both rely on summary
        for at-a-glance triage. Layout:

        {
          "db_type": "ORACLE" | "SQLSERVER" | ...,
          "host": "10.134.183.147",
          "port": 1526,
          "instance_name": "ework",
          "item_breakdown": {"information": 1, "metric": 3, ...},
          "top_findings": [
            {"item_code": "...", "evaluation_status": "critical",
             "message": "...", "execution_status": "success"},
            ...   # up to 5 most severe findings
          ],
          "status_distribution": {"normal": 2, "warning": 0, ...}
        }
        """
        # Item breakdown by item_kind for the items that actually applied
        # to this target.
        applicable_items = [
            ti for ti in (
                db.query(InspectionTaskItem)
                .filter(InspectionTaskItem.task_id == task_id)
                .all()
            )
            if InspectionService._is_task_item_applicable(ti, task_target)
        ]
        item_breakdown: dict[str, int] = {}
        for ti in applicable_items:
            kind = (ti.item_kind or "unknown").lower()
            item_breakdown[kind] = item_breakdown.get(kind, 0) + 1

        # Top findings = results with evaluation_status in
        # (critical, warning, unknown) sorted by severity, capped at 5.
        severity_rank = {"critical": 0, "warning": 1, "unknown": 2, "not_evaluated": 3, "normal": 4}
        results_for_target = (
            db.query(InspectionResult, InspectionTaskItem)
            .join(InspectionTaskItem, InspectionTaskItem.id == InspectionResult.task_item_id)
            .filter(
                InspectionResult.task_id == task_id,
                InspectionResult.task_target_id == int(task_target.id),
            )
            .all()
        )
        findings: list[dict[str, Any]] = []
        for r, ti in results_for_target:
            if r.evaluation_status not in {"critical", "warning", "unknown"}:
                continue
            findings.append({
                "item_code": r.result_code or ti.item_code,
                "item_name": ti.item_name,
                "evaluation_status": r.evaluation_status,
                "execution_status": r.execution_status,
                "message": r.message,
            })
        findings.sort(key=lambda f: severity_rank.get(f["evaluation_status"], 99))
        top_findings = findings[:5]

        # status_distribution = count of results per evaluation_status for
        # this target (across applicable items).
        status_distribution: dict[str, int] = {}
        for r, _ti in results_for_target:
            key = r.evaluation_status or "not_evaluated"
            status_distribution[key] = status_distribution.get(key, 0) + 1

        return {
            "db_type": task_target.db_type_code_snapshot,
            "host": task_target.host_snapshot,
            "port": int(task_target.port_snapshot) if task_target.port_snapshot else None,
            "instance_name": task_target.target_name_snapshot,
            "item_breakdown": item_breakdown,
            "top_findings": top_findings,
            "status_distribution": status_distribution,
        }

    @staticmethod
    def _build_report_summary(
        db: Session,
        *,
        task_id: int,
        task_items: list[InspectionTaskItem],
        total_counts: dict[str, int],
        instance_healths: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build structured summary for the InspectionReport row.

        Complements _build_instance_summary at the report level so the
        Reports list page can display at-a-glance triage without loading
        every instance report individually.
        """
        # Item breakdown by item_kind
        item_breakdown: dict[str, int] = {}
        for ti in task_items:
            kind = (ti.item_kind or "unknown").lower()
            item_breakdown[kind] = item_breakdown.get(kind, 0) + 1

        # status_distribution from total_counts (across all targets)
        status_distribution = {
            "normal": total_counts.get("normal", 0),
            "warning": total_counts.get("warning", 0),
            "critical": total_counts.get("critical", 0),
            "unknown": total_counts.get("unknown", 0),
            "not_evaluated": total_counts.get("not_evaluated", 0),
        }

        # Top findings across all instances (most severe first)
        severity_rank = {"critical": 0, "warning": 1, "unknown": 2}
        all_findings: list[dict[str, Any]] = []
        all_results = (
            db.query(InspectionResult, InspectionTaskItem)
            .join(InspectionTaskItem, InspectionTaskItem.id == InspectionResult.task_item_id)
            .filter(InspectionResult.task_id == task_id)
            .all()
        )
        for r, ti in all_results:
            if r.evaluation_status not in {"critical", "warning", "unknown"}:
                continue
            all_findings.append({
                "item_code": r.result_code or ti.item_code,
                "item_name": ti.item_name,
                "evaluation_status": r.evaluation_status,
                "message": (r.message or "")[:200],
                "execution_status": r.execution_status,
            })
        all_findings.sort(key=lambda f: severity_rank.get(f["evaluation_status"], 99))
        top_findings = all_findings[:5]

        # Target health level distribution
        target_summary = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0, "not_assessed": 0}
        for h in instance_healths:
            level = h.get("health_level") or "not_assessed"
            target_summary[level] = target_summary.get(level, 0) + 1

        return {
            "item_breakdown": item_breakdown,
            "status_distribution": status_distribution,
            "top_findings": top_findings,
            "target_summary": target_summary,
        }

    @staticmethod
    def _re_evaluate_result(
        result: InspectionResult,
        task_item: InspectionTaskItem,
    ) -> None:
        """Re-evaluate a stored inspection_result using the current evaluator.

        v5.1: Called during generate_report so evaluator bug fixes apply to
        already-collected results without re-executing the collector.
        Only re-evaluates when evidence contains rows/columns and the
        execution was successful (no-op for placeholders and failures).
        """
        if result.execution_status != "success":
            return
        evidence = result.evidence or {}
        columns = evidence.get("columns") or []
        rows = evidence.get("rows") or []
        if not columns and not rows:
            return  # skip placeholders / empty evidence
        rule_config = task_item.rule_config_snapshot or {}
        try:
            eval_result = InspectionEvaluatorService.evaluate(
                rule_config, columns, rows, execution_status=result.execution_status
            )
        except Exception:
            return  # keep existing status on evaluator error
        result.evaluation_status = eval_result.get("evaluation_status", result.evaluation_status)
        # Update stored evidence findings with the fresh evaluation
        evidence["findings"] = eval_result.get("findings") or []
        result.evidence = evidence

    @staticmethod
    def _create_missing_result(
        db: Session,
        task_id: int,
        task_item_id: int,
        task_target_id: int,
        task_item: InspectionTaskItem,
        task_target: InspectionTaskTarget,
        now: datetime,
    ) -> InspectionResult:
        """Create placeholder result for expected but missing inspection result."""
        placeholder = InspectionResult(
            task_id=task_id,
            task_item_id=task_item_id,
            task_target_id=task_target_id,
            target_type=task_target.target_type,
            target_id=int(task_target.target_id),
            result_code=task_item.item_code,
            execution_status="skipped",
            evaluation_status="unknown",
            message="未收到预期巡检结果",
            evidence={
                "schema_version": 1,
                "error_code": "MISSING_RESULT",
                "columns": [],
                "rows": [],
                "findings": [],
                "truncated": False,
                "attempt_no": 0,
                "previous_attempt_count": 0,
            },
            attempt_no=0,
            received_at=now,
            detected_at=now,
        )
        db.add(placeholder)
        db.flush()
        return placeholder

    @staticmethod
    def regenerate_report(
        db: Session,
        task_id: int,
        *,
        generated_by: str | None = None,
    ) -> dict[str, Any]:
        """Regenerate report from saved results only (no re-execution)."""
        task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
        if not task:
            raise LookupError(f"巡检任务不存在: {task_id}")
        return InspectionService.generate_report(
            db, task, generated_reason="regenerate", generated_by=generated_by
        )

    @staticmethod
    def get_report(db: Session, task_id: int) -> dict[str, Any]:
        """Get report for a task."""
        report = db.query(InspectionReport).filter(
            InspectionReport.task_id == task_id
        ).first()
        if not report:
            raise LookupError(f"报告不存在: task_id={task_id}")
        return InspectionService._report_to_dict(report)

    @staticmethod
    def list_reports(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        health_level: list[str] | None = None,
        report_status: str | None = None,
    ) -> dict[str, Any]:
        """List reports with pagination."""
        query = db.query(InspectionReport)
        if health_level:
            query = query.filter(InspectionReport.health_level.in_(health_level))
        if report_status:
            query = query.filter(InspectionReport.report_status == report_status)
        total = query.count()
        total_pages = max(1, (total + page_size - 1) // page_size)
        rows = query.order_by(
            InspectionReport.generated_at.desc().nullslast(),
            InspectionReport.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [InspectionService._report_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    @staticmethod
    def list_instance_reports(
        db: Session,
        *,
        report_id: int,
        health_level: str | None = None,
    ) -> list[dict[str, Any]]:
        """List instance reports for a report.

        Eagerly joins task_target so the response can surface the host IP and
        db_type_code snapshot (post-verification 2026-06-26: the report
        detail table needs IP + DB type for at-a-glance triage). The join is
        LEFT OUTER because historical reports may reference task_targets that
        were later deleted.
        """
        query = (
            db.query(InspectionInstanceReport, InspectionTaskTarget)
            .outerjoin(
                InspectionTaskTarget,
                InspectionInstanceReport.task_target_id == InspectionTaskTarget.id,
            )
            .filter(InspectionInstanceReport.report_id == report_id)
        )
        if health_level:
            query = query.filter(InspectionInstanceReport.health_level == health_level)
        return [
            InspectionService._irep_to_dict(irep, task_target=tt)
            for irep, tt in query.all()
        ]

    @staticmethod
    def get_instance_report_results(
        db: Session,
        *,
        report_id: int,
        target_type: str,
        target_id: int,
    ) -> list[dict[str, Any]]:
        """Get all results for a specific target within a report.

        Bug5 fix 2026-06-26: filter results by db_type_code applicability so
        a SQL Server instance does not show Oracle items (and vice versa)
        when a task was created with "all DB types" + "all inspection items".
        Reuses the same _is_task_item_applicable guard that generate_report
        already applies, so the in-app results list, the single-instance
        DOCX export and the report aggregation all agree.
        """
        report = db.query(InspectionReport).filter(
            InspectionReport.id == report_id
        ).first()
        if not report:
            raise LookupError(f"报告不存在: {report_id}")
        task_target = db.query(InspectionTaskTarget).filter(
            InspectionTaskTarget.task_id == int(report.task_id),
            InspectionTaskTarget.target_type == target_type,
            InspectionTaskTarget.target_id == int(target_id),
        ).first()
        task_items = db.query(InspectionTaskItem).filter(
            InspectionTaskItem.task_id == int(report.task_id),
        ).all()
        applicable_item_ids = [
            int(ti.id) for ti in task_items
            if task_target is None
            or InspectionService._is_task_item_applicable(ti, task_target)
        ]
        results = db.query(InspectionResult).filter(
            InspectionResult.task_id == int(report.task_id),
            InspectionResult.target_type == target_type,
            InspectionResult.target_id == target_id,
            InspectionResult.task_item_id.in_(applicable_item_ids),
        ).all()
        return [InspectionService._result_to_dict(r) for r in results]

    # ------------------------------------------------------------------
    # Report serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_report_code() -> str:
        now_str = datetime.now().strftime("%Y%m%d")
        suffix = secrets.token_hex(3).upper()
        return f"RPT-{now_str}-{suffix}"

    @staticmethod
    def _report_to_dict(report: InspectionReport) -> dict[str, Any]:
        return {
            "id": int(report.id),
            "report_code": report.report_code,
            "task_id": int(report.task_id),
            "report_status": report.report_status,
            "health_level": report.health_level,
            "health_score": float(report.health_score) if report.health_score is not None else None,
            "total_target_count": int(report.total_target_count or 0),
            "healthy_count": int(report.healthy_count or 0),
            "warning_count": int(report.warning_count or 0),
            "critical_count": int(report.critical_count or 0),
            "unknown_count": int(report.unknown_count or 0),
            "not_assessed_count": int(report.not_assessed_count or 0),
            "normal_item_count": int(report.normal_item_count or 0),
            "warning_item_count": int(report.warning_item_count or 0),
            "critical_item_count": int(report.critical_item_count or 0),
            "unknown_item_count": int(report.unknown_item_count or 0),
            "collection_failed_count": int(report.collection_failed_count or 0),
            "missing_result_count": int(report.missing_result_count or 0),
            "summary": report.summary or {},
            "rule_engine_version": report.rule_engine_version,
            "source_data_hash": report.source_data_hash,
            "source_result_count": int(report.source_result_count or 0),
            "generated_reason": report.generated_reason,
            "generated_by": report.generated_by,
            "generated_at": report.generated_at,
            "created_at": report.created_at,
            "updated_at": report.updated_at,
        }

    @staticmethod
    def _irep_to_dict(
        irep: InspectionInstanceReport,
        *,
        task_target: InspectionTaskTarget | None = None,
    ) -> dict[str, Any]:
        return {
            "id": int(irep.id),
            "report_id": int(irep.report_id),
            "task_id": int(irep.task_id),
            "task_target_id": int(irep.task_target_id),
            "target_type": irep.target_type,
            "target_id": int(irep.target_id),
            "host_snapshot": task_target.host_snapshot if task_target else None,
            "db_type_code_snapshot": task_target.db_type_code_snapshot if task_target else None,
            "health_level": irep.health_level,
            "health_score": float(irep.health_score) if irep.health_score is not None else None,
            "normal_count": int(irep.normal_count or 0),
            "warning_count": int(irep.warning_count or 0),
            "critical_count": int(irep.critical_count or 0),
            "unknown_count": int(irep.unknown_count or 0),
            "not_evaluated_count": int(irep.not_evaluated_count or 0),
            "collection_failed_count": int(irep.collection_failed_count or 0),
            "missing_result_count": int(irep.missing_result_count or 0),
            "summary": irep.summary or {},
            "generated_at": irep.generated_at,
            "created_at": irep.created_at,
        }
