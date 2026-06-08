from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dbops_assets import (
    AssetChangeProposal,
    AssetEndpoint,
    CollectorCheckDefinition,
    CollectorRun,
    CollectorRunItem,
    CollectorRunResult,
    DbInstance,
    DbType,
    Server,
)
from app.schemas.collector import (
    AssetVerifyLaunchRequest,
    CollectorCallbackItem,
    CollectorCallbackRequest,
    CollectorEndpointResponse,
    CollectorRunCreateRequest,
    CollectorRunCreateResponse,
    CollectorRunItemResponse,
    CollectorRunResponse,
    CollectorRunResultResponse,
)
from app.services.asset_event_history_service import record_event
from app.services.awx_service import AwxService, AwxServiceError


class CollectorService:
    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    @staticmethod
    def _validate_port(port: int | None) -> int:
        if port is None:
            raise ValueError("端口不能为空")
        if port < 1 or port > 65535:
            raise ValueError("端口范围必须在 1~65535")
        return int(port)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _build_run_id(scope_target: str, first_asset_id: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"COLLECT-{timestamp}-{scope_target}-{first_asset_id}"

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
    def _get_server(db: Session, server_id: int) -> Server:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise LookupError("服务器不存在")
        return server

    @staticmethod
    def _check_definition_defaults(check_code: str) -> dict[str, Any]:
        defaults = {
            "DB_PORT_REACHABILITY": {
                "check_name": "数据库端口连通性校验",
                "target_scope": "db_instance",
                "task_type": "PORT_CHECK",
                "default_timeout_seconds": 5,
            },
            "SSH_PORT_REACHABILITY": {
                "check_name": "SSH 端口连通性校验",
                "target_scope": "server",
                "task_type": "PORT_CHECK",
                "default_timeout_seconds": 5,
            },
        }
        return defaults.get(
            check_code,
            {
                "check_name": check_code,
                "target_scope": "db_instance",
                "task_type": "PORT_CHECK",
                "default_timeout_seconds": 5,
            },
        )

    @staticmethod
    def _get_check_definition(db: Session, check_code: str) -> dict[str, Any]:
        row = db.query(CollectorCheckDefinition).filter(CollectorCheckDefinition.check_code == check_code).first()
        if row:
            return {
                "check_code": row.check_code,
                "check_name": row.check_name,
                "target_scope": row.target_scope,
                "task_type": row.task_type,
                "default_timeout_seconds": row.default_timeout_seconds or 5,
                "config": row.config or {},
            }

        defaults = CollectorService._check_definition_defaults(check_code)
        defaults["check_code"] = check_code
        defaults["config"] = {}
        return defaults

    @staticmethod
    def _make_item_key(target_scope: str, asset_id: int, check_code: str, target_host: str, target_port: int) -> str:
        return f"{target_scope}:{asset_id}:{check_code}:{target_host}:{target_port}"

    @staticmethod
    def _normalize_check_codes(check_codes: list[str]) -> list[str]:
        normalized: list[str] = []
        for code in check_codes:
            cleaned = (code or "").strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        if not normalized:
            raise ValueError("check_codes 不能为空")
        return normalized

    @staticmethod
    def _build_item(
        db: Session,
        *,
        run_id: str,
        scope_target: str,
        asset_id: int,
        check_code: str,
        options: dict[str, Any],
    ) -> tuple[CollectorRunItem, dict[str, Any]]:
        check_def = CollectorService._get_check_definition(db, check_code)
        timeout_seconds = int(options.get("timeout_seconds") or check_def.get("default_timeout_seconds") or 5)

        if scope_target == "db_instance":
            instance, server, db_type = CollectorService._get_instance_context(db, asset_id)
            if check_code == "DB_PORT_REACHABILITY":
                target_scope = "db_instance"
                target_host = str(options.get("target_host") or server.ip_address)
                target_port = CollectorService._validate_port(options.get("target_port") or instance.port)
                asset_name = instance.instance_name
                related_db_instance_id = int(instance.id)
                related_server_id = int(server.id)
                asset_type = "db_instance"
            elif check_code == "SSH_PORT_REACHABILITY":
                target_scope = "server"
                target_host = str(options.get("target_host") or server.ip_address)
                target_port = CollectorService._validate_port(options.get("ssh_port") or getattr(get_settings(), "SSH_PORT", 22))
                asset_name = server.hostname or server.server_code
                related_db_instance_id = int(instance.id)
                related_server_id = int(server.id)
                asset_type = "server"
            else:
                raise ValueError(f"不支持的 check_code: {check_code}")

            item_key = CollectorService._make_item_key(target_scope, asset_id if target_scope == "db_instance" else server.id, check_code, target_host, target_port)
            item = CollectorRunItem(
                run_id=run_id,
                item_key=item_key,
                check_code=check_code,
                target_scope=target_scope,
                db_instance_id=related_db_instance_id,
                server_id=related_server_id,
                target_host=target_host,
                target_port=target_port,
                timeout_seconds=timeout_seconds,
                status="pending",
            )
            extra = {
                "item_key": item_key,
                "check_code": check_code,
                "task_type": check_def["task_type"],
                "target_scope": target_scope,
                "asset_id": related_db_instance_id if target_scope == "db_instance" else related_server_id,
                "asset_name": asset_name,
                "db_type": db_type.type_code,
                "target_host": target_host,
                "target_port": target_port,
                "timeout_seconds": timeout_seconds,
                "protocol": "tcp",
            }
            return item, extra

        if scope_target == "server":
            server = CollectorService._get_server(db, asset_id)
            if check_code != "SSH_PORT_REACHABILITY":
                raise ValueError(f"服务器 scope 暂不支持 check_code: {check_code}")
            target_scope = "server"
            target_host = str(options.get("target_host") or server.ip_address)
            target_port = CollectorService._validate_port(options.get("ssh_port") or getattr(get_settings(), "SSH_PORT", 22))
            item_key = CollectorService._make_item_key(target_scope, server.id, check_code, target_host, target_port)
            item = CollectorRunItem(
                run_id=run_id,
                item_key=item_key,
                check_code=check_code,
                target_scope=target_scope,
                server_id=int(server.id),
                target_host=target_host,
                target_port=target_port,
                timeout_seconds=timeout_seconds,
                status="pending",
            )
            extra = {
                "item_key": item_key,
                "check_code": check_code,
                "task_type": check_def["task_type"],
                "target_scope": target_scope,
                "asset_id": int(server.id),
                "asset_name": server.hostname or server.server_code,
                "target_host": target_host,
                "target_port": target_port,
                "timeout_seconds": timeout_seconds,
                "protocol": "tcp",
            }
            return item, extra

        raise ValueError(f"不支持的 scope.target_scope: {scope_target}")

    @staticmethod
    def launch_collector_run(
        db: Session,
        *,
        payload: CollectorRunCreateRequest,
        requested_by: str | None,
        request_base_url: str | None = None,
    ) -> dict[str, Any]:
        check_codes = CollectorService._normalize_check_codes(payload.check_codes)
        asset_ids = [int(asset_id) for asset_id in payload.scope.asset_ids]
        if not asset_ids:
            raise ValueError("asset_ids 不能为空")

        run_id = CollectorService._build_run_id(payload.scope.target_scope, asset_ids[0])
        callback_url = CollectorService._resolve_callback_url(request_base_url)

        run = CollectorRun(
            run_id=run_id,
            target_scope=payload.scope.target_scope,
            status="pending",
            requested_by=requested_by,
            callback_url=callback_url,
            request_payload=payload.model_dump(mode="json"),
            extra_vars={"schema_version": 1, "run_id": run_id, "callback_url": callback_url, "items": []},
            item_count=0,
        )
        db.add(run)
        db.flush()

        items: list[CollectorRunItem] = []
        extra_items: list[dict[str, Any]] = []
        seen_server_ids: set[int] = set()
        seen_db_instance_ids: set[int] = set()
        for asset_id in asset_ids:
            for check_code in check_codes:
                item, extra = CollectorService._build_item(
                    db,
                    run_id=run_id,
                    scope_target=payload.scope.target_scope,
                    asset_id=asset_id,
                    check_code=check_code,
                    options=payload.options,
                )
                item.collector_run_id = int(run.id)
                items.append(item)
                extra_items.append(extra)
                if item.server_id is not None:
                    seen_server_ids.add(int(item.server_id))
                if item.db_instance_id is not None:
                    seen_db_instance_ids.add(int(item.db_instance_id))

        run.item_count = len(items)
        if seen_db_instance_ids and len(seen_db_instance_ids) == 1:
            run.db_instance_id = next(iter(seen_db_instance_ids))
        if seen_server_ids and len(seen_server_ids) == 1:
            run.server_id = next(iter(seen_server_ids))
        run.target_scope = payload.scope.target_scope if len({item.target_scope for item in items}) == 1 else "mixed"
        run.extra_vars = {"schema_version": 1, "run_id": run_id, "callback_url": callback_url, "items": extra_items}
        if extra_items:
            run.target_host = extra_items[0]["target_host"]
            run.target_port = extra_items[0]["target_port"]

        for item in items:
            db.add(item)
        db.commit()
        db.refresh(run)

        try:
            launch_result = AwxService.launch_job(extra_vars=run.extra_vars)
        except AwxServiceError as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = CollectorService._now()
            db.commit()
            raise RuntimeError(str(exc)) from exc

        run.status = "launched"
        run.awx_job_id = launch_result.get("awx_job_id")
        run.awx_job_url = launch_result.get("awx_job_url")
        run.awx_job_template_id = launch_result.get("awx_job_template_id")
        run.awx_job_template_name = launch_result.get("awx_job_template_name")
        run.started_at = CollectorService._now()
        run.error_message = None
        db.commit()
        db.refresh(run)

        return {
            "detail": "launched",
            "run_id": run.run_id,
            "collector_run_id": int(run.id),
            "awx_job_id": run.awx_job_id,
            "awx_job_url": run.awx_job_url,
            "status": run.status,
            "item_count": run.item_count,
        }

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

        run_payload = CollectorRunCreateRequest(
            scope={"target_scope": "db_instance", "asset_ids": [int(instance.id)]},
            check_codes=["DB_PORT_REACHABILITY"],
            options={
                "timeout_seconds": payload.check_timeout,
                "target_host": target_host,
                "target_port": target_port,
                "db_type": db_type.type_code,
            },
        )
        return CollectorService.launch_collector_run(
            db,
            payload=run_payload,
            requested_by=requested_by,
            request_base_url=request_base_url,
        )

    @staticmethod
    def _result_to_dict(result: CollectorRunResult) -> dict[str, Any]:
        return {
            "run_id": result.run_id,
            "item_key": result.item_key,
            "check_code": result.check_code,
            "target_scope": result.target_scope,
            "status": result.status,
            "port_reachable": result.port_reachable,
            "target_host": result.target_host,
            "target_port": result.target_port,
            "error_message": result.error_message,
            "result_message": result.result_message,
            "awx_job_id": result.awx_job_id,
            "checked_by": result.checked_by,
            "checked_at": result.checked_at,
            "raw_result": result.raw_result or {},
            "created_at": result.created_at,
            "updated_at": result.updated_at,
        }

    @staticmethod
    def _item_to_dict(item: CollectorRunItem) -> dict[str, Any]:
        return {
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
            "timeout_seconds": item.timeout_seconds,
            "status": item.status,
            "result_status": item.result_status,
            "result_message": item.result_message,
            "raw_result": item.raw_result or {},
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _endpoint_to_dict(endpoint: AssetEndpoint) -> dict[str, Any]:
        return {
            "id": int(endpoint.id),
            "entity_type": endpoint.entity_type,
            "entity_id": int(endpoint.entity_id),
            "endpoint_type": endpoint.endpoint_type,
            "host": endpoint.host,
            "port": endpoint.port,
            "protocol": endpoint.protocol,
            "source": endpoint.source,
            "expected": endpoint.expected,
            "status": endpoint.status,
            "last_seen_at": endpoint.last_seen_at,
            "last_verify_at": endpoint.last_verify_at,
            "last_run_id": endpoint.last_run_id,
            "last_message": endpoint.last_message,
            "evidence": endpoint.evidence or {},
            "created_at": endpoint.created_at,
            "updated_at": endpoint.updated_at,
        }

    @staticmethod
    def _to_run_dict(run: CollectorRun, result: CollectorRunResult | None = None, items: list[CollectorRunItem] | None = None) -> dict[str, Any]:
        latest_result = CollectorService._result_to_dict(result) if result is not None else None
        run_items = [CollectorService._item_to_dict(item) for item in (items or [])]
        return {
            "id": int(run.id),
            "run_id": run.run_id,
            "target_scope": run.target_scope,
            "instance_id": int(run.db_instance_id) if run.db_instance_id is not None else None,
            "server_id": int(run.server_id) if run.server_id is not None else None,
            "job_type": run.job_type,
            "status": run.status,
            "item_count": run.item_count or 0,
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
            "items": run_items,
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
        items = db.query(CollectorRunItem).filter(CollectorRunItem.run_id == run_id).all()
        items = sorted(items, key=lambda row: (row.created_at or datetime.min, row.id or 0))
        return CollectorService._to_run_dict(run, result, items)

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
        item_map: dict[str, list[CollectorRunItem]] = {}
        if run_ids:
            results = (
                db.query(CollectorRunResult)
                .filter(CollectorRunResult.run_id.in_(run_ids))
                .order_by(CollectorRunResult.id.desc())
                .all()
            )
            for row in results:
                result_map.setdefault(row.run_id, row)

            items = db.query(CollectorRunItem).filter(CollectorRunItem.run_id.in_(run_ids)).all()
            for item in items:
                item_map.setdefault(item.run_id, []).append(item)

        return [CollectorService._to_run_dict(row, result_map.get(row.run_id), item_map.get(row.run_id)) for row in rows]

    @staticmethod
    def list_server_runs(db: Session, *, server_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rows = (
            db.query(CollectorRun)
            .filter(CollectorRun.server_id == server_id)
            .order_by(CollectorRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [CollectorService._to_run_dict(row) for row in rows]

    @staticmethod
    def list_run_items(db: Session, *, run_id: str) -> list[dict[str, Any]]:
        rows = (
            db.query(CollectorRunItem)
            .filter(CollectorRunItem.run_id == run_id)
            .order_by(CollectorRunItem.created_at.asc())
            .all()
        )
        return [CollectorService._item_to_dict(row) for row in rows]

    @staticmethod
    def list_endpoints(db: Session, *, entity_type: str | None = None, entity_id: int | None = None) -> list[dict[str, Any]]:
        query = db.query(AssetEndpoint)
        if entity_type:
            query = query.filter(AssetEndpoint.entity_type == entity_type)
        if entity_id is not None:
            query = query.filter(AssetEndpoint.entity_id == entity_id)
        rows = query.order_by(AssetEndpoint.updated_at.desc()).all()
        return [CollectorService._endpoint_to_dict(row) for row in rows]

    @staticmethod
    def _callback_items(payload: CollectorCallbackRequest, run: CollectorRun) -> list[CollectorCallbackItem]:
        if payload.items:
            return payload.items

        if payload.target_host is None or payload.target_port is None or payload.status is None or payload.asset_id is None:
            raise ValueError("callback payload 缺少 items 或旧协议必要字段")

        fallback_target_scope = payload.target_scope or ("db_instance" if run.db_instance_id == payload.asset_id else "server")
        return [
            CollectorCallbackItem(
                item_key=CollectorService._make_item_key(
                    fallback_target_scope,
                    int(payload.asset_id),
                    payload.check_type or "PORT_REACHABILITY",
                    payload.target_host,
                    int(payload.target_port),
                ),
                check_code=payload.check_type or "PORT_REACHABILITY",
                target_scope=fallback_target_scope,
                asset_id=int(payload.asset_id),
                target_host=payload.target_host,
                target_port=int(payload.target_port),
                status=payload.status,
                reachable=payload.port_reachable,
                message=payload.error_message,
                raw_result={},
            )
        ]

    @staticmethod
    def _map_item_status(status: str) -> tuple[str, str | None]:
        if status == "verified":
            return "success", "verified"
        if status == "collected":
            return "success", "collected"
        if status == "missing":
            return "failed", "missing"
        if status == "drifted":
            return "failed", "drifted"
        if status == "failed":
            return "failed", "failed"
        return "success", status

    @staticmethod
    def _endpoint_status(status: str) -> str:
        if status in {"verified", "collected"}:
            return "online"
        if status in {"missing", "failed"}:
            return "offline"
        if status == "drifted":
            return "drifted"
        return "unknown"

    @staticmethod
    def _upsert_endpoint(
        db: Session,
        *,
        entity_type: str,
        entity_id: int,
        host: str,
        port: int,
        run_id: str,
        status: str,
        evidence: dict[str, Any],
        source: str = "cmdb",
    ) -> AssetEndpoint:
        endpoint = (
            db.query(AssetEndpoint)
            .filter(
                AssetEndpoint.entity_type == entity_type,
                AssetEndpoint.entity_id == entity_id,
                AssetEndpoint.endpoint_type == "port",
                AssetEndpoint.host == host,
                AssetEndpoint.port == port,
                AssetEndpoint.source == source,
            )
            .first()
        )
        if endpoint is None:
            endpoint = AssetEndpoint(
                entity_type=entity_type,
                entity_id=entity_id,
                endpoint_type="port",
                host=host,
                port=port,
                source=source,
            )
            db.add(endpoint)

        endpoint.expected = source == "cmdb"
        endpoint.status = CollectorService._endpoint_status(status)
        endpoint.last_run_id = run_id
        endpoint.last_message = evidence.get("message") or evidence.get("error_message")
        endpoint.last_verify_at = CollectorService._now()
        endpoint.last_seen_at = CollectorService._now() if endpoint.status == "online" else endpoint.last_seen_at
        endpoint.evidence = evidence
        return endpoint

    @staticmethod
    def _maybe_create_change_proposal(
        db: Session,
        *,
        entity_type: str,
        entity_id: int,
        run_id: str,
        old_value: dict[str, Any],
        new_value: dict[str, Any],
        evidence: dict[str, Any],
    ) -> AssetChangeProposal:
        proposal = AssetChangeProposal(
            entity_type=entity_type,
            entity_id=entity_id,
            change_type="DB_PORT_DRIFT",
            old_value=old_value,
            new_value=new_value,
            evidence_run_id=run_id,
            evidence=evidence,
            status="pending",
        )
        db.add(proposal)
        return proposal

    @staticmethod
    def _build_callback_items(payload: CollectorCallbackRequest, run: CollectorRun) -> list[CollectorCallbackItem]:
        return CollectorService._callback_items(payload, run)

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

        callback_items = CollectorService._build_callback_items(payload, run)
        processed_count = 0

        for callback_item in callback_items:
            run_item = (
                db.query(CollectorRunItem)
                .filter(
                    CollectorRunItem.run_id == payload.run_id,
                    CollectorRunItem.item_key == callback_item.item_key,
                )
                .with_for_update()
                .first()
            )
            if run_item is None:
                raise LookupError(f"item_key 不存在: {callback_item.item_key}")

            expected_asset_id = run_item.db_instance_id if run_item.target_scope == "db_instance" else run_item.server_id
            if expected_asset_id is None:
                expected_asset_id = callback_item.asset_id
            if int(callback_item.asset_id) != int(expected_asset_id):
                raise ValueError("asset_id 与 item 记录不匹配")
            if callback_item.target_scope != run_item.target_scope:
                raise ValueError("target_scope 与 item 记录不匹配")

            result_status = callback_item.status
            run_item.status, run_item.result_status = CollectorService._map_item_status(result_status)
            run_item.result_message = callback_item.message
            run_item.raw_result = callback_item.raw_result or {}
            run_item.finished_at = now
            if run_item.started_at is None:
                run_item.started_at = now

            result = (
                db.query(CollectorRunResult)
                .filter(
                    CollectorRunResult.collector_run_id == run.id,
                    CollectorRunResult.item_key == callback_item.item_key,
                )
                .first()
            )
            if result is None:
                result = CollectorRunResult(
                    collector_run_id=run.id,
                    run_id=run.run_id,
                    collector_run_item_id=run_item.id,
                    item_key=callback_item.item_key,
                    check_code=run_item.check_code,
                    target_scope=run_item.target_scope,
                    db_instance_id=run_item.db_instance_id,
                    server_id=run_item.server_id,
                    check_type=run_item.check_code,
                    target_host=callback_item.target_host,
                    target_port=callback_item.target_port,
                )
                db.add(result)
            else:
                result.collector_run_item_id = run_item.id

            _, result_status_name = CollectorService._map_item_status(callback_item.status)
            result.status = result_status_name or callback_item.status
            result.port_reachable = callback_item.reachable
            result.target_host = callback_item.target_host
            result.target_port = callback_item.target_port
            result.error_message = callback_item.message
            result.result_message = callback_item.message
            result.awx_job_id = payload.awx_job_id
            result.checked_by = payload.checked_by
            result.checked_at = payload.checked_at or now
            result.raw_result = callback_item.raw_result or {}
            result.updated_at = now

            endpoint = CollectorService._upsert_endpoint(
                db,
                entity_type=run_item.target_scope,
                entity_id=int(callback_item.asset_id),
                host=callback_item.target_host,
                port=callback_item.target_port,
                run_id=run.run_id,
                status=callback_item.status,
                evidence={
                    "item_key": callback_item.item_key,
                    "check_code": callback_item.check_code,
                    "message": callback_item.message,
                    "raw_result": callback_item.raw_result or {},
                },
            )

            if run_item.target_scope == "db_instance" and run_item.db_instance_id is not None:
                instance = (
                    db.query(DbInstance)
                    .filter(DbInstance.id == run_item.db_instance_id)
                    .with_for_update()
                    .first()
                )
                if instance is None:
                    raise LookupError("run 关联实例不存在")

                before_status = instance.trust_status
                before_reachability = instance.reachability_status
                if callback_item.status == "verified":
                    instance.trust_status = "verified"
                    instance.reachability_status = "online"
                    instance.last_seen_at = now
                    instance.verify_message = callback_item.message or "PORT_REACHABILITY_OK"
                elif callback_item.status == "missing":
                    instance.trust_status = "missing"
                    instance.reachability_status = "offline"
                    instance.verify_message = callback_item.message or "PORT_REACHABILITY_FAILED"
                elif callback_item.status == "drifted":
                    instance.trust_status = "drifted"
                    instance.reachability_status = "unknown"
                    instance.verify_message = callback_item.message or "ASSET_DRIFT_DETECTED"
                else:
                    instance.verify_message = callback_item.message or callback_item.status
                instance.last_verify_at = now
                instance.last_verify_run_id = run.run_id
                instance.last_awx_job_id = payload.awx_job_id
                instance.verify_detail = {
                    "item_key": callback_item.item_key,
                    "check_code": callback_item.check_code,
                    "status": callback_item.status,
                    "target_host": callback_item.target_host,
                    "target_port": callback_item.target_port,
                    "raw_result": callback_item.raw_result or {},
                }

                if before_status != instance.trust_status or before_reachability != instance.reachability_status:
                    event_type = "ASSET_VERIFY_SUCCESS"
                    if callback_item.status == "missing":
                        event_type = "ASSET_VERIFY_FAILED"
                    elif callback_item.status == "drifted":
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
                            "item_key": callback_item.item_key,
                            "awx_job_id": payload.awx_job_id,
                            "target_host": callback_item.target_host,
                            "target_port": callback_item.target_port,
                        },
                        reason=callback_item.message,
                        operator=payload.checked_by or "awx",
                    )

                if callback_item.status == "drifted":
                    CollectorService._maybe_create_change_proposal(
                        db,
                        entity_type="db_instance",
                        entity_id=int(instance.id),
                        run_id=run.run_id,
                        old_value={"port": instance.port},
                        new_value={"port": callback_item.target_port},
                        evidence=callback_item.raw_result or {},
                    )

            elif run_item.target_scope == "server" and run_item.server_id is not None:
                server = db.query(Server).filter(Server.id == run_item.server_id).with_for_update().first()
                if server is None:
                    raise LookupError("run 关联服务器不存在")
                record_event(
                    db,
                    asset_type="server",
                    asset_id=int(server.id),
                    event_type="SERVER_PORT_CHECK",
                    before_status=None,
                    after_status=endpoint.status,
                    changed_fields={
                        "run_id": run.run_id,
                        "item_key": callback_item.item_key,
                        "check_code": callback_item.check_code,
                        "endpoint_status": endpoint.status,
                        "target_host": callback_item.target_host,
                        "target_port": callback_item.target_port,
                    },
                    reason=callback_item.message,
                    operator=payload.checked_by or "awx",
                )

            processed_count += 1

        run.status = CollectorService._summarize_run_status(
            db.query(CollectorRunItem).filter(CollectorRunItem.run_id == run.run_id).all()
        )
        run.error_message = None
        run.awx_job_id = payload.awx_job_id or run.awx_job_id
        if run.started_at is None:
            run.started_at = now
        run.finished_at = now
        db.commit()

        return {
            "detail": "ok",
            "run_id": payload.run_id,
            "status": run.status,
            "item_count": processed_count,
        }

    @staticmethod
    def _summarize_run_status(items: list[CollectorRunItem]) -> str:
        if not items:
            return "failed"
        statuses = [item.status for item in items]
        if all(status == "success" for status in statuses):
            return "success"
        if any(status == "success" for status in statuses) and any(status in {"failed", "timeout"} for status in statuses):
            return "partial_success"
        if any(status == "success" for status in statuses):
            return "partial_success"
        return "failed"
