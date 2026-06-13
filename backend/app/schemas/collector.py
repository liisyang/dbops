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
    run_type: str = Field(default="asset_verify", min_length=1)
    scope: Optional[CollectorRunScopeRequest] = None
    target_scope: Optional[Literal["db_instance", "server"]] = None
    asset_ids: Optional[list[int]] = None
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
    endpoint_type: Optional[str] = None
    port_source: Optional[str] = None
    is_required: bool = False
    timeout_seconds: int
    status: str
    result_status: Optional[str] = None
    result_message: Optional[str] = None
    candidate_state: Optional[str] = None
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
    reachable: Optional[bool] = None
    port_source: Optional[str] = None
    is_required: bool = False
    last_checked_at: Optional[datetime] = None
    last_item_key: Optional[str] = None
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
    endpoint_type: Optional[str] = None
    protocol: str = Field(default="tcp", min_length=1)
    port_source: str = Field(default="unknown", min_length=1)
    is_required: bool = False
    status: Literal["verified", "missing", "drifted", "collected", "failed"]
    reachable: Optional[bool] = None
    message: Optional[str] = None
    raw_result: dict[str, Any] = Field(default_factory=dict)


class CollectorInspectionCallbackItem(BaseModel):
    item_code: str = Field(min_length=1, max_length=100)
    result_status: Literal["normal", "abnormal", "warning", "unknown"]
    target_scope: Literal["db_instance", "server"]
    asset_id: int
    severity: Literal["info", "warning", "critical"] = "warning"
    result_code: Optional[str] = None
    check_code: Optional[str] = None
    message: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class CollectorCallbackRequest(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    run_id: str = Field(min_length=1)
    awx_job_id: Optional[int] = None
    checked_by: Optional[str] = "awx"
    checked_at: Optional[datetime] = None
    items: list[CollectorCallbackItem] | None = None
    inspection_results: list[CollectorInspectionCallbackItem] | None = None

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
    endpoint_type: Optional[str] = None
    protocol: Optional[str] = None
    port_source: Optional[str] = None
    is_required: Optional[bool] = None
    error_message: Optional[str] = None
    result_message: Optional[str] = None
    candidate_state: Optional[str] = None
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
    run_type: str = "asset_verify"
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


class PortProfileResponse(BaseModel):
    id: int
    profile_code: str
    target_scope: Literal["server", "db_instance"]
    endpoint_type: str
    db_type_code: Optional[str] = None
    os_family: Optional[str] = None
    protocol: str
    default_port: int
    is_required: bool
    is_candidate: bool
    is_enabled: bool
    priority: int
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssetChangeProposalResponse(BaseModel):
    id: int
    target_type: Literal["server", "db_instance"]
    target_id: int
    proposal_type: str
    field_path: Optional[str] = None
    current_value: Any = None
    suggested_value: Any = None
    confidence: Optional[str] = None
    evidence: dict[str, Any]
    source_run_id: Optional[str] = None
    source_item_key: Optional[str] = None
    status: str
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProposalRejectRequest(BaseModel):
    reason: Optional[str] = None


# ============================================================================
# Phase 3.2 — Batch / Dispatch schemas
# ============================================================================


class BatchRunFiltersRequest(BaseModel):
    db_type_code: Optional[str] = None
    status: Optional[str] = None
    site_id: Optional[int] = None
    target_scope: Optional[Literal["server", "db_instance"]] = None


class BatchRunCreateRequest(BaseModel):
    run_type: str = Field(default="asset_verify", min_length=1)
    target_scope: Literal["db_instance", "server"]
    asset_ids: Optional[list[int]] = None
    filters: Optional[BatchRunFiltersRequest] = None
    check_codes: list[str] = Field(min_length=1)
    include_related_server: bool = True
    max_items_per_dispatch: int = Field(default=100, ge=1, le=500)
    timeout_seconds: int = Field(default=3, ge=1, le=60)


class DispatchRunSummary(BaseModel):
    dispatch_run_id: int
    dispatch_code: Optional[str] = None
    collector_run_id: Optional[int] = None
    network_zone: Optional[str] = None
    awx_instance_group: Optional[str] = None
    awx_job_template: str = "JT_DBOPS_COLLECTOR_GENERIC"
    awx_job_template_id: Optional[int] = None
    awx_job_id: Optional[int] = None
    status: str
    item_count: int = 0
    success_item_count: int = 0
    failed_item_count: int = 0
    error_message: Optional[str] = None
    launched_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class BatchRunCreateResponse(BaseModel):
    batch_run_id: int
    batch_code: str
    status: str
    run_type: str
    target_scope: str
    total_asset_count: int = 0
    total_item_count: int = 0
    dispatch_count: int = 0
    dispatches: list[DispatchRunSummary] = Field(default_factory=list)


class BatchRunResponse(BaseModel):
    id: int
    batch_code: str
    run_type: str
    target_scope: str
    status: str
    total_asset_count: int = 0
    total_item_count: int = 0
    success_item_count: int = 0
    failed_item_count: int = 0
    pending_item_count: int = 0
    running_item_count: int = 0
    skipped_item_count: int = 0
    dispatch_count: int = 0
    request_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    dispatches: list[DispatchRunSummary] = Field(default_factory=list)


class BatchRunSummary(BaseModel):
    id: int
    batch_code: str
    run_type: str
    target_scope: str
    status: str
    total_asset_count: int = 0
    total_item_count: int = 0
    success_item_count: int = 0
    failed_item_count: int = 0
    dispatch_count: int = 0
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DispatchRunResponse(BaseModel):
    id: int
    dispatch_code: Optional[str] = None
    batch_run_id: int
    collector_run_id: Optional[int] = None
    network_zone: Optional[str] = None
    awx_instance_group: Optional[str] = None
    awx_job_template: str = "JT_DBOPS_COLLECTOR_GENERIC"
    awx_job_template_id: Optional[int] = None
    awx_job_id: Optional[int] = None
    status: str
    item_count: int = 0
    success_item_count: int = 0
    failed_item_count: int = 0
    request_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    launched_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BatchRunItemResponse(BaseModel):
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
    endpoint_type: Optional[str] = None
    port_source: Optional[str] = None
    is_required: bool = False
    timeout_seconds: int
    status: str
    result_status: Optional[str] = None
    result_message: Optional[str] = None
    candidate_state: Optional[str] = None
    raw_result: dict[str, Any] = Field(default_factory=dict)
    batch_run_id: Optional[int] = None
    dispatch_run_id: Optional[int] = None
    network_zone: Optional[str] = None
    awx_instance_group: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RetryFailedRequest(BaseModel):
    scope: Literal["failed", "dispatch_failed"] = "failed"


# ============================================================================
# Phase 3.3A — Credential Profile schemas
# ============================================================================


class CredentialProfileCreate(BaseModel):
    profile_code: str = Field(min_length=1, max_length=100)
    profile_name: str = Field(min_length=1, max_length=200)
    credential_type: Literal["ssh_password", "ssh_key", "db_password", "winrm_password", "api_token"]
    awx_credential_id: Optional[int] = None
    awx_credential_name: Optional[str] = Field(default=None, max_length=200)
    binding_role: Literal["os_readonly", "db_readonly", "db_monitor", "db_owner", "db_admin"]
    db_type_code: Optional[str] = Field(default=None, max_length=50)
    os_family: Optional[str] = Field(default=None, max_length=50)
    usage_scope: Optional[Literal["server", "db_instance"]] = None
    network_zone: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[Literal["prod", "staging", "dev", "test"]] = None
    extra_attrs: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    remark: Optional[str] = None


class CredentialProfileUpdate(BaseModel):
    profile_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    credential_type: Optional[Literal["ssh_password", "ssh_key", "db_password", "winrm_password", "api_token"]] = None
    awx_credential_id: Optional[int] = None
    awx_credential_name: Optional[str] = Field(default=None, max_length=200)
    binding_role: Optional[Literal["os_readonly", "db_readonly", "db_monitor", "db_owner", "db_admin"]] = None
    db_type_code: Optional[str] = Field(default=None, max_length=50)
    os_family: Optional[str] = Field(default=None, max_length=50)
    usage_scope: Optional[Literal["server", "db_instance"]] = None
    network_zone: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[Literal["prod", "staging", "dev", "test"]] = None
    extra_attrs: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class CredentialProfileResponse(BaseModel):
    id: int
    profile_code: str
    profile_name: str
    credential_type: str
    awx_credential_id: Optional[int] = None
    awx_credential_name: Optional[str] = None
    binding_role: str
    db_type_code: Optional[str] = None
    os_family: Optional[str] = None
    usage_scope: Optional[str] = None
    network_zone: Optional[str] = None
    environment: Optional[str] = None
    extra_attrs: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Phase 3.3A — Credential Binding schemas
# ============================================================================


class CredentialBindingCreate(BaseModel):
    binding_code: str = Field(min_length=1, max_length=100)
    credential_profile_id: int
    target_type: Literal["server", "db_instance", "cluster", "business_system", "network_zone", "global"]
    target_id: Optional[int] = None
    network_zone: Optional[str] = Field(default=None, max_length=100)
    binding_role: Optional[Literal["os_readonly", "db_readonly", "db_monitor", "db_owner", "db_admin"]] = None
    priority: int = Field(default=100, ge=1, le=1000)
    is_enabled: bool = True
    extra_attrs: dict[str, Any] = Field(default_factory=dict)
    remark: Optional[str] = None


class CredentialBindingUpdate(BaseModel):
    binding_code: Optional[str] = Field(default=None, min_length=1, max_length=100)
    credential_profile_id: Optional[int] = None
    target_type: Optional[Literal["server", "db_instance", "cluster", "business_system", "network_zone", "global"]] = None
    target_id: Optional[int] = None
    network_zone: Optional[str] = Field(default=None, max_length=100)
    binding_role: Optional[Literal["os_readonly", "db_readonly", "db_monitor", "db_owner", "db_admin"]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
    is_enabled: Optional[bool] = None
    extra_attrs: Optional[dict[str, Any]] = None
    remark: Optional[str] = None


class CredentialBindingResponse(BaseModel):
    id: int
    binding_code: str
    credential_profile_id: int
    target_type: str
    target_id: Optional[int] = None
    network_zone: Optional[str] = None
    binding_role: Optional[str] = None
    priority: int = 100
    is_enabled: bool = True
    extra_attrs: dict[str, Any] = Field(default_factory=dict)
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    profile: Optional[CredentialProfileResponse] = None


# ============================================================================
# Phase 3.3A — Asset Fact schemas
# ============================================================================


class AssetFactValueResponse(BaseModel):
    id: int
    snapshot_id: int
    fact_key: str
    fact_value: Any = None
    fact_type: str = "string"
    collected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AssetFactSnapshotResponse(BaseModel):
    id: int
    snapshot_id: str
    target_type: str
    target_id: int
    source_run_id: Optional[str] = None
    source_item_key: Optional[str] = None
    check_code: Optional[str] = None
    collected_at: Optional[datetime] = None
    fact_count: int = 0
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    values: list[AssetFactValueResponse] = Field(default_factory=list)


class AssetFactSnapshotSummary(BaseModel):
    id: int
    snapshot_id: str
    target_type: str
    target_id: int
    source_run_id: Optional[str] = None
    check_code: Optional[str] = None
    collected_at: Optional[datetime] = None
    fact_count: int = 0
    created_at: Optional[datetime] = None


# ============================================================================
# Phase 3.3A — Asset Drift schemas
# ============================================================================


class AssetDriftRecordResponse(BaseModel):
    id: int
    drift_code: str
    snapshot_id: int
    target_type: str
    target_id: int
    fact_key: str
    expected_value: Any = None
    actual_value: Any = None
    drift_type: str = "mismatch"
    severity: str = "warning"
    proposal_id: Optional[int] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
