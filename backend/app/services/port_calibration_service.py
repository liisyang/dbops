from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.dbops_assets import (
    AssetEndpoint,
    CollectorRun,
    CollectorRunItem,
    DbInstance,
    DbType,
    OsVersion,
    Server,
    StagingExcelImport,
)
from app.services.asset_event_history_service import record_event
from app.services.asset_proposal_service import AssetProposalService
from app.services.port_profile_service import PortProfileService


class PortCalibrationService:
    _SOURCE_PRIORITY = {
        "asset_endpoint": 0,
        "db_instance_port": 1,
        "server_extra_attrs": 2,
        "related_server": 2,
        "excel_import": 3,
        "default_profile": 4,
        "profile_candidate": 5,
        "unknown": 9,
    }

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= parsed <= 65535:
            return parsed
        return None

    @staticmethod
    def _source_priority(port_source: str | None) -> int:
        return PortCalibrationService._SOURCE_PRIORITY.get((port_source or "unknown").strip(), 9)

    @staticmethod
    def _is_specific_endpoint_type(endpoint_type: str | None) -> bool:
        cleaned = (endpoint_type or "").strip()
        return cleaned not in {"", "port", "DB_SERVICE_PORT", "OS_ADMIN_PORT", "CUSTOM_PORT"}

    @staticmethod
    def _normalize_endpoint_type(target_scope: str, endpoint_type: str | None, port_source: str | None) -> str:
        cleaned = (endpoint_type or "").strip()
        if cleaned and cleaned != "port":
            return cleaned
        if target_scope == "server":
            return "OS_ADMIN_PORT"
        if (port_source or "").strip() in {"server_extra_attrs", "related_server"}:
            return "OS_ADMIN_PORT"
        return "DB_SERVICE_PORT"

    @staticmethod
    def _candidate_score(candidate: dict[str, Any]) -> tuple[int, int]:
        return (
            0 if PortCalibrationService._is_specific_endpoint_type(candidate.get("endpoint_type")) else 1,
            PortCalibrationService._source_priority(candidate.get("port_source")),
        )

    @staticmethod
    def _is_service_endpoint_type(endpoint_type: str | None) -> bool:
        cleaned = (endpoint_type or "").strip()
        return cleaned not in {"", "LINUX_SSH", "WINDOWS_RDP", "OS_ADMIN_PORT"}

    @staticmethod
    def _merge_candidate(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        existing.setdefault("sources", []).extend(incoming.get("sources", []))
        existing["is_required"] = bool(existing.get("is_required")) or bool(incoming.get("is_required"))
        if PortCalibrationService._candidate_score(incoming) < PortCalibrationService._candidate_score(existing):
            for key in ("host", "endpoint_type", "port_source", "protocol"):
                if incoming.get(key) is not None:
                    existing[key] = incoming[key]
        if not existing.get("endpoint_type"):
            existing["endpoint_type"] = incoming.get("endpoint_type")
        if not existing.get("port_source"):
            existing["port_source"] = incoming.get("port_source")
        if not existing.get("protocol"):
            existing["protocol"] = incoming.get("protocol") or "tcp"
        return existing

    @staticmethod
    def _make_candidate(
        *,
        host: str,
        port: int,
        endpoint_type: str | None,
        protocol: str = "tcp",
        port_source: str = "unknown",
        is_required: bool = False,
        origin: str | None = None,
    ) -> dict[str, Any]:
        return {
            "host": host,
            "port": int(port),
            "protocol": protocol or "tcp",
            "endpoint_type": endpoint_type,
            "port_source": port_source,
            "is_required": bool(is_required),
            "sources": [
                {
                    "origin": origin or port_source,
                    "port_source": port_source,
                    "endpoint_type": endpoint_type,
                    "is_required": bool(is_required),
                }
            ],
        }

    @staticmethod
    def _add_candidate(candidate_map: dict[tuple[str, int, str], dict[str, Any]], candidate: dict[str, Any], target_scope: str) -> None:
        host = str(candidate.get("host") or "")
        port = int(candidate["port"])
        protocol = str(candidate.get("protocol") or "tcp")
        normalized = dict(candidate)
        normalized["host"] = host
        normalized["port"] = port
        normalized["protocol"] = protocol
        normalized["endpoint_type"] = PortCalibrationService._normalize_endpoint_type(
            target_scope,
            normalized.get("endpoint_type"),
            normalized.get("port_source"),
        )
        key = (host, port, protocol)
        if key in candidate_map:
            candidate_map[key] = PortCalibrationService._merge_candidate(candidate_map[key], normalized)
        else:
            candidate_map[key] = normalized

    @staticmethod
    def _normalize_os_family(server: Server, db: Session) -> str | None:
        extra = server.extra_attrs or {}
        explicit = (extra.get("os_family") or "").strip().lower()
        if explicit:
            return explicit

        os_name = ""
        if getattr(server, "os_version", None) is not None:
            os_name = str(getattr(server.os_version, "os_name", "") or "")
        if not os_name and server.os_version_id:
            os_row = db.query(OsVersion).filter(OsVersion.id == server.os_version_id).first()
            if os_row:
                os_name = str(os_row.os_name or "")

        normalized = os_name.strip().lower()
        if not normalized:
            return None
        if "win" in normalized:
            return "windows"
        if "linux" in normalized or "rhel" in normalized or "centos" in normalized:
            return "linux"
        return normalized

    @staticmethod
    def _resolve_db_type_code(instance: DbInstance, db: Session) -> str | None:
        if getattr(instance, "db_type", None) is not None and getattr(instance.db_type, "type_code", None):
            return str(instance.db_type.type_code)
        row = db.query(DbType).filter(DbType.id == instance.db_type_id).first()
        if row and row.type_code:
            return str(row.type_code)
        return None

    @staticmethod
    def _collect_extra_attrs_ports(extra_attrs: dict[str, Any], *, keys: list[str], source: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for key in keys:
            parsed = PortCalibrationService._to_int(extra_attrs.get(key))
            if parsed is None:
                continue
            candidates.append(
                {
                    "port": parsed,
                    "port_source": source,
                    "endpoint_type": None,
                    "protocol": "tcp",
                    "is_required": False,
                }
            )
        return candidates

    @staticmethod
    def _resolve_excel_port(instance: DbInstance, server: Server, db: Session) -> list[dict[str, Any]]:
        row = (
            db.query(StagingExcelImport)
            .filter(StagingExcelImport.instance_name == instance.instance_name, StagingExcelImport.ip == str(server.ip_address))
            .order_by(StagingExcelImport.imported_at.desc())
            .first()
        )
        if row is None:
            row = (
                db.query(StagingExcelImport)
                .filter(StagingExcelImport.instance_name == instance.instance_name)
                .order_by(StagingExcelImport.imported_at.desc())
                .first()
            )
        if row is None:
            return []
        parsed = PortCalibrationService._to_int(row.port)
        if parsed is None:
            return []
        return [
            {
                "port": parsed,
                "port_source": "excel_import",
                "endpoint_type": None,
                "protocol": "tcp",
                "is_required": False,
            }
        ]

    @staticmethod
    def _resolve_existing_endpoints(
        *,
        target_scope: str,
        asset_id: int,
        db: Session,
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(AssetEndpoint)
            .filter(AssetEndpoint.entity_type == target_scope, AssetEndpoint.entity_id == asset_id)
            .order_by(AssetEndpoint.updated_at.desc())
            .all()
        )
        return [
            {
                "host": str(row.host),
                "port": int(row.port),
                "port_source": "asset_endpoint",
                "endpoint_type": row.endpoint_type,
                "protocol": row.protocol or "tcp",
                "is_required": bool(row.is_required),
            }
            for row in rows
            if (row.endpoint_type or "").strip() and (row.endpoint_type or "").strip() != "port"
        ]

    @staticmethod
    def _profile_candidates(
        *,
        target_scope: str,
        db_type_code: str | None,
        os_family: str | None,
        db: Session,
    ) -> list[dict[str, Any]]:
        rows = PortProfileService.get_candidate_ports(
            db,
            target_scope=target_scope,
            db_type_code=db_type_code,
            os_family=os_family,
        )
        candidates: list[dict[str, Any]] = []
        for row in rows:
            candidates.append(
                {
                    "port": int(row["default_port"]),
                    "port_source": "default_profile" if row["is_required"] else "profile_candidate",
                    "endpoint_type": row["endpoint_type"],
                    "protocol": row["protocol"],
                    "is_required": bool(row["is_required"]),
                }
            )
        return candidates

    @staticmethod
    def _related_server_candidates(*, server: Server, db: Session, include_related_server: bool) -> list[dict[str, Any]]:
        if not include_related_server:
            return []

        host = str(server.ip_address)
        candidates: list[dict[str, Any]] = []
        candidates.extend(
            PortCalibrationService._resolve_existing_endpoints(
                target_scope="server",
                asset_id=int(server.id),
                db=db,
            )
        )
        candidates.extend(
            PortCalibrationService._collect_extra_attrs_ports(
                server.extra_attrs or {},
                keys=["ssh_port", "rdp_port", "admin_port", "management_port", "port"],
                source="related_server",
            )
        )
        os_family = PortCalibrationService._normalize_os_family(server, db)
        if os_family:
            candidates.extend(
                PortCalibrationService._profile_candidates(
                    target_scope="server",
                    db_type_code=None,
                    os_family=os_family,
                    db=db,
                )
            )
        for candidate in candidates:
            candidate["host"] = host
            candidate["port_source"] = candidate.get("port_source") or "related_server"
        return candidates

    @staticmethod
    def _collect_instance_candidates(
        db: Session,
        *,
        instance: DbInstance,
        server: Server,
        include_related_server: bool,
    ) -> tuple[str, dict[tuple[str, int, str], dict[str, Any]]]:
        host = str(server.ip_address)
        candidate_map: dict[tuple[str, int, str], dict[str, Any]] = {}

        for candidate in PortCalibrationService._resolve_existing_endpoints(
            target_scope="db_instance", asset_id=int(instance.id), db=db
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="db_instance")

        if instance.port is not None:
            PortCalibrationService._add_candidate(
                candidate_map,
                {
                    "host": host,
                    "port": int(instance.port),
                    "port_source": "db_instance_port",
                    "endpoint_type": "DB_SERVICE_PORT",
                    "protocol": "tcp",
                    "is_required": True,
                },
                target_scope="db_instance",
            )

        for candidate in PortCalibrationService._collect_extra_attrs_ports(
            server.extra_attrs or {},
            keys=["db_port", "listener_port", "service_port", "port"],
            source="server_extra_attrs",
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="db_instance")

        for candidate in PortCalibrationService._resolve_excel_port(instance, server, db):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="db_instance")

        db_type_code = PortCalibrationService._resolve_db_type_code(instance, db)
        os_family = PortCalibrationService._normalize_os_family(server, db)
        for candidate in PortCalibrationService._profile_candidates(
            target_scope="db_instance",
            db_type_code=db_type_code,
            os_family=os_family,
            db=db,
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="db_instance")

        for candidate in PortCalibrationService._related_server_candidates(
            server=server,
            db=db,
            include_related_server=include_related_server,
        ):
            candidate["target_scope"] = "db_instance"
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="db_instance")

        return host, candidate_map

    @staticmethod
    def _collect_server_candidates(
        db: Session,
        *,
        server: Server,
    ) -> tuple[str, dict[tuple[str, int, str], dict[str, Any]]]:
        host = str(server.ip_address)
        os_family = PortCalibrationService._normalize_os_family(server, db)
        candidate_map: dict[tuple[str, int, str], dict[str, Any]] = {}

        for candidate in PortCalibrationService._resolve_existing_endpoints(
            target_scope="server", asset_id=int(server.id), db=db
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="server")

        for candidate in PortCalibrationService._collect_extra_attrs_ports(
            server.extra_attrs or {},
            keys=["ssh_port", "rdp_port", "admin_port", "management_port", "port"],
            source="server_extra_attrs",
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="server")

        for candidate in PortCalibrationService._profile_candidates(
            target_scope="server",
            db_type_code=None,
            os_family=os_family,
            db=db,
        ):
            candidate["host"] = host
            PortCalibrationService._add_candidate(candidate_map, candidate, target_scope="server")

        return host, candidate_map

    @staticmethod
    def _sort_candidates(
        candidate_map: dict[tuple[str, int, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return sorted(
            candidate_map.values(),
            key=lambda row: (
                PortCalibrationService._candidate_score(row),
                int(row["port"]),
                str(row.get("endpoint_type") or ""),
            ),
        )

    @staticmethod
    def get_candidate_ports_for_asset(
        db: Session,
        *,
        target_scope: str,
        asset_id: int,
        include_related_server: bool = True,
    ) -> tuple[str, list[dict[str, Any]]]:
        if target_scope == "db_instance":
            instance = (
                db.query(DbInstance)
                .options(
                    joinedload(DbInstance.db_type),
                    joinedload(DbInstance.server).joinedload(Server.os_version),
                )
                .filter(DbInstance.id == asset_id)
                .first()
            )
            if instance is None:
                raise LookupError("实例不存在")
            # 优先使用 eager-loaded 关系；在测试/内存 session 中回退到显式查询
            server = instance.server if instance.server is not None else db.query(Server).filter(Server.id == instance.server_id).first()
            if server is None:
                raise ValueError("实例未关联服务器")

            host, candidate_map = PortCalibrationService._collect_instance_candidates(
                db,
                instance=instance,
                server=server,
                include_related_server=include_related_server,
            )
            return host, PortCalibrationService._sort_candidates(candidate_map)

        if target_scope == "server":
            server = (
                db.query(Server)
                .options(joinedload(Server.os_version))
                .filter(Server.id == asset_id)
                .first()
            )
            if server is None:
                raise LookupError("服务器不存在")

            host, candidate_map = PortCalibrationService._collect_server_candidates(
                db,
                server=server,
            )
            return host, PortCalibrationService._sort_candidates(candidate_map)

        raise ValueError(f"不支持的 target_scope: {target_scope}")

    @staticmethod
    def build_port_calibration_items(
        db: Session,
        *,
        run: CollectorRun,
        check_codes: list[str],
        target_scope: str,
        asset_ids: list[int],
        timeout_seconds: int,
        include_related_server: bool = True,
    ) -> tuple[list[CollectorRunItem], list[dict[str, Any]]]:
        items: list[CollectorRunItem] = []
        extra_items: list[dict[str, Any]] = []
        now = PortCalibrationService._now()
        for asset_id in asset_ids:
            host, candidates = PortCalibrationService.get_candidate_ports_for_asset(
                db,
                target_scope=target_scope,
                asset_id=asset_id,
                include_related_server=include_related_server,
            )
            if not candidates:
                record_event(
                    db,
                    asset_type=target_scope,
                    asset_id=asset_id,
                    event_type="PORT_PROFILE_MISSING",
                    before_status=None,
                    after_status=None,
                    changed_fields={"target_scope": target_scope, "asset_id": asset_id},
                    reason="未找到候选端口",
                    operator=run.requested_by or "system",
                )
                continue

            for candidate in candidates:
                for check_code in check_codes:
                    endpoint_type = candidate.get("endpoint_type") or PortCalibrationService._normalize_endpoint_type(
                        target_scope,
                        candidate.get("endpoint_type"),
                        candidate.get("port_source"),
                    )
                    item_key = f"{target_scope}:{asset_id}:{endpoint_type}:{candidate['port']}"
                    item = CollectorRunItem(
                        collector_run_id=int(run.id),
                        run_id=run.run_id,
                        item_key=item_key,
                        check_code=check_code,
                        target_scope=target_scope,
                        db_instance_id=asset_id if target_scope == "db_instance" else None,
                        server_id=asset_id if target_scope == "server" else None,
                        target_host=str(candidate.get("host") or host),
                        target_port=int(candidate["port"]),
                        protocol=str(candidate.get("protocol") or "tcp"),
                        timeout_seconds=timeout_seconds,
                        status="pending",
                        endpoint_type=str(endpoint_type),
                        port_source=str(candidate.get("port_source") or "unknown"),
                        is_required=bool(candidate.get("is_required")),
                        started_at=None,
                        finished_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                    extra = {
                        "item_key": item.item_key,
                        "check_code": check_code,
                        "target_scope": target_scope,
                        "asset_id": asset_id,
                        "target_host": item.target_host,
                        "target_port": item.target_port,
                        "timeout_seconds": item.timeout_seconds,
                        "endpoint_type": item.endpoint_type,
                        "protocol": item.protocol,
                        "port_source": item.port_source,
                        "is_required": item.is_required,
                    }
                    items.append(item)
                    extra_items.append(extra)
        return items, extra_items

    @staticmethod
    def create_port_change_proposals(
        db: Session,
        *,
        run: CollectorRun,
        callback_items: list[dict[str, Any]],
    ) -> None:
        grouped: dict[tuple[str, int, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in callback_items:
            grouped[
                (
                    row["target_scope"],
                    int(row["asset_id"]),
                    str(row.get("target_host") or ""),
                    str(row.get("protocol") or "tcp"),
                )
            ].append(row)

        for (target_scope, asset_id, host, protocol), rows in grouped.items():
            if target_scope != "db_instance":
                continue
            instance = db.query(DbInstance).filter(DbInstance.id == asset_id).first()
            if instance is None:
                continue

            service_rows = [row for row in rows if PortCalibrationService._is_service_endpoint_type(row.get("endpoint_type"))]
            if not service_rows:
                continue

            reachable_ports = sorted({int(row["target_port"]) for row in service_rows if row.get("reachable") is True})
            unreachable_ports = sorted({int(row["target_port"]) for row in service_rows if row.get("reachable") is False})
            current_port = PortCalibrationService._to_int(instance.port)

            if current_port is None and len(reachable_ports) == 1:
                AssetProposalService.create_proposal(
                    db,
                    target_type="db_instance",
                    target_id=asset_id,
                    proposal_type="PORT_FILL_SUGGESTION",
                    field_path="port",
                    current_value=None,
                    suggested_value=reachable_ports[0],
                    confidence="medium",
                    evidence={
                        "run_type": "port_calibration",
                        "endpoint_type": service_rows[0].get("endpoint_type"),
                        "reachable_candidates": reachable_ports,
                        "unreachable_candidates": unreachable_ports,
                        "target_host": host,
                        "protocol": protocol,
                    },
                    source_run_id=run.run_id,
                    source_item_key=service_rows[0].get("item_key"),
                    requested_by=run.requested_by,
                )
            elif current_port is None and len(reachable_ports) > 1:
                AssetProposalService.create_proposal(
                    db,
                    target_type="db_instance",
                    target_id=asset_id,
                    proposal_type="PORT_FILL_SUGGESTION",
                    field_path="port",
                    current_value=None,
                    suggested_value={"candidates": reachable_ports},
                    confidence="low",
                    evidence={
                        "run_type": "port_calibration",
                        "endpoint_type": service_rows[0].get("endpoint_type"),
                        "reachable_candidates": reachable_ports,
                        "unreachable_candidates": unreachable_ports,
                        "target_host": host,
                        "protocol": protocol,
                    },
                    source_run_id=run.run_id,
                    source_item_key=service_rows[0].get("item_key"),
                    requested_by=run.requested_by,
                )
            elif current_port is not None and current_port not in reachable_ports:
                alternatives = [port for port in reachable_ports if port != current_port]
                if alternatives:
                    confidence = "medium" if current_port in unreachable_ports else "low"
                    AssetProposalService.create_proposal(
                        db,
                        target_type="db_instance",
                        target_id=asset_id,
                        proposal_type="PORT_DRIFT_SUSPECTED",
                        field_path="port",
                        current_value=current_port,
                        suggested_value=alternatives[0],
                        confidence=confidence,
                        evidence={
                            "run_type": "port_calibration",
                            "endpoint_type": service_rows[0].get("endpoint_type"),
                            "reachable_candidates": reachable_ports,
                            "unreachable_candidates": unreachable_ports,
                            "target_host": host,
                            "protocol": protocol,
                            "note": "current_port_not_a_service_candidate" if current_port not in unreachable_ports else None,
                        },
                        source_run_id=run.run_id,
                        source_item_key=service_rows[0].get("item_key"),
                        requested_by=run.requested_by,
                    )
