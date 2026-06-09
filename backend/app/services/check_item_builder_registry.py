from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import CollectorRunItem
from app.services.port_calibration_service import PortCalibrationService


class BaseCheckItemBuilder:
    """Base class for check_code → item builders.

    Each builder receives (db, assets, options) and returns a list of
    dicts with keys suitable for CollectorRunItem construction plus
    extra_vars entries.
    """

    def build(
        self,
        db: Session,
        *,
        assets: list[Any],
        options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class CheckItemBuilderRegistry:
    """Registry that maps check_code → builder.

    BatchCollectorService MUST use this registry for all item generation.
    It MUST NOT contain `if check_code == ...` branches.
    """

    _builders: dict[str, BaseCheckItemBuilder] = {}

    @classmethod
    def register(cls, check_code: str, builder: BaseCheckItemBuilder) -> None:
        cls._builders[check_code] = builder

    @classmethod
    def build_items(
        cls,
        db: Session,
        check_code: str,
        assets: list[Any],
        options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        builder = cls._builders.get(check_code)
        if builder is None:
            raise ValueError(f"Unsupported check_code: {check_code}")
        return builder.build(db=db, assets=assets, options=options)

    @classmethod
    def supported_codes(cls) -> list[str]:
        return sorted(cls._builders.keys())


# ============================================================================
# Built-in builders
# ============================================================================


class _DbPortReachabilityBuilder(BaseCheckItemBuilder):
    """Generate items for DB_PORT_REACHABILITY check.

    For each db_instance asset, builds one item targeting instance.port
    on the associated server's IP.
    """

    def build(self, db, *, assets, options):
        from app.models.dbops_assets import DbInstance, Server

        timeout_seconds = int(options.get("timeout_seconds") or 5)
        items: list[dict[str, Any]] = []

        for asset in assets:
            target_scope = asset.get("target_scope", "db_instance")
            if target_scope != "db_instance":
                continue

            instance_id = int(asset["id"])
            instance = db.query(DbInstance).filter(DbInstance.id == instance_id).first()
            if not instance:
                continue

            server = db.query(Server).filter(Server.id == instance.server_id).first()
            if not server:
                continue

            target_host = str(options.get("target_host") or str(server.ip_address))
            target_port = int(options.get("target_port") or instance.port or 0)
            if target_port < 1 or target_port > 65535:
                continue

            item_key = f"db_instance:{instance_id}:DB_PORT_REACHABILITY:{target_host}:{target_port}"
            items.append(
                {
                    "item_key": item_key,
                    "check_code": "DB_PORT_REACHABILITY",
                    "target_scope": "db_instance",
                    "db_instance_id": instance_id,
                    "server_id": int(server.id),
                    "target_host": target_host,
                    "target_port": target_port,
                    "protocol": "tcp",
                    "endpoint_type": "DB_SERVICE_PORT",
                    "port_source": "db_instance_port",
                    "is_required": True,
                    "timeout_seconds": timeout_seconds,
                    "asset_name": instance.instance_name or str(instance_id),
                }
            )
        return items


class _SshPortReachabilityBuilder(BaseCheckItemBuilder):
    """Generate items for SSH_PORT_REACHABILITY check.

    For each server asset (or server associated with db_instance),
    resolves the SSH/admin port via PortCalibrationService.
    """

    def build(self, db, *, assets, options):
        timeout_seconds = int(options.get("timeout_seconds") or 5)
        items: list[dict[str, Any]] = []

        for asset in assets:
            target_scope = asset.get("target_scope", "server")
            resolved_server_id: int | None = None

            if target_scope == "server":
                resolved_server_id = int(asset["id"])
            elif target_scope == "db_instance":
                resolved_server_id = int(asset.get("server_id") or 0)

            if not resolved_server_id:
                continue

            try:
                host, candidates = PortCalibrationService.get_candidate_ports_for_asset(
                    db,
                    target_scope="server",
                    asset_id=resolved_server_id,
                    include_related_server=False,
                )
            except (LookupError, ValueError):
                continue

            if not candidates:
                continue

            # Use the first candidate as the SSH/admin port
            chosen = candidates[0]
            target_host = str(options.get("target_host") or host)
            target_port = int(chosen["port"])

            item_key = f"server:{resolved_server_id}:SSH_PORT_REACHABILITY:{target_host}:{target_port}"
            items.append(
                {
                    "item_key": item_key,
                    "check_code": "SSH_PORT_REACHABILITY",
                    "target_scope": "server",
                    "server_id": resolved_server_id,
                    "target_host": target_host,
                    "target_port": target_port,
                    "protocol": str(chosen.get("protocol") or "tcp"),
                    "endpoint_type": "OS_ADMIN_PORT",
                    "port_source": str(chosen.get("port_source") or "server_extra_attrs"),
                    "is_required": True,
                    "timeout_seconds": timeout_seconds,
                    "asset_name": f"server-{resolved_server_id}",
                }
            )
        return items


class _PortCandidateReachabilityBuilder(BaseCheckItemBuilder):
    """Generate items for PORT_CANDIDATE_REACHABILITY check.

    Delegates to PortCalibrationService.build_port_calibration_items.
    Each asset produces multiple items (one per candidate port).
    """

    def build(self, db, *, assets, options):
        from app.models.dbops_assets import CollectorRun

        timeout_seconds = int(options.get("timeout_seconds") or 3)
        include_related_server = bool(options.get("include_related_server", True))
        items: list[dict[str, Any]] = []

        for asset in assets:
            target_scope = asset.get("target_scope", "db_instance")
            asset_id = int(asset["id"])

            try:
                host, candidates = PortCalibrationService.get_candidate_ports_for_asset(
                    db,
                    target_scope=target_scope,
                    asset_id=asset_id,
                    include_related_server=include_related_server,
                )
            except (LookupError, ValueError):
                continue

            for candidate in candidates:
                endpoint_type = candidate.get("endpoint_type") or PortCalibrationService._normalize_endpoint_type(
                    target_scope,
                    candidate.get("endpoint_type"),
                    candidate.get("port_source"),
                )
                item_key = f"{target_scope}:{asset_id}:{endpoint_type}:{candidate['port']}"
                items.append(
                    {
                        "item_key": item_key,
                        "check_code": "PORT_CANDIDATE_REACHABILITY",
                        "target_scope": target_scope,
                        "db_instance_id": asset_id if target_scope == "db_instance" else None,
                        "server_id": asset_id if target_scope == "server" else None,
                        "target_host": str(candidate.get("host") or host),
                        "target_port": int(candidate["port"]),
                        "protocol": str(candidate.get("protocol") or "tcp"),
                        "endpoint_type": str(endpoint_type),
                        "port_source": str(candidate.get("port_source") or "unknown"),
                        "is_required": bool(candidate.get("is_required")),
                        "timeout_seconds": timeout_seconds,
                        "asset_name": f"{target_scope}-{asset_id}",
                    }
                )
        return items


# Register built-in builders
CheckItemBuilderRegistry.register("DB_PORT_REACHABILITY", _DbPortReachabilityBuilder())
CheckItemBuilderRegistry.register("SSH_PORT_REACHABILITY", _SshPortReachabilityBuilder())
CheckItemBuilderRegistry.register("PORT_CANDIDATE_REACHABILITY", _PortCandidateReachabilityBuilder())
