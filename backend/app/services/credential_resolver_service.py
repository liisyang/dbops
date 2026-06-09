from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    CredentialBinding,
    CredentialProfile,
    DbInstance,
    Server,
)


class CredentialResolverService:
    """Resolve credentials for assets using the binding priority chain.

    Key behaviors:
    - Returns only: {credential_profile_id, credential_code, awx_credential_id,
                     awx_credential_name, credential_type, binding_role}
    - Missing credential → returns None (caller sets CREDENTIAL_MISSING)
    - OS credential: binding_role = os_readonly
    - DB credential: binding_role prefers db_readonly, then db_monitor
    - NEVER returns username/password/private_key
    """

    # Ordered list of binding roles to try for each target type
    OS_BINDING_ROLES = ["os_readonly", "os_sudo"]
    DB_BINDING_ROLES = ["db_readonly", "db_monitor"]

    @staticmethod
    def resolve_for_item(
        db: Session,
        target_scope: str,
        asset: dict[str, Any],
        check_code: str,
    ) -> dict[str, Any] | None:
        """Main entry point. Returns credential dict or None.

        Args:
            db: Database session
            target_scope: 'server' or 'db_instance'
            asset: Normalized asset dict from BatchCollectorService.resolve_assets()
            check_code: The check_code for this item

        Returns:
            Dict with credential references, or None if no credential found.
        """
        if target_scope == "server":
            server_id = int(asset["id"])
            return CredentialResolverService.resolve_os_credential(db, server_id)
        elif target_scope == "db_instance":
            instance_id = int(asset["id"])
            return CredentialResolverService.resolve_db_credential(db, instance_id)
        else:
            return None

    @staticmethod
    def resolve_os_credential(db: Session, server_id: int) -> dict[str, Any] | None:
        """Resolve OS credential for a server.

        Priority chain:
        1. server (binding_target_type='server', binding_target_id=server_id)
        2. business_system (via server → instance → cluster → business_system)
        3. network_zone (via server.extra_attrs.network_zone)
        4. global (binding_target_type='global')
        """
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return None

        # Collect candidate bindings across the priority chain
        candidates = CredentialResolverService._collect_os_candidates(db, server)
        if not candidates:
            return None

        # Pick the best match (lowest priority, then earliest binding_role)
        return CredentialResolverService._pick_best(candidates)

    @staticmethod
    def resolve_db_credential(db: Session, db_instance_id: int) -> dict[str, Any] | None:
        """Resolve DB credential for a db_instance.

        Priority chain:
        1. db_instance (binding_target_type='db_instance', binding_target_id=instance_id)
        2. cluster (via db_instance.cluster_id)
        3. business_system (via cluster.business_system_id)
        4. network_zone (via server.extra_attrs.network_zone)
        5. global (binding_target_type='global')
        """
        instance = db.query(DbInstance).filter(DbInstance.id == db_instance_id).first()
        if not instance:
            return None

        candidates = CredentialResolverService._collect_db_candidates(db, instance)
        if not candidates:
            return None

        return CredentialResolverService._pick_best(candidates)

    @staticmethod
    def _collect_os_candidates(db: Session, server: Server) -> list[dict[str, Any]]:
        """Collect all candidate credential bindings across the OS priority chain."""
        candidates: list[dict[str, Any]] = []
        server_id = int(server.id)

        # 1. Direct server binding
        candidates.extend(
            CredentialResolverService._query_bindings(
                db,
                binding_target_type="server",
                binding_target_id=server_id,
                binding_roles=CredentialResolverService.OS_BINDING_ROLES,
            )
        )

        # 2. Business system binding (via any db_instance → cluster → business_system)
        instances = db.query(DbInstance).filter(DbInstance.server_id == server_id).all()
        seen_bs_ids: set[int] = set()
        for inst in instances:
            if inst.cluster_id and inst.cluster:
                bs_id = int(inst.cluster.business_system_id) if inst.cluster.business_system_id else None
                if bs_id and bs_id not in seen_bs_ids:
                    seen_bs_ids.add(bs_id)
                    candidates.extend(
                        CredentialResolverService._query_bindings(
                            db,
                            binding_target_type="business_system",
                            binding_target_id=bs_id,
                            binding_roles=CredentialResolverService.OS_BINDING_ROLES,
                        )
                    )

        # 3. Network zone binding
        network_zone = (server.extra_attrs or {}).get("network_zone")
        if network_zone:
            candidates.extend(
                CredentialResolverService._query_bindings(
                    db,
                    binding_target_type="network_zone",
                    network_zone=str(network_zone),
                    binding_roles=CredentialResolverService.OS_BINDING_ROLES,
                )
            )

        # 4. Global binding
        candidates.extend(
            CredentialResolverService._query_bindings(
                db,
                binding_target_type="global",
                binding_roles=CredentialResolverService.OS_BINDING_ROLES,
            )
        )

        return candidates

    @staticmethod
    def _collect_db_candidates(db: Session, instance: DbInstance) -> list[dict[str, Any]]:
        """Collect all candidate credential bindings across the DB priority chain."""
        candidates: list[dict[str, Any]] = []
        instance_id = int(instance.id)

        # 1. Direct db_instance binding
        candidates.extend(
            CredentialResolverService._query_bindings(
                db,
                binding_target_type="db_instance",
                binding_target_id=instance_id,
                binding_roles=CredentialResolverService.DB_BINDING_ROLES,
            )
        )

        # 2. Cluster binding
        if instance.cluster_id:
            candidates.extend(
                CredentialResolverService._query_bindings(
                    db,
                    binding_target_type="cluster",
                    binding_target_id=int(instance.cluster_id),
                    binding_roles=CredentialResolverService.DB_BINDING_ROLES,
                )
            )

        # 3. Business system binding (via cluster)
        if instance.cluster and instance.cluster.business_system_id:
            candidates.extend(
                CredentialResolverService._query_bindings(
                    db,
                    binding_target_type="business_system",
                    binding_target_id=int(instance.cluster.business_system_id),
                    binding_roles=CredentialResolverService.DB_BINDING_ROLES,
                )
            )

        # 4. Network zone binding (via server)
        if instance.server_id:
            server = db.query(Server).filter(Server.id == instance.server_id).first()
            if server:
                network_zone = (server.extra_attrs or {}).get("network_zone")
                if network_zone:
                    candidates.extend(
                        CredentialResolverService._query_bindings(
                            db,
                            binding_target_type="network_zone",
                            network_zone=str(network_zone),
                            binding_roles=CredentialResolverService.DB_BINDING_ROLES,
                        )
                    )

        # 5. Global binding
        candidates.extend(
            CredentialResolverService._query_bindings(
                db,
                binding_target_type="global",
                binding_roles=CredentialResolverService.DB_BINDING_ROLES,
            )
        )

        return candidates

    @staticmethod
    def _query_bindings(
        db: Session,
        binding_target_type: str,
        binding_target_id: int | None = None,
        network_zone: str | None = None,
        binding_roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query credential_binding joined with credential_profile.

        Returns list of dicts with credential references (NO passwords).
        """
        query = (
            db.query(CredentialBinding, CredentialProfile)
            .join(CredentialProfile, CredentialBinding.profile_id == CredentialProfile.id)
            .filter(
                CredentialBinding.binding_target_type == binding_target_type,
                CredentialBinding.is_enabled == True,
                CredentialProfile.is_enabled == True,
            )
        )

        if binding_target_id is not None:
            query = query.filter(CredentialBinding.binding_target_id == binding_target_id)
        else:
            query = query.filter(CredentialBinding.binding_target_id.is_(None))

        if network_zone is not None:
            query = query.filter(CredentialBinding.network_zone == network_zone)
        else:
            query = query.filter(CredentialBinding.network_zone.is_(None))

        if binding_roles:
            query = query.filter(CredentialBinding.binding_role.in_(binding_roles))

        results = query.order_by(CredentialBinding.priority.asc()).all()

        return [
            {
                "credential_profile_id": int(binding.profile_id),
                "credential_code": profile.profile_code,
                "awx_credential_id": int(profile.awx_credential_id),
                "awx_credential_name": profile.awx_credential_name,
                "credential_type": profile.credential_type,
                "binding_role": binding.binding_role,
                "binding_target_type": binding.binding_target_type,
                "binding_priority": int(binding.priority),
                "default_database": profile.default_database,
                "db_type_code": profile.db_type_code,
            }
            for binding, profile in results
        ]

    @staticmethod
    def _pick_best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Pick the best candidate by priority (lower = better), then role order.

        Returns a dict with only the safe fields needed by consumers.
        """
        if not candidates:
            return None

        # Sort by priority, then by binding_role order
        role_order = {
            "db_readonly": 0,
            "db_monitor": 1,
            "os_readonly": 0,
            "os_sudo": 1,
        }

        def sort_key(c: dict[str, Any]) -> tuple[int, int]:
            role_rank = role_order.get(c.get("binding_role", ""), 99)
            return (int(c.get("binding_priority", 100)), role_rank)

        candidates.sort(key=sort_key)
        best = candidates[0]

        return {
            "credential_profile_id": best["credential_profile_id"],
            "credential_code": best["credential_code"],
            "awx_credential_id": best["awx_credential_id"],
            "awx_credential_name": best.get("awx_credential_name"),
            "credential_type": best["credential_type"],
            "binding_role": best["binding_role"],
            "default_database": best.get("default_database"),
            "db_type_code": best.get("db_type_code"),
        }
