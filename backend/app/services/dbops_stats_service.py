from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import BusinessSystem, Cluster, DbInstance, Server, Site, SystemGroup


class DbopsStatsService:
    @staticmethod
    def _count_by(rows: list[Any], key_builder) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            key = key_builder(row) or "未知"
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def dashboard(db: Session) -> dict[str, Any]:
        return {
            "total_business_systems": db.query(BusinessSystem).count(),
            "total_clusters": db.query(Cluster).count(),
            "total_instances": db.query(DbInstance).count(),
            "total_servers": db.query(Server).count(),
        }

    @staticmethod
    def by_country(db: Session) -> dict[str, Any]:
        sites = {row.id: row for row in db.query(Site).all()}
        servers = {row.id: row for row in db.query(Server).all()}
        instances = db.query(DbInstance).all()
        counts = DbopsStatsService._count_by(
            instances,
            lambda item: sites.get(servers.get(item.server_id).site_id).country if servers.get(item.server_id) and sites.get(servers.get(item.server_id).site_id) else "未知",
        )
        return {"groups": [{"country": key, "count": value} for key, value in counts.items()]}

    @staticmethod
    def by_factory(db: Session) -> dict[str, Any]:
        sites = {row.id: row for row in db.query(Site).all()}
        servers = {row.id: row for row in db.query(Server).all()}
        instances = db.query(DbInstance).all()
        counts = DbopsStatsService._count_by(
            instances,
            lambda item: sites.get(servers.get(item.server_id).site_id).factory_area if servers.get(item.server_id) and sites.get(servers.get(item.server_id).site_id) else "未知",
        )
        return {"groups": [{"factory_area": key, "count": value} for key, value in counts.items()]}

    @staticmethod
    def by_deploy_type(db: Session) -> dict[str, Any]:
        sites = {row.id: row for row in db.query(Site).all()}
        servers = {row.id: row for row in db.query(Server).all()}
        instances = db.query(DbInstance).all()
        counts = DbopsStatsService._count_by(
            instances,
            lambda item: sites.get(servers.get(item.server_id).site_id).deploy_type if servers.get(item.server_id) and sites.get(servers.get(item.server_id).site_id) else "未知",
        )
        return {"groups": [{"deploy_type": key, "count": value} for key, value in counts.items()]}

    @staticmethod
    def by_provider(db: Session) -> dict[str, Any]:
        sites = {row.id: row for row in db.query(Site).all()}
        servers = {row.id: row for row in db.query(Server).all()}
        instances = db.query(DbInstance).all()
        counts = DbopsStatsService._count_by(
            instances,
            lambda item: sites.get(servers.get(item.server_id).site_id).provider if servers.get(item.server_id) and sites.get(servers.get(item.server_id).site_id) else "未知",
        )
        return {"groups": [{"provider": key, "count": value} for key, value in counts.items()]}

    @staticmethod
    def by_db_type(db: Session) -> dict[str, Any]:
        clusters = {row.id: row for row in db.query(Cluster).all()}
        counts = DbopsStatsService._count_by(
            db.query(DbInstance).all(),
            lambda item: (item.db_type.name if hasattr(item, "db_type") and item.db_type else None) or (clusters.get(item.cluster_id).db_type.name if clusters.get(item.cluster_id) and getattr(clusters.get(item.cluster_id), "db_type", None) else None) or "未知",
        )
        return {"groups": [{"db_type": key, "count": value} for key, value in counts.items()]}

    @staticmethod
    def by_system_group(db: Session) -> dict[str, Any]:
        groups = {row.id: row for row in db.query(SystemGroup).all()}
        counts = DbopsStatsService._count_by(
            db.query(BusinessSystem).all(),
            lambda item: groups.get(item.system_group_id).name if item.system_group_id and groups.get(item.system_group_id) else "未分类",
        )
        return {"groups": [{"system_group": key, "count": value} for key, value in counts.items()]}
