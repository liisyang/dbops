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

    @staticmethod
    def _build_skipped_item(
        *,
        item: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        skipped = dict(item)
        skipped["status"] = "skipped"
        skipped["result_status"] = None
        skipped["result_message"] = reason
        skipped["raw_result"] = {
            "skip_reason": reason,
            "skip_code": reason,
        }
        return skipped


class CheckItemBuilderRegistry:
    """Registry that maps check_code → builder.

    BatchCollectorService MUST use this registry for all item generation.
    It MUST NOT contain `if check_code == ...` branches.
    """

    _builders: dict[str, BaseCheckItemBuilder] = {}
    _inspection_item_templates: dict[str, dict[str, Any]] = {
        "CONNECTIVITY_PORT_REACHABLE": {
            "item_name": "端口连通性可达",
            "check_code": "DB_PORT_REACHABILITY",
            "target_scope": "db_instance",
            "severity": "critical",
        },
        "DB_VERSION_COLLECTED": {
            "item_name": "数据库版本已采集",
            "check_code": "DB_VERSION_FACT_COLLECTION",
            "target_scope": "db_instance",
            "severity": "warning",
        },
        "DB_ROLE_COLLECTED": {
            "item_name": "数据库角色已采集",
            "check_code": "DB_ROLE_FACT_COLLECTION",
            "target_scope": "db_instance",
            "severity": "warning",
        },
        "DB_ROLE_CHANGED": {
            "item_name": "数据库角色发生变化",
            "check_code": "DB_ROLE_FACT_COLLECTION",
            "target_scope": "db_instance",
            "severity": "critical",
        },
        "INSTANCE_PORT_DRIFT": {
            "item_name": "实例端口漂移",
            "check_code": "PORT_CANDIDATE_REACHABILITY",
            "target_scope": "db_instance",
            "severity": "critical",
        },
        "FACT_COLLECTION_FAILED": {
            "item_name": "事实采集失败",
            "check_code": "DB_BASIC_FACT_COLLECTION",
            "target_scope": "db_instance",
            "severity": "critical",
        },
        "CREDENTIAL_AUTH_FAILED": {
            "item_name": "凭证认证失败",
            "check_code": "DB_BASIC_FACT_COLLECTION",
            "target_scope": "db_instance",
            "severity": "critical",
        },
        "SERVER_OS_COLLECTED": {
            "item_name": "服务器OS事实已采集",
            "check_code": "OS_BASIC_FACT_COLLECTION",
            "target_scope": "server",
            "severity": "warning",
        },
    }
    _checkcode_to_inspection_items: dict[str, list[str]] = {
        "DB_PORT_REACHABILITY": ["CONNECTIVITY_PORT_REACHABLE", "INSTANCE_PORT_DRIFT"],
        "SSH_PORT_REACHABILITY": ["CONNECTIVITY_PORT_REACHABLE"],
        "PORT_CANDIDATE_REACHABILITY": ["CONNECTIVITY_PORT_REACHABLE", "INSTANCE_PORT_DRIFT"],
        "DB_BASIC_FACT_COLLECTION": ["FACT_COLLECTION_FAILED", "CREDENTIAL_AUTH_FAILED"],
        "DB_VERSION_FACT_COLLECTION": [
            "DB_VERSION_COLLECTED",
            "FACT_COLLECTION_FAILED",
            "CREDENTIAL_AUTH_FAILED",
        ],
        "DB_ROLE_FACT_COLLECTION": [
            "DB_ROLE_COLLECTED",
            "DB_ROLE_CHANGED",
            "FACT_COLLECTION_FAILED",
            "CREDENTIAL_AUTH_FAILED",
        ],
        "OS_BASIC_FACT_COLLECTION": [
            "SERVER_OS_COLLECTED",
            "FACT_COLLECTION_FAILED",
            "CREDENTIAL_AUTH_FAILED",
        ],
    }

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

    @classmethod
    def inspection_item_templates(cls) -> dict[str, dict[str, Any]]:
        return dict(cls._inspection_item_templates)

    @classmethod
    def inspection_item_codes(cls) -> list[str]:
        return sorted(cls._inspection_item_templates.keys())

    @classmethod
    def inspection_defaults(cls, item_codes: list[str] | None = None) -> list[dict[str, Any]]:
        selected = set(item_codes or cls.inspection_item_codes())
        rows: list[dict[str, Any]] = []
        for item_code, template in cls._inspection_item_templates.items():
            if item_code not in selected:
                continue
            rows.append(
                {
                    "item_code": item_code,
                    "item_name": template["item_name"],
                    "check_code": template["check_code"],
                    "target_scope": template["target_scope"],
                    "severity": template["severity"],
                    "enabled": True,
                    "rule_config": {},
                }
            )
        return rows

    @classmethod
    def resolve_check_codes_for_inspection_items(cls, item_codes: list[str]) -> list[str]:
        code_set = set(item_codes)
        check_codes: list[str] = []
        for check_code, mapped_items in cls._checkcode_to_inspection_items.items():
            if code_set.intersection(mapped_items):
                check_codes.append(check_code)
        return sorted(set(check_codes))

    @staticmethod
    def _facts_from_raw(raw_result: dict[str, Any]) -> dict[str, Any]:
        facts = raw_result.get("facts")
        if isinstance(facts, dict):
            return facts
        if isinstance(facts, list):
            converted: dict[str, Any] = {}
            for row in facts:
                if isinstance(row, dict) and row.get("fact_key"):
                    converted[str(row["fact_key"])] = row.get("fact_value")
            return converted
        return {}

    @staticmethod
    def _contains_auth_failed(message: str, raw_result: dict[str, Any]) -> bool:
        error_code = str(raw_result.get("error_code") or "").upper()
        error_message = str(raw_result.get("error_message") or message or "").upper()
        if error_code in {"AUTHENTICATION_FAILED", "INVALID_CREDENTIAL"}:
            return True
        return (
            "ORA-01017" in error_message
            or "AUTHENTICATION_FAILED" in error_message
            or "LOGIN FAILED" in error_message
            or "PASSWORD" in error_message and "INVALID" in error_message
        )

    @classmethod
    def build_inspection_results_from_callback(
        cls,
        *,
        check_code: str,
        status: str,
        target_scope: str,
        asset_id: int,
        item_key: str | None,
        message: str | None,
        raw_result: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        normalized_check_code = (check_code or "").strip().upper()
        normalized_status = (status or "").strip().lower()
        payload = dict(raw_result or {})
        facts = cls._facts_from_raw(payload)
        candidates = cls._checkcode_to_inspection_items.get(normalized_check_code, [])
        rows: list[dict[str, Any]] = []

        for item_code in candidates:
            template = cls._inspection_item_templates.get(item_code)
            if not template:
                continue

            result_status = "unknown"
            result_message = message
            result_code = item_code

            if item_code == "CONNECTIVITY_PORT_REACHABLE":
                if normalized_status in {"verified", "collected"}:
                    result_status = "normal"
                elif normalized_status in {"missing", "failed", "drifted"}:
                    result_status = "abnormal"
                else:
                    result_status = "unknown"
            elif item_code == "DB_VERSION_COLLECTED":
                has_version_fact = "db_version" in facts or "version" in facts
                if normalized_status in {"verified", "collected"} and has_version_fact:
                    result_status = "normal"
                else:
                    result_status = "abnormal"
                    result_message = result_message or "DB_VERSION_MISSING"
            elif item_code == "DB_ROLE_COLLECTED":
                has_role_fact = "db_role" in facts or "role" in facts
                if normalized_status in {"verified", "collected"} and has_role_fact:
                    result_status = "normal"
                else:
                    result_status = "abnormal"
                    result_message = result_message or "DB_ROLE_MISSING"
            elif item_code == "DB_ROLE_CHANGED":
                changed = bool(
                    facts.get("db_role_changed")
                    or payload.get("db_role_changed")
                    or (
                        facts.get("previous_role") is not None
                        and facts.get("current_role") is not None
                        and facts.get("previous_role") != facts.get("current_role")
                    )
                )
                if changed:
                    result_status = "abnormal"
                    result_message = result_message or "DB_ROLE_CHANGED"
                else:
                    result_status = "normal"
            elif item_code == "INSTANCE_PORT_DRIFT":
                if normalized_status == "drifted":
                    result_status = "abnormal"
                    result_message = result_message or "INSTANCE_PORT_DRIFT"
                elif normalized_status in {"verified", "collected"}:
                    result_status = "normal"
                else:
                    result_status = "warning"
            elif item_code == "FACT_COLLECTION_FAILED":
                if normalized_status in {"failed", "missing"}:
                    result_status = "abnormal"
                    result_message = result_message or "FACT_COLLECTION_FAILED"
                elif normalized_status in {"verified", "collected"}:
                    result_status = "normal"
                else:
                    result_status = "warning"
            elif item_code == "CREDENTIAL_AUTH_FAILED":
                if cls._contains_auth_failed(result_message or "", payload):
                    result_status = "abnormal"
                    result_message = result_message or "CREDENTIAL_AUTH_FAILED"
                else:
                    result_status = "normal"
            elif item_code == "SERVER_OS_COLLECTED":
                has_os_fact = any(key.startswith("os_") for key in facts.keys()) or "hostname" in facts
                if normalized_status in {"verified", "collected"} and has_os_fact:
                    result_status = "normal"
                else:
                    result_status = "abnormal"
                    result_message = result_message or "OS_FACT_MISSING"

            rows.append(
                {
                    "item_code": item_code,
                    "item_name": template["item_name"],
                    "check_code": normalized_check_code,
                    "target_scope": target_scope,
                    "asset_id": int(asset_id),
                    "result_code": result_code,
                    "result_status": result_status,
                    "severity": template["severity"],
                    "message": result_message,
                    "evidence": {
                        "collector_item_key": item_key,
                        "raw_result": payload,
                    },
                }
            )

        return rows


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
                    "server_id": int(instance.server_id),
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


# ============================================================================
# Phase 3.3A — Fact collection builders
# ============================================================================


class _OsBasicFactCollectionBuilder(BaseCheckItemBuilder):
    """Generate items for OS_BASIC_FACT_COLLECTION.

    For each server asset, resolves OS readonly credential and builds
    an item targeting the server's SSH port.
    """

    def build(self, db, *, assets, options):
        from app.models.dbops_assets import Server
        from app.services.credential_resolver_service import CredentialResolverService

        timeout_seconds = int(options.get("timeout_seconds") or 30)
        items: list[dict[str, Any]] = []

        for asset in assets:
            target_scope = asset.get("target_scope", "server")
            if target_scope != "server":
                continue

            server_id = int(asset["id"])
            server = db.query(Server).filter(Server.id == server_id).first()
            if not server:
                continue

            # Resolve credential
            credential = CredentialResolverService.resolve_for_item(
                db,
                target_scope="server",
                asset=asset,
                check_code="OS_BASIC_FACT_COLLECTION",
            )
            if not credential:
                items.append(
                    self._build_skipped_item(
                        item={
                            "item_key": f"server:{server_id}:OS_BASIC_FACT_COLLECTION:{str(server.ip_address)}:{int(options.get('ssh_port') or (server.extra_attrs or {}).get('ssh_port') or 22)}",
                            "check_code": "OS_BASIC_FACT_COLLECTION",
                            "target_scope": "server",
                            "server_id": server_id,
                            "target_host": str(options.get("target_host") or str(server.ip_address)),
                            "target_port": int(options.get("ssh_port") or (server.extra_attrs or {}).get("ssh_port") or 22),
                            "protocol": "ssh",
                            "endpoint_type": "OS_ADMIN_PORT",
                            "port_source": "server_extra_attrs",
                            "is_required": True,
                            "timeout_seconds": timeout_seconds,
                            "asset_name": server.hostname or server.server_code or str(server_id),
                            "os_family": str((server.extra_attrs or {}).get("os_family") or "linux"),
                            "credential_profile_id": None,
                            "credential_code": None,
                            "awx_credential_id": None,
                            "credential_role": None,
                            "credential_type": None,
                        },
                        reason="CREDENTIAL_MISSING",
                    )
                )
                continue

            target_host = str(options.get("target_host") or str(server.ip_address))
            # SSH port: try options, then server extra_attrs, default 22
            ssh_port = int(options.get("ssh_port") or (server.extra_attrs or {}).get("ssh_port") or 22)
            os_family = str((server.extra_attrs or {}).get("os_family") or "linux")

            item_key = f"server:{server_id}:OS_BASIC_FACT_COLLECTION:{target_host}:{ssh_port}"
            items.append(
                {
                    "item_key": item_key,
                    "check_code": "OS_BASIC_FACT_COLLECTION",
                    "target_scope": "server",
                    "server_id": server_id,
                    "target_host": target_host,
                    "target_port": ssh_port,
                    "protocol": "ssh",
                    "endpoint_type": "OS_ADMIN_PORT",
                    "port_source": "server_extra_attrs",
                    "is_required": True,
                    "timeout_seconds": timeout_seconds,
                    "asset_name": server.hostname or server.server_code or str(server_id),
                    "os_family": os_family,
                    "credential_profile_id": credential["credential_profile_id"],
                    "credential_code": credential["profile_code"],
                    "awx_credential_id": credential["awx_credential_id"],
                    "credential_role": credential["binding_role"],
                    "credential_type": credential["credential_type"],
                }
            )
        return items


class _DbFactCollectionBuilderBase(BaseCheckItemBuilder):
    """Shared logic for DB fact collection builders.

    Subclasses set `_check_code` to the specific check_code they handle.
    """

    _check_code: str = ""

    @staticmethod
    def _default_database(db_type_code: str) -> str:
        """Return the default database name for initial connection."""
        defaults = {
            "mssql": "master",
            "sqlserver": "master",
            "postgresql": "postgres",
            "postgres": "postgres",
            "mysql": "mysql",
        }
        return defaults.get((db_type_code or "").lower(), "master")

    def build(self, db, *, assets, options):
        from app.models.dbops_assets import DbInstance, DbType, Server
        from app.services.credential_resolver_service import CredentialResolverService

        timeout_seconds = int(options.get("timeout_seconds") or 30)
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

            db_type = db.query(DbType).filter(DbType.id == instance.db_type_id).first()
            db_type_code = (db_type.type_code or "").lower() if db_type else ""
            target_host = str(options.get("target_host") or str(server.ip_address))
            target_port = int(options.get("target_port") or instance.port or 0)
            database_name = str(options.get("database_name") or self._default_database(db_type_code))
            service_name = instance.service_name or ""

            # Resolve credential
            credential = CredentialResolverService.resolve_for_item(
                db,
                target_scope="db_instance",
                asset=asset,
                check_code=self._check_code,
            )
            if not credential:
                items.append(
                    self._build_skipped_item(
                        item={
                            "item_key": f"db_instance:{instance_id}:{self._check_code}:{target_host}:{target_port}",
                            "check_code": self._check_code,
                            "target_scope": "db_instance",
                            "db_instance_id": instance_id,
                            "server_id": int(instance.server_id),
                            "target_host": target_host,
                            "target_port": target_port,
                            "protocol": "tcp",
                            "endpoint_type": "DB_SERVICE_PORT",
                            "port_source": "db_instance_port",
                            "is_required": True,
                            "timeout_seconds": timeout_seconds,
                            "asset_name": instance.instance_name or str(instance_id),
                            "db_type_code": db_type_code,
                            "database_name": database_name,
                            "service_name": service_name if db_type_code in ("oracle",) else None,
                            "credential_profile_id": None,
                            "credential_code": None,
                            "awx_credential_id": None,
                            "credential_role": None,
                            "credential_type": None,
                        },
                        reason="CREDENTIAL_MISSING",
                    )
                )
                continue

            if target_port < 1 or target_port > 65535:
                continue

            item_key = (
                f"db_instance:{instance_id}:{self._check_code}:{target_host}:{target_port}"
            )

            item: dict[str, Any] = {
                "item_key": item_key,
                "check_code": self._check_code,
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
                "db_type_code": db_type_code,
                "database_name": database_name,
                "credential_profile_id": credential["credential_profile_id"],
                "credential_code": credential["profile_code"],
                "awx_credential_id": credential["awx_credential_id"],
                "credential_role": credential["binding_role"],
                "credential_type": credential["credential_type"],
            }

            # Oracle-specific: add service_name
            if db_type_code in ("oracle",):
                item["service_name"] = service_name

            items.append(item)

        return items


class _DbBasicFactCollectionBuilder(_DbFactCollectionBuilderBase):
    _check_code = "DB_BASIC_FACT_COLLECTION"


class _DbVersionFactCollectionBuilder(_DbFactCollectionBuilderBase):
    _check_code = "DB_VERSION_FACT_COLLECTION"


class _DbRoleFactCollectionBuilder(_DbFactCollectionBuilderBase):
    _check_code = "DB_ROLE_FACT_COLLECTION"


# Register built-in builders
CheckItemBuilderRegistry.register("DB_PORT_REACHABILITY", _DbPortReachabilityBuilder())
CheckItemBuilderRegistry.register("SSH_PORT_REACHABILITY", _SshPortReachabilityBuilder())
CheckItemBuilderRegistry.register("PORT_CANDIDATE_REACHABILITY", _PortCandidateReachabilityBuilder())
CheckItemBuilderRegistry.register("OS_BASIC_FACT_COLLECTION", _OsBasicFactCollectionBuilder())
CheckItemBuilderRegistry.register("DB_BASIC_FACT_COLLECTION", _DbBasicFactCollectionBuilder())
CheckItemBuilderRegistry.register("DB_VERSION_FACT_COLLECTION", _DbVersionFactCollectionBuilder())
CheckItemBuilderRegistry.register("DB_ROLE_FACT_COLLECTION", _DbRoleFactCollectionBuilder())
