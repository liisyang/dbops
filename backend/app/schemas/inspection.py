from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class InspectionItemCreateRequest(BaseModel):
    item_code: str = Field(min_length=1, max_length=100)
    item_name: str = Field(min_length=1, max_length=200)
    check_code: str = Field(min_length=1, max_length=100)
    target_scope: Literal["server", "db_instance"] = "db_instance"
    severity: Literal["info", "warning", "critical"] = "warning"
    enabled: bool = True
    description: Optional[str] = None
    rule_config: dict[str, Any] = Field(default_factory=dict)


class InspectionItemUpdateRequest(BaseModel):
    item_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    check_code: Optional[str] = Field(default=None, min_length=1, max_length=100)
    target_scope: Optional[Literal["server", "db_instance"]] = None
    severity: Optional[Literal["info", "warning", "critical"]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    rule_config: Optional[dict[str, Any]] = None


class InspectionItemResponse(BaseModel):
    id: int
    item_code: str
    item_name: str
    check_code: str
    target_scope: str
    severity: str
    enabled: bool
    description: Optional[str] = None
    rule_config: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InspectionTaskCreateRequest(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    target_scope: Literal["server", "db_instance"]
    asset_ids: Optional[list[int]] = None
    db_type_code: Optional[str] = None
    item_codes: list[str] = Field(min_length=1)
    include_related_server: bool = True
    max_items_per_dispatch: int = Field(default=100, ge=1, le=500)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    schedule_id: Optional[int] = None
    # Phase 3.4 fleet-scan footgun guard:
    # when neither asset_ids nor db_type_code is set, the service falls back to
    # "scan every asset in the scope" — a request that is easy to send by
    # accident. The caller MUST pass confirm_fleet_scan=true to opt in.
    confirm_fleet_scan: bool = False
    request_payload: dict[str, Any] = Field(default_factory=dict)


class InspectionTaskResponse(BaseModel):
    id: int
    task_code: str
    task_name: str
    run_type: str
    target_scope: str
    status: str
    schedule_id: Optional[int] = None
    batch_run_id: Optional[int] = None
    check_codes: list[str] = Field(default_factory=list)
    item_codes: list[str] = Field(default_factory=list)
    asset_ids: list[int] = Field(default_factory=list)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InspectionTaskCreateResponse(BaseModel):
    detail: str
    task_id: int
    task_code: str
    batch_run_id: int
    status: str
    dispatch_count: int = 0
    total_item_count: int = 0


class InspectionResultResponse(BaseModel):
    id: int
    task_id: int
    item_id: Optional[int] = None
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    batch_run_id: Optional[int] = None
    collector_run_id: Optional[int] = None
    collector_run_item_id: Optional[int] = None
    target_type: str
    target_id: int
    result_code: str
    result_status: str
    severity: str
    message: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
