from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    AssetEventHistory,
    BusinessSystem,
    BusinessSystemContact,
    Cluster,
    ClusterVip,
    Contact,
    DbInstance,
    DbType,
    DbVersion,
    OsVersion,
    Server,
    Site,
)
from app.services.asset_event_history_service import event_to_dict, list_events, record_event


def _make_system_code(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
    return f"SYS-{digest[:12]}"


class DbopsAssetService:
    BUSINESS_LIFECYCLE_STATUS_MAP = {
        "build": "building",
        "building": "building",
        "ready": "pending",
        "pending": "pending",
        "active": "active",
        "retired": "retired",
    }

    @staticmethod
    def _make_site_code(fields: dict[str, Any]) -> str:
        seed = "|".join([
            str(fields.get("country") or "").strip(),
            str(fields.get("deploy_type") or "").strip(),
            str(fields.get("provider") or "").strip(),
            str(fields.get("factory_area") or fields.get("factory") or "").strip(),
            str(fields.get("room_location") or "").strip(),
        ])
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
        return f"SITE-{digest[:12]}"

    @staticmethod
    def upsert_site(db: Session, fields: dict[str, Any]) -> Site | None:
        has_site_fields = any(str(fields.get(key) or "").strip() for key in ["country", "deploy_type", "provider", "factory_area", "room_location"])
        if not has_site_fields:
            return None

        site_code = DbopsAssetService._make_site_code(fields)
        site = db.query(Site).filter_by(site_code=site_code).first()
        if not site:
            site = Site(
                site_code=site_code,
                country=str(fields.get("country") or "").strip() or "Unknown",
                deploy_type=str(fields.get("deploy_type") or "").strip() or "Unknown",
                provider=str(fields.get("provider") or "").strip() or "Unknown",
                factory_area=str(fields.get("factory_area") or fields.get("factory") or "").strip() or "Unknown",
                room_location=str(fields.get("room_location") or "").strip() or "",
            )
            db.add(site)
            db.flush()
        else:
            for key in ["country", "deploy_type", "provider", "factory_area", "room_location"]:
                lookup_key = "factory" if key == "factory_area" else key
                value = str(fields.get(lookup_key) or fields.get(key) or "").strip()
                if value:
                    setattr(site, key, value)
        return site

    @staticmethod
    def list_business_systems(db: Session) -> list[dict[str, Any]]:
        systems = db.query(BusinessSystem).all()
        links = db.query(BusinessSystemContact).all()
        contacts = {row.id: row for row in db.query(Contact).all()}
        clusters = db.query(Cluster).all()

        cluster_by_system: dict[int, list[Cluster]] = {}
        for cluster in clusters:
            cluster_by_system.setdefault(cluster.business_system_id, []).append(cluster)

        contact_by_system: dict[int, list[dict[str, Any]]] = {}
        for link in links:
            contact = contacts.get(link.contact_id)
            if not contact:
                continue
            contact_by_system.setdefault(link.business_system_id, []).append({
                "id": contact.id,
                "employee_no": getattr(contact, "employee_no", None),
                "contact_type": link.role_code,
                "name": contact.contact_name,
                "phone": contact.phone,
                "email": contact.email,
                "dept": contact.dept,
            })

        return [
            {
                "id": system.id,
                "system_code": system.system_code,
                "system_name": system.system_name,
                "system_group_id": system.system_group_id,
                "business_unit": system.business_unit,
                "department": system.department,
                "service_scope": system.service_scope,
                "biz_level": system.biz_level,
                "status": system.status,
                "remark": system.remark,
                "contacts": contact_by_system.get(system.id, []),
                "clusters": [
                    {
                        "id": cluster.id,
                        "cluster_code": cluster.cluster_code,
                        "cluster_name": cluster.cluster_name,
                        "cluster_type": cluster.cluster_type,
                    }
                    for cluster in cluster_by_system.get(system.id, [])
                ],
            }
            for system in systems
        ]

    @staticmethod
    def upsert_business_system(db: Session, fields: dict[str, Any], system_id: int | None = None) -> BusinessSystem:
        system_name = str(fields.get("system_name") or "").strip()
        if not system_name:
            raise ValueError("system_name is required")

        business_system = None
        if system_id is not None:
            business_system = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
        if not business_system:
            business_system = db.query(BusinessSystem).filter_by(system_name=system_name).first()

        if not business_system:
            business_system = BusinessSystem(
                system_code=_make_system_code(system_name),
                system_name=system_name,
                business_unit=str(fields.get("business_unit") or "").strip() or None,
                department=str(fields.get("department") or "").strip() or None,
                service_scope=str(fields.get("service_scope") or "").strip() or None,
                biz_level=str(fields.get("biz_level") or "").strip() or None,
                remark=str(fields.get("remark") or "").strip() or None,
                status="building",
                extra_attrs=dict(fields.get("extra_attrs") or {}),
            )
            db.add(business_system)
            db.flush()
        else:
            if "system_name" in fields and system_name:
                business_system.system_name = system_name
            if "business_unit" in fields:
                business_system.business_unit = str(fields.get("business_unit") or "").strip() or None
            if "department" in fields:
                business_system.department = str(fields.get("department") or "").strip() or None
            if "service_scope" in fields:
                business_system.service_scope = str(fields.get("service_scope") or "").strip() or None
            if "biz_level" in fields:
                business_system.biz_level = str(fields.get("biz_level") or "").strip() or None
            if "remark" in fields:
                business_system.remark = str(fields.get("remark") or "").strip() or None
            if "system_group_id" in fields:
                business_system.system_group_id = fields.get("system_group_id")
        db.commit()
        return business_system

    @staticmethod
    def upsert_business_contact_link(
        db: Session,
        business_system_id: int,
        contact_id: int,
        role_code: str,
        remark: str | None = None,
    ) -> BusinessSystemContact:
        link = db.query(BusinessSystemContact).filter_by(
            business_system_id=business_system_id,
            contact_id=contact_id,
            role_code=role_code,
        ).first()
        if not link:
            link = BusinessSystemContact(
                business_system_id=business_system_id,
                contact_id=contact_id,
                role_code=role_code,
                remark=remark,
            )
            db.add(link)
            db.flush()
        else:
            if remark is not None:
                link.remark = remark
        db.commit()
        return link

    @staticmethod
    def delete_business_contact_link(
        db: Session,
        business_system_id: int,
        contact_id: int,
        role_code: str,
    ) -> bool:
        link = db.query(BusinessSystemContact).filter_by(
            business_system_id=business_system_id,
            contact_id=contact_id,
            role_code=role_code,
        ).first()
        if not link:
            return False
        db.delete(link)
        db.commit()
        return True

    @staticmethod
    def get_business_system_detail(db: Session, system_id: int) -> dict[str, Any] | None:
        for row in DbopsAssetService.list_business_systems(db):
            if row["id"] == system_id:
                row["lifecycle"] = {
                    "history": [
                        event_to_dict(event)
                        for event in DbopsAssetService.list_business_lifecycle_history(db, system_id)
                    ],
                }
                return row
        return None

    @staticmethod
    def list_business_lifecycle_history(db: Session, system_id: int) -> list[AssetEventHistory]:
        return list_events(db, asset_type="business_system", asset_id=system_id)

    @staticmethod
    def change_business_status(
        db: Session,
        system_id: int,
        action: str,
        reason: str | None = None,
        remark: str | None = None,
        operator: str | None = None,
        lifecycle_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        system = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
        if not system:
            return None

        normalized_action = str(action or "").strip().lower()
        status_map = DbopsAssetService.BUSINESS_LIFECYCLE_STATUS_MAP
        if normalized_action not in status_map:
            raise ValueError(f"unsupported business lifecycle action: {action}")

        before_status = system.status
        after_status = status_map[normalized_action]
        system.status = after_status

        context_snapshot = dict(lifecycle_context or {})
        lifecycle_snapshot = {
            "action": normalized_action,
            "before_status": before_status,
            "after_status": after_status,
            "reason": reason,
            "remark": remark,
            "operator": operator,
            "context": context_snapshot,
        }

        extra_attrs = dict(system.extra_attrs or {})
        extra_attrs["lifecycle_context"] = lifecycle_snapshot
        system.extra_attrs = extra_attrs

        history = record_event(
            db,
            asset_type="business_system",
            asset_id=system.id,
            event_type=f"business.{normalized_action}",
            before_status=before_status,
            after_status=after_status,
            changed_fields=lifecycle_snapshot,
            reason=reason,
            operator=operator,
            remark=remark,
        )
        db.commit()
        return {
            "business_system": system,
            "history": history,
        }

    @staticmethod
    def list_clusters(db: Session) -> list[dict[str, Any]]:
        clusters = db.query(Cluster).all()
        vips = db.query(ClusterVip).all()
        instances = db.query(DbInstance).all()
        systems = {row.id: row for row in db.query(BusinessSystem).all()}

        vip_map: dict[int, list[str]] = {}
        for vip in vips:
            vip_map.setdefault(vip.cluster_id, []).append(vip.vip_address)

        instance_map: dict[int, list[DbInstance]] = {}
        for instance in instances:
            instance_map.setdefault(instance.cluster_id, []).append(instance)

        rows: list[dict[str, Any]] = []
        for cluster in clusters:
            cluster_instances = instance_map.get(cluster.id, [])
            system = systems.get(cluster.business_system_id)
            rows.append({
                "id": cluster.id,
                "cluster_code": cluster.cluster_code,
                "cluster_name": cluster.cluster_name,
                "cluster_type": cluster.cluster_type,
                "business_system_id": cluster.business_system_id,
                "business_system_name": system.system_name if system else None,
                "source_cluster_no": (cluster.extra_attrs or {}).get("source_cluster_no"),
                "vip_addresses": vip_map.get(cluster.id, []),
                "instance_count": len(cluster_instances),
                "roles": sorted({item.node_role for item in cluster_instances}),
            })
        return rows

    @staticmethod
    def get_cluster_detail(db: Session, cluster_id: int) -> dict[str, Any] | None:
        clusters = {row["id"]: row for row in DbopsAssetService.list_clusters(db)}
        cluster = clusters.get(cluster_id)
        if not cluster:
            return None
        cluster["instances"] = DbopsAssetService.list_instances_by_cluster(db, cluster_id)
        return cluster

    @staticmethod
    def list_instances_by_cluster(db: Session, cluster_id: int) -> list[dict[str, Any]]:
        return [row for row in DbopsAssetService.list_instances(db) if row["cluster_id"] == cluster_id]

    @staticmethod
    def list_instances(db: Session) -> list[dict[str, Any]]:
        instances = db.query(DbInstance).all()
        clusters = {row.id: row for row in db.query(Cluster).all()}
        servers = {row.id: row for row in db.query(Server).all()}
        sites = {row.id: row for row in db.query(Site).all()}
        db_types = {row.id: row for row in db.query(DbType).all()}
        db_versions = {row.id: row for row in db.query(DbVersion).all()}
        business_systems = {row.id: row for row in db.query(BusinessSystem).all()}

        rows: list[dict[str, Any]] = []
        for instance in instances:
            cluster = clusters.get(instance.cluster_id)
            server = servers.get(instance.server_id)
            site = sites.get(server.site_id) if server else None
            db_type = db_types.get(instance.db_type_id)
            db_version = db_versions.get(instance.db_version_id) if instance.db_version_id else None
            biz_system = business_systems.get(cluster.business_system_id) if cluster else None
            rows.append({
                "id": instance.id,
                "instance_code": instance.instance_code,
                "instance_name": instance.instance_name,
                "cluster_id": instance.cluster_id,
                "cluster_code": cluster.cluster_code if cluster else None,
                "cluster_name": cluster.cluster_name if cluster else None,
                "db_type": db_type.name if db_type else None,
                "db_version": db_version.version_name if db_version else None,
                "node_role": instance.node_role,
                "engine_role": (instance.extra_attrs or {}).get("engine_role"),
                "source_node_role": (instance.extra_attrs or {}).get("source_node_role"),
                "server_id": instance.server_id,
                "server_ip": server.ip_address if server else None,
                "hostname": server.hostname if server else None,
                "country": site.country if site else None,
                "factory_area": site.factory_area if site else None,
                "room_location": site.room_location if site else None,
                "deploy_type": site.deploy_type if site else None,
                "provider": site.provider if site else None,
                "system_name": biz_system.system_name if biz_system else None,
            })
        return rows

    @staticmethod
    def get_instance_detail(db: Session, instance_id: int) -> dict[str, Any] | None:
        for row in DbopsAssetService.list_instances(db):
            if row["id"] == instance_id:
                return row
        return None

    @staticmethod
    def list_servers(db: Session) -> list[dict[str, Any]]:
        servers = db.query(Server).all()
        sites = {row.id: row for row in db.query(Site).all()}
        os_versions = {row.id: row for row in db.query(OsVersion).all()}
        instances = db.query(DbInstance).all()

        instance_map: dict[int, list[DbInstance]] = {}
        for instance in instances:
            instance_map.setdefault(instance.server_id, []).append(instance)

        rows: list[dict[str, Any]] = []
        for server in servers:
            site = sites.get(server.site_id)
            os_version = os_versions.get(server.os_version_id) if server.os_version_id else None
            rows.append({
                "id": server.id,
                "server_code": server.server_code,
                "ip_address": server.ip_address,
                "hostname": server.hostname,
                "dns_name": server.dns_name,
                "server_type": server.server_type,
                "cpu_cores": server.cpu_cores,
                "memory_gb": server.memory_gb,
                "disk_gb": server.disk_gb,
                "business_group": server.business_group,
                "os_name": os_version.os_name if os_version else None,
                "os_version": os_version.version_name if os_version else None,
                "country": site.country if site else None,
                "factory_area": site.factory_area if site else None,
                "deploy_type": site.deploy_type if site else None,
                "provider": site.provider if site else None,
                "room_location": site.room_location if site else None,
                "instance_count": len(instance_map.get(server.id, [])),
            })
        return rows

    @staticmethod
    def create_server(db: Session, data: dict[str, Any]) -> int:
        site = DbopsAssetService.upsert_site(db, data)
        server = Server(
            server_code=str(data.get("server_code") or f"SRV-{hashlib.sha1(str(data.get('ip_address') or data.get('ip') or '').encode('utf-8')).hexdigest().upper()[:12]}"),
            hostname=data.get("hostname"),
            ip_address=data.get("ip_address") or data.get("ip"),
            site_id=site.id if site else None,
            cpu_cores=data.get("cpu_cores"),
            memory_gb=data.get("memory_gb"),
            disk_gb=data.get("disk_gb"),
            server_type=data.get("server_type") or data.get("host_type"),
            business_group=data.get("business_group"),
            status=data.get("status") or "building",
            extra_attrs=data.get("extra_attrs") or {},
        )
        db.add(server)
        db.commit()
        return int(server.id)

    @staticmethod
    def update_server(db: Session, server_id: int, data: dict[str, Any]) -> bool:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return False
        site = server.site
        if not site and server.site_id:
            site = db.query(Site).filter_by(id=server.site_id).first()
        for field in ["hostname", "cpu_cores", "memory_gb", "disk_gb", "business_group", "status"]:
            if field in data:
                setattr(server, field, data.get(field))
        if "ip" in data or "ip_address" in data:
            server.ip_address = data.get("ip_address") or data.get("ip")
        if "server_type" in data or "host_type" in data:
            server.server_type = data.get("server_type") or data.get("host_type")
        site_keys = {"country", "deploy_type", "provider", "factory_area", "room_location"}
        if any(key in data for key in site_keys):
            if site:
                for key, lookup_key in [
                    ("country", "country"),
                    ("deploy_type", "deploy_type"),
                    ("provider", "provider"),
                    ("factory_area", "factory_area"),
                    ("room_location", "room_location"),
                ]:
                    value = data.get(lookup_key) or (data.get("factory") if key == "factory_area" else None)
                    if value:
                        setattr(site, key, value)
            else:
                merged = {
                    "country": data.get("country"),
                    "deploy_type": data.get("deploy_type"),
                    "provider": data.get("provider"),
                    "factory_area": data.get("factory_area") or data.get("factory"),
                    "room_location": data.get("room_location"),
                }
                site = DbopsAssetService.upsert_site(db, merged)
                if site:
                    server.site_id = site.id
        db.commit()
        return True

    @staticmethod
    def delete_server(db: Session, server_id: int) -> bool:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return False
        db.delete(server)
        db.commit()
        return True

    @staticmethod
    def get_server_detail(db: Session, server_id: int) -> dict[str, Any] | None:
        for row in DbopsAssetService.list_servers(db):
            if row["id"] == server_id:
                row["instances"] = [item for item in DbopsAssetService.list_instances(db) if item["server_id"] == server_id]
                return row
        return None

    @staticmethod
    def list_db_types(db: Session) -> list[dict[str, Any]]:
        rows = db.query(DbType).filter(DbType.is_active == True).all()
        return [{"id": row.id, "name": row.name, "type_code": row.type_code} for row in rows]

    @staticmethod
    def list_servers_for_dropdown(db: Session) -> list[dict[str, Any]]:
        rows = db.query(Server).all()
        return [{"id": row.id, "hostname": row.hostname or row.server_code, "server_code": row.server_code} for row in rows]

    @staticmethod
    def upsert_cluster(db: Session, fields: dict[str, Any], cluster_id: int | None = None) -> Cluster:
        cluster_name = str(fields.get("cluster_name") or "").strip()
        if not cluster_name:
            raise ValueError("cluster_name is required")

        business_system_id = fields.get("business_system_id")
        if not business_system_id:
            raise ValueError("business_system_id is required")

        db_type_id = fields.get("db_type_id")
        if not db_type_id:
            raise ValueError("db_type_id is required")

        cluster_type = str(fields.get("cluster_type") or "").strip()
        if not cluster_type:
            raise ValueError("cluster_type is required")

        cluster = None
        if cluster_id is not None:
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

        if not cluster:
            db_type = db.query(DbType).filter(DbType.id == db_type_id).first()
            db_type_name = db_type.type_code if db_type else "UNKNOWN"
            seed = f"{cluster_name}|{db_type_name}|{cluster_type}"
            digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
            cluster_code = f"CLU-{db_type_name}-{cluster_type}-{digest[:10]}"
            cluster = Cluster(
                cluster_code=cluster_code,
                cluster_name=cluster_name,
                business_system_id=int(business_system_id),
                db_type_id=int(db_type_id),
                cluster_type=cluster_type,
                ha_enabled=cluster_type != "SINGLE",
                status=str(fields.get("status") or "active").strip(),
                remark=str(fields.get("remark") or "").strip() or None,
                extra_attrs={},
            )
            db.add(cluster)
        else:
            cluster.cluster_name = cluster_name
            cluster.business_system_id = int(business_system_id)
            cluster.db_type_id = int(db_type_id)
            cluster.cluster_type = cluster_type
            if "status" in fields:
                cluster.status = str(fields.get("status") or "active").strip()
            if "remark" in fields:
                cluster.remark = str(fields.get("remark") or "").strip() or None

        db.commit()

        # sync vip_addresses if provided in fields
        if "vip_addresses" in fields:
            vips = [v.strip() for v in (fields.get("vip_addresses") or []) if str(v).strip()]
            db.query(ClusterVip).filter(ClusterVip.cluster_id == cluster.id).delete()
            for vip in vips:
                db.add(ClusterVip(cluster_id=cluster.id, vip_address=vip))
            db.commit()

        return cluster

    @staticmethod
    def delete_cluster(db: Session, cluster_id: int) -> bool:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return False
        instance_count = db.query(DbInstance).filter(DbInstance.cluster_id == cluster_id).count()
        if instance_count > 0:
            raise ValueError(f"集群下存在 {instance_count} 个实例，无法删除")
        db.delete(cluster)
        db.commit()
        return True

    @staticmethod
    def upsert_dbinstance(db: Session, fields: dict[str, Any], instance_id: int | None = None) -> DbInstance:
        instance_name = str(fields.get("instance_name") or "").strip()
        if not instance_name:
            raise ValueError("instance_name is required")

        cluster_id = fields.get("cluster_id")
        if not cluster_id:
            raise ValueError("cluster_id is required")

        db_type_id = fields.get("db_type_id")
        if not db_type_id:
            raise ValueError("db_type_id is required")

        server_id = fields.get("server_id")
        if not server_id:
            raise ValueError("server_id is required")

        node_role = str(fields.get("node_role") or "unknown").strip()

        instance = None
        if instance_id is not None:
            instance = db.query(DbInstance).filter(DbInstance.id == instance_id).first()

        if not instance:
            digest = hashlib.sha1(instance_name.encode("utf-8")).hexdigest().upper()
            instance_code = f"INS-{digest[:12]}"
            instance = DbInstance(
                instance_code=instance_code,
                instance_name=instance_name,
                cluster_id=int(cluster_id),
                db_type_id=int(db_type_id),
                server_id=int(server_id),
                db_version_id=fields.get("db_version_id") or None,
                node_role=node_role,
                service_name=str(fields.get("service_name") or "").strip() or None,
                status=str(fields.get("status") or "active").strip(),
                remark=str(fields.get("remark") or "").strip() or None,
                extra_attrs={},
            )
            db.add(instance)
        else:
            instance.instance_name = instance_name
            instance.cluster_id = int(cluster_id)
            instance.db_type_id = int(db_type_id)
            instance.server_id = int(server_id)
            instance.node_role = node_role
            if "db_version_id" in fields:
                instance.db_version_id = fields.get("db_version_id") or None
            if "service_name" in fields:
                instance.service_name = str(fields.get("service_name") or "").strip() or None
            if "status" in fields:
                instance.status = str(fields.get("status") or "active").strip()
            if "remark" in fields:
                instance.remark = str(fields.get("remark") or "").strip() or None

        db.commit()
        return instance

    @staticmethod
    def delete_dbinstance(db: Session, instance_id: int) -> bool:
        instance = db.query(DbInstance).filter(DbInstance.id == instance_id).first()
        if not instance:
            return False
        db.delete(instance)
        db.commit()
        return True
