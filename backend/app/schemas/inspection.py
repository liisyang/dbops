"""Inspection v5.1 schemas — refactored 2026-06-25.

Design principles:
- execution_status (采集层) vs evaluation_status (规则层)
- result = task_item × task_target, UNIQUE(task_id, task_item_id, task_target_id)
- No severity column on result — health aggregation uses evaluation_status only
- Information items → not_evaluated, not counted in health score
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =========================================================================
# Inspection Item
# =========================================================================


class InspectionItemCreateRequest(BaseModel):
    item_code: str = Field(min_length=1, max_length=100)
    item_name: str = Field(min_length=1, max_length=200)
    check_code: str = Field(min_length=1, max_length=100)
    executor_type: Optional[str] = None
    target_scope: str = "db_instance"
    db_type_code: Optional[str] = None
    category: Optional[str] = None
    inspection_type: Optional[str] = None
    item_kind: str = "state"
    evaluator_type: str = "none"
    severity: str = "warning"
    weight: int = Field(default=10, ge=1, le=100)
    rule_version: Optional[str] = None
    rule_config: dict[str, Any] = Field(default_factory=dict)
    applicability: Optional[dict[str, Any]] = None
    enabled: bool = True
    description: Optional[str] = None


class InspectionItemUpdateRequest(BaseModel):
    item_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    check_code: Optional[str] = Field(default=None, min_length=1, max_length=100)
    executor_type: Optional[str] = None
    target_scope: Optional[str] = None
    db_type_code: Optional[str] = None
    category: Optional[str] = None
    inspection_type: Optional[str] = None
    item_kind: Optional[str] = None
    evaluator_type: Optional[str] = None
    severity: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=1, le=100)
    rule_version: Optional[str] = None
    rule_config: Optional[dict[str, Any]] = None
    applicability: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


class InspectionItemResponse(BaseModel):
    id: int
    item_code: str
    item_name: str
    check_code: str
    executor_type: Optional[str] = None
    target_scope: str
    db_type_code: Optional[str] = None
    category: Optional[str] = None
    inspection_type: Optional[str] = None
    item_kind: str
    evaluator_type: str
    severity: str
    weight: int = 10
    rule_version: Optional[str] = None
    rule_config: dict[str, Any] = Field(default_factory=dict)
    applicability: Optional[dict[str, Any]] = None
    enabled: bool = True
    description: Optional[str] = None
    sql_hash: Optional[str] = None
    rule_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# =========================================================================
# Inspection Task
# =========================================================================


class InspectionTaskCreateRequest(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    target_scope: str = "db_instance"
    asset_ids: Optional[list[int]] = None
    db_type_code: Optional[str] = None
    item_codes: list[str] = Field(min_length=1)
    include_related_server: bool = True
    max_items_per_dispatch: int = Field(default=100, ge=1, le=500)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    schedule_id: Optional[int] = None
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
    report_status: Optional[str] = None
    health_level: Optional[str] = None
    report_id: Optional[int] = None
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


# =========================================================================
# Inspection Result (v5.1 — execution/evaluation split, no severity)
# =========================================================================


class InspectionResultResponse(BaseModel):
    id: int
    task_id: int
    task_item_id: int
    task_target_id: int
    collector_run_id: Optional[int] = None
    collector_run_item_id: Optional[int] = None
    target_type: str
    target_id: int
    result_code: str
    execution_status: str
    evaluation_status: str
    message: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    attempt_no: int = 1
    received_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Joined from task_item
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    item_kind: Optional[str] = None
    category: Optional[str] = None

    # Joined from task_target
    target_name: Optional[str] = None


# =========================================================================
# Report (v5.1)
# =========================================================================


class InspectionReportResponse(BaseModel):
    id: int
    report_code: str
    task_id: int
    report_status: str
    health_level: Optional[str] = None
    health_score: Optional[float] = None
    total_target_count: int = 0
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    unknown_count: int = 0
    not_assessed_count: int = 0
    normal_item_count: int = 0
    warning_item_count: int = 0
    critical_item_count: int = 0
    unknown_item_count: int = 0
    collection_failed_count: int = 0
    missing_result_count: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    rule_engine_version: Optional[str] = None
    source_data_hash: Optional[str] = None
    source_result_count: int = 0
    generated_reason: str = "auto"
    generated_by: Optional[str] = None
    generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InspectionInstanceReportResponse(BaseModel):
    id: int
    report_id: int
    task_id: int
    task_target_id: int
    target_type: str
    target_id: int
    # Joined from task_target snapshot (post-verification 2026-06-26: report
    # detail table needs the host IP and DB type for at-a-glance triage).
    host_snapshot: Optional[str] = None
    db_type_code_snapshot: Optional[str] = None
    health_level: Optional[str] = None
    health_score: Optional[float] = None
    normal_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    unknown_count: int = 0
    not_evaluated_count: int = 0
    collection_failed_count: int = 0
    missing_result_count: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class InspectionReportListResponse(BaseModel):
    items: list[InspectionReportResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


# =========================================================================
# Phase 3.5: SQL validate / verify (preserved)
# =========================================================================


class ValidateSqlRequest(BaseModel):
    db_type_code: str = Field(min_length=1, max_length=50)
    sql_text: str = Field(min_length=1)


class ValidateSqlResponse(BaseModel):
    valid: bool
    sql_hash: str
    message: str
    errors: list[str] = Field(default_factory=list)


class VerifySqlRequest(BaseModel):
    instance_ids: list[int] = Field(min_length=1)
    db_type_code: str = Field(min_length=1, max_length=50)
    sql_text: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_rows: int = Field(default=200, ge=1, le=1000)


class VerifySqlResponse(BaseModel):
    verify_run_ids: list[int]
    collector_run_ids: list[str]
    status: str
    awx_job_id: Optional[int] = None
    message: Optional[str] = None


class VerifySqlResultResponse(BaseModel):
    success: bool
    verified: bool
    status: str
    sql_hash: Optional[str] = None
    duration_ms: Optional[int] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    error_code: Optional[str] = None
    connector: Optional[str] = None
