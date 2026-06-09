from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dbops_assets import DbInstance, Server


class DispatchPlannerService:
    """Determine which AWX Instance Group each asset/item should be dispatched to.

    Priority chain (does NOT depend on site.extra_attrs):
    1. db_instance.extra_attrs.awx_instance_group
    2. db_instance.extra_attrs.network_zone
    3. server.extra_attrs.awx_instance_group
    4. server.extra_attrs.network_zone
    5. config.AWX_DEFAULT_INSTANCE_GROUP
    6. "default" (hardcoded fallback)
    """

    @staticmethod
    def _safe_extra(extra_attrs: dict[str, Any] | None, key: str) -> str | None:
        if not extra_attrs or not isinstance(extra_attrs, dict):
            return None
        value = extra_attrs.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
        return None

    @staticmethod
    def _resolve_network_zone(
        db_instance_extra: dict[str, Any] | None,
        server_extra: dict[str, Any] | None,
    ) -> str | None:
        zone = DispatchPlannerService._safe_extra(db_instance_extra, "network_zone")
        if zone:
            return zone
        return DispatchPlannerService._safe_extra(server_extra, "network_zone")

    @staticmethod
    def _resolve_awx_instance_group(
        db_instance_extra: dict[str, Any] | None,
        server_extra: dict[str, Any] | None,
    ) -> str | None:
        group = DispatchPlannerService._safe_extra(db_instance_extra, "awx_instance_group")
        if group:
            return group
        return DispatchPlannerService._safe_extra(server_extra, "awx_instance_group")

    @classmethod
    def resolve_dispatch_target(
        cls,
        db: Session,
        asset: dict[str, Any],
        target_scope: str,
    ) -> tuple[str, str]:
        """Return (network_zone, awx_instance_group) for an asset dict.

        The asset dict is expected to have keys from the asset resolution step:
        {id, target_scope, ...}.
        For db_instance scope, we also look up the associated Server.
        """
        db_instance_extra: dict[str, Any] | None = None
        server_extra: dict[str, Any] | None = None

        # Try to get extra_attrs from asset dict or from DB
        if target_scope == "db_instance":
            db_instance_extra = asset.get("extra_attrs")
            server_id = asset.get("server_id")

            # Single DB query to get both instance extra_attrs and server_id if needed
            if db_instance_extra is None or server_id is None:
                inst = db.query(DbInstance).filter(DbInstance.id == int(asset["id"])).first()
                if inst:
                    if db_instance_extra is None:
                        db_instance_extra = inst.extra_attrs or {}
                    if server_id is None:
                        server_id = inst.server_id

            if server_id:
                srv = db.query(Server).filter(Server.id == int(server_id)).first()
                if srv:
                    server_extra = srv.extra_attrs or {}
        elif target_scope == "server":
            server_extra = asset.get("extra_attrs")
            if server_extra is None:
                srv = db.query(Server).filter(Server.id == int(asset["id"])).first()
                if srv:
                    server_extra = srv.extra_attrs or {}

        # Resolve awx_instance_group with priority chain
        awx_instance_group = cls._resolve_awx_instance_group(db_instance_extra, server_extra)
        if not awx_instance_group:
            settings = get_settings()
            awx_instance_group = settings.AWX_DEFAULT_INSTANCE_GROUP or "default"

        # Resolve network_zone
        network_zone = cls._resolve_network_zone(db_instance_extra, server_extra) or ""

        return network_zone, awx_instance_group

    @classmethod
    def group_items_by_dispatch_target(
        cls,
        db: Session,
        items: list[dict[str, Any]],
        target_scope: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Group a list of item dicts by (network_zone, awx_instance_group).

        Each item dict must have an 'asset_id' or 'db_instance_id'/'server_id'
        key so we can resolve its dispatch target.

        Returns dict keyed by group_label like "NET_A|IG_NET_A".
        """
        # Build a lookup of asset_id → (network_zone, awx_instance_group)
        # from the items themselves. For efficiency we resolve each unique
        # asset once and cache.
        asset_cache: dict[tuple[str, int], tuple[str, str]] = {}

        def _resolve(scope: str, asset_id: int) -> tuple[str, str]:
            cache_key = (scope, asset_id)
            if cache_key not in asset_cache:
                asset_cache[cache_key] = cls.resolve_dispatch_target(
                    db,
                    {"id": asset_id, "target_scope": scope},
                    scope,
                )
            return asset_cache[cache_key]

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            item_scope = item.get("target_scope") or target_scope
            asset_id = item.get("db_instance_id") or item.get("server_id") or item.get("asset_id")
            if asset_id is None:
                # Can't resolve — put in skipped bucket
                group_key = "__skipped__"
            else:
                nz, ig = _resolve(item_scope, int(asset_id))
                if not ig:
                    group_key = "__skipped__"
                else:
                    group_key = f"{nz}|{ig}" if nz else ig

            grouped.setdefault(group_key, []).append(item)

        return grouped
