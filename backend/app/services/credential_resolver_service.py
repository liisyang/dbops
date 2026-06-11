from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    Cluster,
    CredentialBinding,
    CredentialProfile,
    DbInstance,
    DbType,
    Server,
)


class CredentialResolverService:
    """Resolve credentials for fact collection items.

    Priority chain (first match wins, sorted by binding priority ascending):
      OS:  server > business_system > network_zone > global
      DB:  db_instance > cluster > business_system > network_zone > global

    Role resolution:
      binding_role on CredentialBinding takes precedence over CredentialProfile.binding_role.

    Type filtering:
      DB:  matches CredentialProfile.db_type_code against the instance's DbType.type_code.
      OS:  matches CredentialProfile.os_family against the server's extra_attrs.os_family.

    Returns only credential reference metadata — NEVER plaintext passwords.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_for_item(
        db: Session,
        *,
        target_scope: str,
        asset: dict[str, Any],
        check_code: str,
    ) -> dict[str, Any] | None:
        """Resolve the credential for a single collector item.

        Returns dict with keys:
          credential_profile_id, profile_code, awx_credential_id,
          awx_credential_name, credential_type, binding_role

        Returns None when no matching credential is found.
        """
        asset_id = int(asset["id"])

        if target_scope == "server":
            return CredentialResolverService.resolve_os_credential(db, server_id=asset_id)

        if target_scope == "db_instance":
            preferred_roles = CredentialResolverService._db_roles_for_check_code(check_code)
            return CredentialResolverService.resolve_db_credential(
                db, db_instance_id=asset_id, preferred_roles=preferred_roles
            )

        return None

    # ------------------------------------------------------------------
    # OS credential resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_os_credential(
        db: Session,
        *,
        server_id: int,
    ) -> dict[str, Any] | None:
        """Resolve OS readonly credential for a server.

        Priority: server > business_system > network_zone > global
        Filters by os_family from server.extra_attrs.os_family.
        """
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return None

        extra = server.extra_attrs or {}
        network_zone = str(extra.get("network_zone", "")).strip() or None
        os_family = str(extra.get("os_family", "")).strip() or None

        # 1) Direct server binding
        result = CredentialResolverService._query_binding(
            db,
            target_type="server",
            target_id=server_id,
            binding_roles=["os_readonly"],
            os_family=os_family,
        )
        if result:
            return result

        # 2) Business system binding (via instances → cluster)
        business_system_ids = CredentialResolverService._resolve_server_business_system_ids(db, server_id)
        if business_system_ids:
            result = CredentialResolverService._query_binding(
                db,
                target_type="business_system",
                target_ids=business_system_ids,
                binding_roles=["os_readonly"],
                os_family=os_family,
            )
            if result:
                return result

        # 3) Network zone binding
        if network_zone:
            result = CredentialResolverService._query_binding(
                db,
                target_type="network_zone",
                network_zone=network_zone,
                binding_roles=["os_readonly"],
                os_family=os_family,
            )
            if result:
                return result

        # 4) Global binding
        return CredentialResolverService._query_binding(
            db,
            target_type="global",
            binding_roles=["os_readonly"],
            os_family=os_family,
        )

    # ------------------------------------------------------------------
    # DB credential resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_db_credential(
        db: Session,
        *,
        db_instance_id: int,
        preferred_roles: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Resolve DB readonly credential for a db_instance.

        Priority: db_instance > cluster > business_system > network_zone > global
        Filters by db_type_code from the instance's DbType.type_code.
        """
        if preferred_roles is None:
            preferred_roles = ["db_readonly", "db_monitor"]

        instance = db.query(DbInstance).filter(DbInstance.id == db_instance_id).first()
        if not instance:
            return None

        # Get db_type_code for filtering
        db_type_code: str | None = None
        if instance.db_type_id:
            db_type = db.query(DbType).filter(DbType.id == instance.db_type_id).first()
            if db_type:
                db_type_code = (db_type.type_code or "").lower().strip() or None

        server = db.query(Server).filter(Server.id == instance.server_id).first()
        extra = server.extra_attrs if server else {}
        network_zone = str(extra.get("network_zone", "")).strip() or None

        cluster_id = int(instance.cluster_id) if instance.cluster_id else None
        business_system_id: int | None = None
        if cluster_id:
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster and cluster.business_system_id:
                business_system_id = int(cluster.business_system_id)

        # 1) Direct db_instance binding
        result = CredentialResolverService._query_binding(
            db,
            target_type="db_instance",
            target_ids=[db_instance_id],
            binding_roles=preferred_roles,
            db_type_code=db_type_code,
        )
        if result:
            return result

        # 2) Cluster binding
        if cluster_id:
            result = CredentialResolverService._query_binding(
                db,
                target_type="cluster",
                target_ids=[cluster_id],
                binding_roles=preferred_roles,
                db_type_code=db_type_code,
            )
            if result:
                return result

        # 3) Business system binding
        if business_system_id:
            result = CredentialResolverService._query_binding(
                db,
                target_type="business_system",
                target_ids=[business_system_id],
                binding_roles=preferred_roles,
                db_type_code=db_type_code,
            )
            if result:
                return result

        # 4) Network zone binding
        if network_zone:
            result = CredentialResolverService._query_binding(
                db,
                target_type="network_zone",
                network_zone=network_zone,
                binding_roles=preferred_roles,
                db_type_code=db_type_code,
            )
            if result:
                return result

        # 5) Global binding
        return CredentialResolverService._query_binding(
            db,
            target_type="global",
            binding_roles=preferred_roles,
            db_type_code=db_type_code,
        )

    # ------------------------------------------------------------------
    # Query helpers — unified single-entry query with db_type_code / os_family filter
    # ------------------------------------------------------------------

    @staticmethod
    def _query_binding(
        db: Session,
        *,
        target_type: str,
        target_id: int | None = None,
        target_ids: list[int] | None = None,
        binding_roles: list[str] | None = None,
        network_zone: str | None = None,
        db_type_code: str | None = None,
        os_family: str | None = None,
    ) -> dict[str, Any] | None:
        """Unified query: returns the best-matching binding + profile pair.

        Role resolution:
          Filters by CredentialBinding.binding_role first; if NULL on binding,
          falls back to CredentialProfile.binding_role.

        Type filtering:
          If db_type_code is given, prefers profiles with matching db_type_code
          (or NULL db_type_code) — exact match ranked higher.
          If os_family is given, prefers profiles with matching os_family
          (or NULL os_family) — exact match ranked higher.
        """
        if not binding_roles:
            return None

        query = (
            db.query(CredentialBinding, CredentialProfile)
            .join(CredentialProfile, CredentialBinding.credential_profile_id == CredentialProfile.id)
            .filter(
                CredentialBinding.target_type == target_type,
                CredentialBinding.is_enabled == True,
                CredentialProfile.is_enabled == True,
            )
        )

        # target_id / target_ids
        if target_ids is not None:
            query = query.filter(CredentialBinding.target_id.in_(target_ids))
        elif target_id is not None:
            query = query.filter(CredentialBinding.target_id == target_id)
        else:
            query = query.filter(CredentialBinding.target_id.is_(None))

        # network_zone
        if network_zone is not None:
            query = query.filter(CredentialBinding.network_zone == network_zone)

        # Role filter: binding_role takes precedence over profile.binding_role
        # Use OR: (binding.binding_role IN roles) OR (binding.binding_role IS NULL AND profile.binding_role IN roles)
        from sqlalchemy import or_, and_

        role_cond = or_(
            CredentialBinding.binding_role.in_(binding_roles),
            and_(
                CredentialBinding.binding_role.is_(None),
                CredentialProfile.binding_role.in_(binding_roles),
            ),
        )
        query = query.filter(role_cond)

        # db_type_code / os_family: prefer exact match, but also accept NULL
        if db_type_code is not None:
            query = query.filter(
                or_(
                    CredentialProfile.db_type_code == db_type_code,
                    CredentialProfile.db_type_code.is_(None),
                )
            )
        if os_family is not None:
            query = query.filter(
                or_(
                    CredentialProfile.os_family == os_family,
                    CredentialProfile.os_family.is_(None),
                )
            )

        rows = query.order_by(CredentialBinding.priority.asc()).all()
        if not rows:
            return None

        # Score and pick best:
        #   - prefer exact db_type_code / os_family match over NULL
        #   - prefer earlier role in binding_roles
        #   - lower priority = better
        role_rank = {r: i for i, r in enumerate(binding_roles)}

        def _score(row) -> tuple[int, int, int, int]:
            binding, profile = row
            # exact db_type_code match = 0, NULL = 1
            db_score = 0 if (db_type_code and profile.db_type_code == db_type_code) else (1 if profile.db_type_code is None else 2)
            # exact os_family match = 0, NULL = 1
            os_score = 0 if (os_family and profile.os_family == os_family) else (1 if profile.os_family is None else 2)
            # effective role
            eff_role = binding.binding_role or profile.binding_role
            role_score = role_rank.get(eff_role, 99)
            priority = binding.priority or 100
            return (db_score, os_score, role_score, priority)

        rows.sort(key=_score)
        return CredentialResolverService._to_dict(rows[0])

    @staticmethod
    def _to_dict(row) -> dict[str, Any]:
        binding, profile = row
        eff_role = binding.binding_role or profile.binding_role
        return {
            "credential_profile_id": int(profile.id),
            "profile_code": profile.profile_code,
            "awx_credential_id": profile.awx_credential_id,
            "awx_credential_name": profile.awx_credential_name,
            "credential_type": profile.credential_type,
            "binding_role": eff_role,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _db_roles_for_check_code(check_code: str) -> list[str]:
        """Return the preferred binding_role(s) for a DB fact check_code."""
        fact_check_codes = {
            "DB_BASIC_FACT_COLLECTION",
            "DB_VERSION_FACT_COLLECTION",
            "DB_ROLE_FACT_COLLECTION",
        }
        if check_code in fact_check_codes:
            return ["db_readonly", "db_monitor"]
        return ["db_readonly", "db_monitor", "db_owner", "db_admin"]

    @staticmethod
    def _resolve_server_business_system_ids(db: Session, server_id: int) -> list[int]:
        """Find all business_system_ids that this server belongs to.

        Traversal: server → db_instance → cluster → business_system
        """
        instances = (
            db.query(DbInstance.cluster_id)
            .filter(DbInstance.server_id == server_id, DbInstance.cluster_id.isnot(None))
            .distinct()
            .all()
        )
        cluster_ids = [row[0] for row in instances if row[0] is not None]
        if not cluster_ids:
            return []

        clusters = (
            db.query(Cluster.business_system_id)
            .filter(
                Cluster.id.in_(cluster_ids),
                Cluster.business_system_id.isnot(None),
            )
            .distinct()
            .all()
        )
        return [row[0] for row in clusters if row[0] is not None]
