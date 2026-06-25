"""Pydantic schemas for backup status endpoints (Phase 3.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request: launch a backup status collect
# ---------------------------------------------------------------------------


class BackupCollectRequest(BaseModel):
    instance_ids: list[int] = Field(min_length=1, max_length=200)
    db_type_code: str = Field(min_length=1, max_length=50)
    backup_type: Optional[str] = Field(default=None, max_length=50)
    sql_text: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_rows: int = Field(default=200, ge=1, le=1000)


class BackupCollectResponse(BaseModel):
    collector_run_id: int
    status: str
    awx_job_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Latest backup status (joined with db_instance/db_type/server)
# ---------------------------------------------------------------------------


class BackupStatusLatestItem(BaseModel):
    id: int
    instance_id: int
    instance_name: str
    db_type_code: str
    host: str
    port: int
    backup_type: Optional[str] = None
    source_type: str
    last_status: str
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    recovery_point_at: Optional[datetime] = None
    age_minutes: Optional[int] = None
    duration_seconds: Optional[int] = None
    backup_size_mb: Optional[float] = None
    message: Optional[str] = None
    collected_at: datetime
    collector_run_id: Optional[int] = None
    collector_run_item_id: Optional[int] = None


# ---------------------------------------------------------------------------
# History (raw snapshot rows)
# ---------------------------------------------------------------------------


class BackupStatusHistoryItem(BaseModel):
    id: int
    instance_id: int
    backup_type: Optional[str] = None
    source_type: str
    last_status: str
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    recovery_point_at: Optional[datetime] = None
    age_minutes: Optional[int] = None
    duration_seconds: Optional[int] = None
    backup_size_mb: Optional[float] = None
    message: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Validate-SQL (defensive; same gate as inspection)
# ---------------------------------------------------------------------------


class ValidateBackupSqlRequest(BaseModel):
    db_type_code: str = Field(min_length=1, max_length=50)
    sql_text: str = Field(min_length=1)


class ValidateBackupSqlResponse(BaseModel):
    valid: bool
    sql_hash: str
    message: str
    errors: list[str] = Field(default_factory=list)
