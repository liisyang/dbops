"""CollectorCheckDefinitionService — list check_code definitions from DB.

资产校验功能优化 v2 / Follow-up A / 2026-06-17:
1:1 镜像 port_profile_service.py:11-55；前端 BatchVerify.vue 通过
GET /v1/collector/check-codes 取数据，避免硬编码 7 个 check_code 列表。

I9 (PR review 2026-06-20): 继承 BaseDefinitionService，消除 1:1 克隆模板。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import CollectorCheckDefinition
from app.services._definition_service_base import BaseDefinitionService


class CollectorCheckDefinitionService(BaseDefinitionService):
    model = CollectorCheckDefinition

    @classmethod
    def _to_dict(cls, row: CollectorCheckDefinition) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "check_code": row.check_code,
            "check_name": row.check_name,
            "target_scope": row.target_scope,
            "task_type": row.task_type,
            "db_type_code": row.db_type_code,
            "os_type_code": row.os_type_code,
            "awx_role": row.awx_role,
            "default_timeout_seconds": int(row.default_timeout_seconds or 5),
            "enabled": bool(row.enabled),
            "config": row.config or {},
            "description": row.description,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @classmethod
    def _default_order_by(cls):
        return cls.model.enabled.desc(), cls.model.check_code.asc()

    @classmethod
    def list_definitions(
        cls,
        db: Session,
        *,
        target_scope: str | None = None,
        task_type: str | None = None,
        is_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List check_code definitions with optional filters."""
        # target_scope and task_type are NOT NULL in the model, so exact match is safe.
        return super().list_definitions(
            db,
            target_scope=target_scope,
            task_type=task_type,
            enabled=is_enabled,  # model column is "enabled", not "is_enabled"
        )
