from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AssetVerifyLaunchRequest(BaseModel):
    check_timeout: int = Field(default=5, ge=1, le=60)
    target_host_override: Optional[str] = None
    target_port_override: Optional[int] = Field(default=None, ge=1, le=65535)


class AssetVerifyLaunchResponse(BaseModel):
    detail: str
    run_id: str
    collector_run_id: int
    instance_id: int
    awx_job_id: Optional[int] = None
    awx_job_url: Optional[str] = None
    status: str


class CollectorCallbackRequest(BaseModel):
    run_id: str = Field(min_length=1)
    asset_id: int
    asset_name: Optional[str] = None
    db_type: Optional[str] = None
    target_host: str = Field(min_length=1)
    target_port: int = Field(ge=1, le=65535)
    check_type: str = Field(default="PORT_REACHABILITY", min_length=1)
    port_reachable: Optional[bool] = None
    status: Literal["verified", "missing", "drifted"]
    error_message: Optional[str] = None
    awx_job_id: Optional[str] = None
    checked_by: Optional[str] = "awx"
    checked_at: Optional[datetime] = None


class CollectorCallbackResponse(BaseModel):
    detail: str
    run_id: str
    asset_id: int
    status: Literal["verified", "missing", "drifted"]


class CollectorRunResultResponse(BaseModel):
    run_id: str
    check_type: str
    status: str
    port_reachable: Optional[bool] = None
    target_host: str
    target_port: int
    error_message: Optional[str] = None
    awx_job_id: Optional[int] = None
    checked_by: Optional[str] = None
    checked_at: Optional[datetime] = None
    raw_result: dict[str, Any]
    created_at: Optional[datetime] = None


class CollectorRunResponse(BaseModel):
    id: int
    run_id: str
    instance_id: int
    job_type: str
    status: str
    awx_job_id: Optional[int] = None
    awx_job_url: Optional[str] = None
    awx_job_template_id: Optional[int] = None
    awx_job_template_name: Optional[str] = None
    target_host: str
    target_port: int
    callback_url: Optional[str] = None
    requested_by: Optional[str] = None
    request_payload: dict[str, Any]
    extra_vars: dict[str, Any]
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    latest_result: Optional[CollectorRunResultResponse] = None
