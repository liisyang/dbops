from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dbops_assets import PortProfile


class PortProfileService:
    @staticmethod
    def _profile_to_dict(profile: PortProfile) -> dict[str, Any]:
        return {
            "id": int(profile.id),
            "profile_code": profile.profile_code,
            "target_scope": profile.target_scope,
            "endpoint_type": profile.endpoint_type,
            "db_type_code": profile.db_type_code,
            "os_family": profile.os_family,
            "protocol": profile.protocol,
            "default_port": int(profile.default_port),
            "is_required": bool(profile.is_required),
            "is_candidate": bool(profile.is_candidate),
            "is_enabled": bool(profile.is_enabled),
            "priority": int(profile.priority or 100),
            "remark": profile.remark,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    @staticmethod
    def list_profiles(
        db: Session,
        *,
        target_scope: str | None = None,
        db_type_code: str | None = None,
        os_family: str | None = None,
        is_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        query = db.query(PortProfile)
        if target_scope:
            query = query.filter(PortProfile.target_scope == target_scope)
        if db_type_code is not None:
            query = query.filter(
                or_(PortProfile.db_type_code.is_(None), PortProfile.db_type_code == db_type_code)
            )
        if os_family is not None:
            query = query.filter(
                or_(PortProfile.os_family.is_(None), PortProfile.os_family == os_family)
            )
        if is_enabled is not None:
            query = query.filter(PortProfile.is_enabled == is_enabled)
        rows = query.order_by(PortProfile.priority.asc(), PortProfile.id.asc()).all()
        return [PortProfileService._profile_to_dict(row) for row in rows]

    @staticmethod
    def get_candidate_ports(
        db: Session,
        *,
        target_scope: str,
        db_type_code: str | None = None,
        os_family: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = PortProfileService.list_profiles(
            db,
            target_scope=target_scope,
            db_type_code=db_type_code,
            os_family=os_family,
            is_enabled=True,
        )
        return [row for row in rows if row["is_candidate"]]
