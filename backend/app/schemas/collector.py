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


class CollectorRunScopeRequest(BaseModel):
    target_scope: Literal["db_instance", "server"]
    asset_ids: list[int] = Field(min_length=1)


class CollectorRunCreateRequest(BaseModel):
    scope: CollectorRunScopeRequest
    check_codes: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class CollectorRunCreateResponse(BaseModel):
    detail: str
    run_id: str
    collector_run_id: int
    awx_job_id: Optional[int] = None
    awx_job_url: Optional[str] = None
    status: str
    item_count: int


class CollectorRunItemResponse(BaseModel):
    id: int
    collector_run_id: int
    run_id: str
    item_key: str
    check_code: str
    target_scope: Literal["db_instance", "server"]
    server_id: Optional[int] = None
    db_instance_id: Optional[int] = None
    target_host: str
    target_port: int
    protocol: str
    timeout_seconds: int
    status: str
    result_status: Optional[str] = None
    result_message: Optional[str] = None
    raw_result: dict[str, Any]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CollectorEndpointResponse(BaseModel):
    id: int
    entity_type: Literal["server", "db_instance"]
    entity_id: int
    endpoint_type: str
    host: str
    port: int
    protocol: str
    source: str
    expected: bool
    status: str
    last_seen_at: Optional[datetime] = None
    last_verify_at: Optional[datetime] = None
    last_run_id: Optional[str] = None
    last_message: Optional[str] = None
    evidence: dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CollectorCallbackItem(BaseModel):
    item_key: str = Field(min_length=1)
    check_code: str = Field(min_length=1)
    target_scope: Literal["db_instance", "server"]
    asset_id: int
    target_host: str = Field(min_length=1)
    target_port: int = Field(ge=1, le=65535)
    status: Literal["verified", "missing", "drifted", "collected", "failed"]
    reachable: Optional[bool] = None
    message: Optional[str] = None
    raw_result: dict[str, Any] = Field(default_factory=dict)


class CollectorCallbackRequest(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    run_id: str = Field(min_length=1)
    awx_job_id: Optional[int] = None
    checked_by: Optional[str] = "awx"
    checked_at: Optional[datetime] = None
    items: list[CollectorCallbackItem] | None = None

    # 兼容旧单结果协议：新 callback 未到位时仍可先回写单条结果。
    asset_id: Optional[int] = None
    asset_name: Optional[str] = None
    db_type: Optional[str] = None
    target_scope: Optional[Literal["db_instance", "server"]] = None
    target_host: Optional[str] = None
    target_port: Optional[int] = Field(default=None, ge=1, le=65535)
    check_type: Optional[str] = Field(default=None, min_length=1)
    port_reachable: Optional[bool] = None
    status: Optional[Literal["verified", "missing", "drifted"]] = None
    error_message: Optional[str] = None


class CollectorCallbackResponse(BaseModel):
    detail: str
    run_id: str
    status: str
    item_count: int = 0


class CollectorRunResultResponse(BaseModel):
    run_id: str
    item_key: str
    check_code: str
    target_scope: Literal["db_instance", "server"]
    status: str
    port_reachable: Optional[bool] = None
    target_host: str
    target_port: int
    error_message: Optional[str] = None
    result_message: Optional[str] = None
    awx_job_id: Optional[int] = None
    checked_by: Optional[str] = None
    checked_at: Optional[datetime] = None
    raw_result: dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CollectorRunResponse(BaseModel):
    id: int
    run_id: str
    target_scope: str
    instance_id: Optional[int] = None
    server_id: Optional[int] = None
    job_type: str
    status: str
    item_count: int = 0
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
    items: list[CollectorRunItemResponse] = Field(default_factory=list)
