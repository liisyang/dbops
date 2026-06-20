from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dbops_assets import PortProfile
from app.services._definition_service_base import BaseDefinitionService


class PortProfileService(BaseDefinitionService):
    """I9 (PR review 2026-06-20): 继承 BaseDefinitionService 消除 1:1 克隆。"""

    model = PortProfile

    @classmethod
    def _to_dict(cls, row: PortProfile) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "profile_code": row.profile_code,
            "target_scope": row.target_scope,
            "endpoint_type": row.endpoint_type,
            "db_type_code": row.db_type_code,
            "os_family": row.os_family,
            "protocol": row.protocol,
            "default_port": int(row.default_port),
            "is_required": bool(row.is_required),
            "is_candidate": bool(row.is_candidate),
            "is_enabled": bool(row.is_enabled),
            "priority": int(row.priority or 100),
            "remark": row.remark,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @classmethod
    def _default_order_by(cls):
        return cls.model.priority.asc(), cls.model.id.asc()

    @classmethod
    def list_profiles(
        cls,
        db: Session,
        *,
        target_scope: str | None = None,
        db_type_code: str | None = None,
        os_family: str | None = None,
        is_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List port profiles with optional filters.

        Uses or_() for db_type_code / os_family so NULL (wildcard) rows also match.
        """
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
        rows = query.order_by(cls._default_order_by()).all()
        return [cls._to_dict(row) for row in rows]

    @classmethod
    def get_candidate_ports(
        cls,
        db: Session,
        *,
        target_scope: str,
        db_type_code: str | None = None,
        os_family: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = cls.list_profiles(
            db,
            target_scope=target_scope,
            db_type_code=db_type_code,
            os_family=os_family,
            is_enabled=True,
        )
        return [row for row in rows if row["is_candidate"]]
