from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dbops_assets import CollectorRun, CollectorRunResult, DbInstance, DbType, Server
from app.schemas.collector import AssetVerifyLaunchRequest, CollectorCallbackRequest
from app.services.asset_event_history_service import record_event
from app.services.awx_service import AwxService, AwxServiceError


class CollectorService:
    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    @staticmethod
    def _validate_port(port: int | None) -> int:
        if port is None:
            raise ValueError("实例端口为空，无法发起校验")
        if port < 1 or port > 65535:
            raise ValueError("端口范围必须在 1~65535")
        return int(port)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _build_run_id(instance_id: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"VERIFY-{timestamp}-{instance_id}"

    @staticmethod
    def _resolve_callback_url(request_base_url: str | None = None) -> str:
        configured_url = get_settings().COLLECTOR_CALLBACK_URL.strip()
        if configured_url:
            return configured_url

        if request_base_url:
            base_url = request_base_url.strip().rstrip("/")
            if base_url:
                return f"{base_url}/api/v1/collector/callback/"

        raise ValueError("COLLECTOR_CALLBACK_URL 未配置")

    @staticmethod
    def _get_instance_context(db: Session, instance_id: int) -> tuple[DbInstance, Server, DbType]:
        instance = db.query(DbInstance).filter(DbInstance.id == instance_id).first()
        if not instance:
            raise LookupError("实例不存在")

        server = db.query(Server).filter(Server.id == instance.server_id).first()
        if not server:
            raise ValueError("实例未关联服务器")

        db_type = db.query(DbType).filter(DbType.id == instance.db_type_id).first()
        if not db_type:
            raise ValueError("实例未关联数据库类型")

        return instance, server, db_type

    @staticmethod
    def launch_asset_verify(
        db: Session,
        *,
        instance_id: int,
        payload: AssetVerifyLaunchRequest,
        requested_by: str | None,
        request_base_url: str | None = None,
    ) -> dict[str, Any]:
        instance, server, db_type = CollectorService._get_instance_context(db, instance_id)

        target_host = (payload.target_host_override or str(server.ip_address)).strip()
        if not target_host:
            raise ValueError("目标主机不能为空")

        target_port = payload.target_port_override if payload.target_port_override is not None else instance.port
        target_port = CollectorService._validate_port(target_port)

        callback_url = CollectorService._resolve_callback_url(request_base_url)

        run_id = CollectorService._build_run_id(instance_id)
        extra_vars = {
            "run_id": run_id,
            "asset_id": int(instance.id),
            "asset_name": instance.instance_name,
            "db_type": db_type.type_code,
            "target_host": target_host,
            "target_port": target_port,
            "check_timeout": payload.check_timeout,
            "callback_url": callback_url,
        }
        request_payload = payload.model_dump(mode="json")

        collector_run = CollectorRun(
            run_id=run_id,
            db_instance_id=instance.id,
            status="pending",
            target_host=target_host,
            target_port=target_port,
            callback_url=callback_url,
            requested_by=requested_by,
            request_payload=request_payload,
            extra_vars=extra_vars,
        )
        db.add(collector_run)
        db.commit()
        db.refresh(collector_run)

        try:
            launch_result = AwxService.launch_verify_job(extra_vars=extra_vars)
        except AwxServiceError as exc:
            collector_run.status = "failed"
            collector_run.error_message = str(exc)
            collector_run.finished_at = CollectorService._now()
            db.commit()
            raise RuntimeError(str(exc)) from exc

        collector_run.status = "launched"
        collector_run.awx_job_id = launch_result.get("awx_job_id")
        collector_run.awx_job_url = launch_result.get("awx_job_url")
        collector_run.awx_job_template_id = launch_result.get("awx_job_template_id")
        collector_run.awx_job_template_name = launch_result.get("awx_job_template_name")
        collector_run.started_at = CollectorService._now()
        collector_run.error_message = None
        db.commit()
        db.refresh(collector_run)

        return {
            "detail": "launched",
            "run_id": collector_run.run_id,
            "collector_run_id": int(collector_run.id),
            "instance_id": int(instance.id),
            "awx_job_id": collector_run.awx_job_id,
            "awx_job_url": collector_run.awx_job_url,
            "status": collector_run.status,
        }

    @staticmethod
    def _map_verify_message(status: str, error_message: str | None) -> tuple[str, str]:
        cleaned_error = (error_message or "").strip()
        if status == "verified":
            return "online", "PORT_REACHABILITY_OK"
        if status == "missing":
            return "offline", cleaned_error or "PORT_REACHABILITY_FAILED"
        return "unknown", cleaned_error or "ASSET_DRIFT_DETECTED"

    @staticmethod
    def _to_run_dict(run: CollectorRun, result: CollectorRunResult | None = None) -> dict[str, Any]:
        latest_result = None
        if result is not None:
            latest_result = {
                "run_id": result.run_id,
                "check_type": result.check_type,
                "status": result.status,
                "port_reachable": result.port_reachable,
                "target_host": result.target_host,
                "target_port": result.target_port,
                "error_message": result.error_message,
                "awx_job_id": result.awx_job_id,
                "checked_by": result.checked_by,
                "checked_at": result.checked_at,
                "raw_result": result.raw_result or {},
                "created_at": result.created_at,
            }
        return {
            "id": int(run.id),
            "run_id": run.run_id,
            "instance_id": int(run.db_instance_id),
            "job_type": run.job_type,
            "status": run.status,
            "awx_job_id": run.awx_job_id,
            "awx_job_url": run.awx_job_url,
            "awx_job_template_id": run.awx_job_template_id,
            "awx_job_template_name": run.awx_job_template_name,
            "target_host": run.target_host,
            "target_port": run.target_port,
            "callback_url": run.callback_url,
            "requested_by": run.requested_by,
            "request_payload": run.request_payload or {},
            "extra_vars": run.extra_vars or {},
            "error_message": run.error_message,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "latest_result": latest_result,
        }

    @staticmethod
    def get_run(db: Session, *, run_id: str) -> dict[str, Any]:
        run = db.query(CollectorRun).filter(CollectorRun.run_id == run_id).first()
        if not run:
            raise LookupError("run_id 不存在")
        result = (
            db.query(CollectorRunResult)
            .filter(CollectorRunResult.run_id == run_id)
            .order_by(CollectorRunResult.id.desc())
            .first()
        )
        return CollectorService._to_run_dict(run, result)

    @staticmethod
    def list_instance_runs(db: Session, *, instance_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rows = (
            db.query(CollectorRun)
            .filter(CollectorRun.db_instance_id == instance_id)
            .order_by(CollectorRun.created_at.desc())
            .limit(limit)
            .all()
        )
        run_ids = [row.run_id for row in rows]
        result_map: dict[str, CollectorRunResult] = {}
        if run_ids:
            results = (
                db.query(CollectorRunResult)
                .filter(CollectorRunResult.run_id.in_(run_ids))
                .order_by(CollectorRunResult.id.desc())
                .all()
            )
            for row in results:
                result_map.setdefault(row.run_id, row)
        return [CollectorService._to_run_dict(row, result_map.get(row.run_id)) for row in rows]

    @staticmethod
    def handle_callback(db: Session, *, payload: CollectorCallbackRequest) -> dict[str, Any]:
        now = CollectorService._now()
        run = (
            db.query(CollectorRun)
            .filter(CollectorRun.run_id == payload.run_id)
            .with_for_update()
            .first()
        )
        if not run:
            raise LookupError("run_id 不存在")
        if int(payload.asset_id) != int(run.db_instance_id):
            run.status = "callback_failed"
            run.error_message = "callback asset_id 与 run 不一致"
            run.finished_at = now
            db.commit()
            raise ValueError("asset_id 与 run_id 不匹配")

        instance = (
            db.query(DbInstance)
            .filter(DbInstance.id == run.db_instance_id)
            .with_for_update()
            .first()
        )
        if not instance:
            run.status = "callback_failed"
            run.error_message = "run 关联实例不存在"
            run.finished_at = now
            db.commit()
            raise LookupError("run 关联实例不存在")

        reachability_status, verify_message = CollectorService._map_verify_message(payload.status, payload.error_message)
        parsed_awx_job_id = CollectorService._to_int(payload.awx_job_id) or run.awx_job_id
        raw_payload = payload.model_dump(mode="json")

        result = (
            db.query(CollectorRunResult)
            .filter(
                CollectorRunResult.run_id == payload.run_id,
                CollectorRunResult.check_type == payload.check_type,
            )
            .first()
        )
        if result is None:
            result = CollectorRunResult(
                collector_run_id=run.id,
                run_id=payload.run_id,
                db_instance_id=run.db_instance_id,
                check_type=payload.check_type,
            )
            db.add(result)

        result.status = payload.status
        result.port_reachable = payload.port_reachable
        result.target_host = payload.target_host
        result.target_port = payload.target_port
        result.error_message = payload.error_message
        result.awx_job_id = parsed_awx_job_id
        result.checked_by = payload.checked_by
        result.checked_at = payload.checked_at or now
        result.raw_result = raw_payload

        run.status = "success"
        run.error_message = payload.error_message or None
        run.awx_job_id = parsed_awx_job_id
        if run.started_at is None:
            run.started_at = now
        run.finished_at = now

        # 仅让更“新”的 run 覆盖实例态，避免旧回调回写污染新状态。
        should_overwrite_instance = True
        if (
            instance.last_verify_at is not None
            and run.started_at is not None
            and run.started_at < instance.last_verify_at
            and instance.last_verify_run_id != run.run_id
        ):
            should_overwrite_instance = False

        if should_overwrite_instance:
            before_status = instance.trust_status
            instance.trust_status = payload.status
            instance.reachability_status = reachability_status
            if payload.status == "verified":
                instance.last_seen_at = now
            instance.last_verify_at = now
            instance.verify_message = verify_message
            instance.last_verify_run_id = run.run_id
            instance.last_awx_job_id = parsed_awx_job_id
            instance.verify_detail = raw_payload

            event_type = "ASSET_VERIFY_SUCCESS"
            if payload.status == "missing":
                event_type = "ASSET_VERIFY_FAILED"
            elif payload.status == "drifted":
                event_type = "ASSET_DRIFT_DETECTED"
            record_event(
                db,
                asset_type="db_instance",
                asset_id=int(instance.id),
                event_type=event_type,
                before_status=before_status,
                after_status=instance.trust_status,
                changed_fields={
                    "trust_status": instance.trust_status,
                    "reachability_status": instance.reachability_status,
                    "run_id": run.run_id,
                    "awx_job_id": parsed_awx_job_id,
                    "target_host": payload.target_host,
                    "target_port": payload.target_port,
                },
                reason=verify_message,
                operator=payload.checked_by or "awx",
            )

        db.commit()

        return {
            "detail": "ok",
            "run_id": payload.run_id,
            "asset_id": int(instance.id),
            "status": payload.status,
        }
