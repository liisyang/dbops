from __future__ import annotations

import hmac
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.user import User
from app.schemas.collector import (
    AssetChangeProposalResponse,
    AssetDriftRecordResponse,
    AssetFactSnapshotResponse,
    AssetFactSnapshotSummary,
    AssetVerifyLaunchRequest,
    AssetVerifyLaunchResponse,
    BatchRunCreateRequest,
    BatchRunCreateResponse,
    BatchRunItemResponse,
    BatchRunResponse,
    BatchRunSummary,
    CollectorCallbackRequest,
    CollectorCallbackResponse,
    CollectorEndpointResponse,
    CredentialBindingCreate,
    CredentialBindingResponse,
    CredentialBindingUpdate,
    CredentialProfileCreate,
    CredentialProfileResponse,
    CredentialProfileUpdate,
    DispatchRunResponse,
    PortProfileResponse,
    ProposalRejectRequest,
    RetryFailedRequest,
    CollectorRunCreateRequest,
    CollectorRunCreateResponse,
    CollectorRunItemResponse,
    CollectorRunResponse,
)
from app.models.dbops_assets import (
    AssetDriftRecord,
    AssetFactSnapshot,
    AssetFactValue,
    CredentialBinding,
    CredentialProfile,
)
from app.services.asset_proposal_service import AssetProposalService
from app.services.batch_collector_service import BatchCollectorService
from app.services.collector_service import CollectorService
from app.services.port_profile_service import PortProfileService

router = APIRouter()


@router.post("/automation/asset-verify/{instance_id}/launch", response_model=AssetVerifyLaunchResponse)
async def launch_asset_verify(
    instance_id: int,
    payload: AssetVerifyLaunchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return CollectorService.launch_asset_verify(
            db,
            instance_id=instance_id,
            payload=payload,
            requested_by=current_user.username,
            request_base_url=str(request.base_url),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/collector/runs", response_model=CollectorRunCreateResponse)
async def create_collector_run(
    payload: CollectorRunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return CollectorService.launch_collector_run(
            db,
            payload=payload,
            requested_by=current_user.username,
            request_base_url=str(request.base_url),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/collector/runs/{run_id}", response_model=CollectorRunResponse)
async def get_collector_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return CollectorService.get_run(db, run_id=run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collector/runs/{run_id}/items", response_model=List[CollectorRunItemResponse])
async def list_collector_run_items(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorService.list_run_items(db, run_id=run_id)


@router.get("/collector/instances/{instance_id}/runs", response_model=List[CollectorRunResponse])
async def list_instance_collector_runs(
    instance_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorService.list_instance_runs(db, instance_id=instance_id, limit=limit)


@router.get("/collector/servers/{server_id}/runs", response_model=List[CollectorRunResponse])
async def list_server_collector_runs(
    server_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorService.list_server_runs(db, server_id=server_id, limit=limit)


@router.get("/collector/endpoints", response_model=List[CollectorEndpointResponse])
async def list_collector_endpoints(
    entity_type: Optional[str] = Query(default=None),
    entity_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorService.list_endpoints(db, entity_type=entity_type, entity_id=entity_id)


@router.get("/collector/assets/{target_scope}/{asset_id}/endpoints", response_model=List[CollectorEndpointResponse])
async def list_asset_endpoints(
    target_scope: str,
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if target_scope not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail=f"不支持的 target_scope: {target_scope}")
    return CollectorService.list_endpoints(db, entity_type=target_scope, entity_id=asset_id)


@router.get("/collector/port-profiles", response_model=List[PortProfileResponse])
async def list_port_profiles(
    target_scope: Optional[str] = Query(default=None),
    db_type_code: Optional[str] = Query(default=None),
    os_family: Optional[str] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PortProfileService.list_profiles(
        db,
        target_scope=target_scope,
        db_type_code=db_type_code,
        os_family=os_family,
        is_enabled=is_enabled,
    )


@router.get("/collector/proposals", response_model=List[AssetChangeProposalResponse])
async def list_collector_proposals(
    target_type: Optional[str] = Query(default=None),
    target_id: Optional[int] = Query(default=None),
    proposal_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return AssetProposalService.list_proposals(
        db,
        target_type=target_type,
        target_id=target_id,
        proposal_type=proposal_type,
        status=status,
    )


@router.post("/collector/proposals/{proposal_id}/approve", response_model=AssetChangeProposalResponse)
async def approve_collector_proposal(
    proposal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = AssetProposalService.approve_proposal(db, proposal_id=proposal_id, operator=current_user.username)
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/proposals/{proposal_id}/reject", response_model=AssetChangeProposalResponse)
async def reject_collector_proposal(
    proposal_id: int,
    payload: ProposalRejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = AssetProposalService.reject_proposal(
            db,
            proposal_id=proposal_id,
            operator=current_user.username,
            reason=payload.reason,
        )
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/proposals/{proposal_id}/apply", response_model=AssetChangeProposalResponse)
async def apply_collector_proposal(
    proposal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = AssetProposalService.apply_proposal(db, proposal_id=proposal_id, operator=current_user.username)
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/callback/", response_model=CollectorCallbackResponse)
async def collector_callback(
    payload: CollectorCallbackRequest,
    collector_token: Optional[str] = Header(default=None, alias="X-Collector-Token"),
    db: Session = Depends(get_db),
):
    expected_token = get_settings().COLLECTOR_CALLBACK_TOKEN
    if not collector_token or not expected_token or not hmac.compare_digest(collector_token, expected_token):
        raise HTTPException(status_code=401, detail="invalid callback token")

    try:
        return CollectorService.handle_callback(db, payload=payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================================
# Phase 3.2 — Batch run endpoints
# ============================================================================


@router.post("/collector/batch-runs", response_model=BatchRunCreateResponse)
async def create_batch_run(
    payload: BatchRunCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return BatchCollectorService.create_batch_run(
            db,
            payload=payload,
            requested_by=current_user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"内部错误: {exc}") from exc


@router.get("/collector/batch-runs", response_model=List[BatchRunSummary])
async def list_batch_runs(
    status: Optional[str] = Query(default=None),
    run_type: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = {}
    if status:
        filters["status"] = status
    if run_type:
        filters["run_type"] = run_type
    return BatchCollectorService.list_batch_runs(db, filters=filters, limit=limit)


@router.get("/collector/batch-runs/{batch_run_id}", response_model=BatchRunResponse)
async def get_batch_run(
    batch_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return BatchCollectorService.get_batch_run(db, batch_run_id=batch_run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collector/batch-runs/{batch_run_id}/dispatches", response_model=List[DispatchRunResponse])
async def list_batch_dispatches(
    batch_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BatchCollectorService.list_batch_dispatches(db, batch_run_id=batch_run_id)


@router.get("/collector/batch-runs/{batch_run_id}/items", response_model=List[BatchRunItemResponse])
async def list_batch_items(
    batch_run_id: int,
    status: Optional[str] = Query(default=None),
    check_code: Optional[str] = Query(default=None),
    target_scope: Optional[str] = Query(default=None),
    asset_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = {}
    if status:
        filters["status"] = status
    if check_code:
        filters["check_code"] = check_code
    if target_scope:
        filters["target_scope"] = target_scope
    if asset_id is not None:
        filters["asset_id"] = asset_id
    return BatchCollectorService.list_batch_items(
        db, batch_run_id=batch_run_id, filters=filters, limit=limit, offset=offset
    )


@router.post("/collector/batch-runs/{batch_run_id}/retry-failed")
async def retry_failed_batch_items(
    batch_run_id: int,
    payload: RetryFailedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return BatchCollectorService.retry_failed_items(
            db,
            batch_run_id=batch_run_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"内部错误: {exc}") from exc


# ============================================================================
# Phase 3.3A — Credential Profile endpoints
# ============================================================================


@router.get("/credentials/profiles", response_model=List[CredentialProfileResponse])
async def list_credential_profiles(
    credential_type: Optional[str] = Query(default=None),
    binding_role: Optional[str] = Query(default=None),
    db_type_code: Optional[str] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(CredentialProfile)
    if credential_type:
        query = query.filter(CredentialProfile.credential_type == credential_type)
    if binding_role:
        query = query.filter(CredentialProfile.binding_role == binding_role)
    if db_type_code:
        query = query.filter(CredentialProfile.db_type_code == db_type_code)
    if is_enabled is not None:
        query = query.filter(CredentialProfile.is_enabled == is_enabled)
    return query.order_by(CredentialProfile.id.desc()).all()


@router.post("/credentials/profiles", response_model=CredentialProfileResponse, status_code=201)
async def create_credential_profile(
    payload: CredentialProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(CredentialProfile).filter(
        CredentialProfile.profile_code == payload.profile_code
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"凭证 profile_code 已存在: {payload.profile_code}")

    profile = CredentialProfile(
        profile_code=payload.profile_code,
        profile_name=payload.profile_name,
        credential_type=payload.credential_type,
        awx_credential_id=payload.awx_credential_id,
        awx_credential_name=payload.awx_credential_name,
        binding_role=payload.binding_role,
        db_type_code=payload.db_type_code,
        os_family=payload.os_family,
        usage_scope=payload.usage_scope,
        network_zone=payload.network_zone,
        environment=payload.environment,
        extra_attrs=payload.extra_attrs,
        is_enabled=payload.is_enabled,
        remark=payload.remark,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/credentials/profiles/{profile_id}", response_model=CredentialProfileResponse)
async def update_credential_profile(
    profile_id: int,
    payload: CredentialProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(CredentialProfile).filter(CredentialProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"凭证 profile 不存在: {profile_id}")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


# ============================================================================
# Phase 3.3A — Credential Binding endpoints
# ============================================================================


@router.get("/credentials/bindings", response_model=List[CredentialBindingResponse])
async def list_credential_bindings(
    credential_profile_id: Optional[int] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    target_id: Optional[int] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(CredentialBinding)
    if credential_profile_id:
        query = query.filter(CredentialBinding.credential_profile_id == credential_profile_id)
    if target_type:
        query = query.filter(CredentialBinding.target_type == target_type)
    if target_id is not None:
        query = query.filter(CredentialBinding.target_id == target_id)
    if is_enabled is not None:
        query = query.filter(CredentialBinding.is_enabled == is_enabled)
    return query.order_by(CredentialBinding.priority.asc()).all()


@router.post("/credentials/bindings", response_model=CredentialBindingResponse, status_code=201)
async def create_credential_binding(
    payload: CredentialBindingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify profile exists
    profile = db.query(CredentialProfile).filter(
        CredentialProfile.id == payload.credential_profile_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"凭证 profile 不存在: {payload.credential_profile_id}")

    existing = db.query(CredentialBinding).filter(
        CredentialBinding.binding_code == payload.binding_code
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"绑定 binding_code 已存在: {payload.binding_code}")

    binding = CredentialBinding(
        binding_code=payload.binding_code,
        credential_profile_id=payload.credential_profile_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        network_zone=payload.network_zone,
        binding_role=payload.binding_role,
        priority=payload.priority,
        is_enabled=payload.is_enabled,
        extra_attrs=payload.extra_attrs,
        remark=payload.remark,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


@router.put("/credentials/bindings/{binding_id}", response_model=CredentialBindingResponse)
async def update_credential_binding(
    binding_id: int,
    payload: CredentialBindingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    binding = db.query(CredentialBinding).filter(CredentialBinding.id == binding_id).first()
    if not binding:
        raise HTTPException(status_code=404, detail=f"绑定不存在: {binding_id}")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(binding, key, value)
    db.commit()
    db.refresh(binding)
    return binding


@router.delete("/credentials/bindings/{binding_id}")
async def delete_credential_binding(
    binding_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    binding = db.query(CredentialBinding).filter(CredentialBinding.id == binding_id).first()
    if not binding:
        raise HTTPException(status_code=404, detail=f"绑定不存在: {binding_id}")
    db.delete(binding)
    db.commit()
    return {"detail": f"绑定 {binding_id} 已删除"}


# ============================================================================
# Phase 3.3A — Asset Fact endpoints
# ============================================================================


@router.get("/assets/{target_type}/{target_id}/facts/latest", response_model=Optional[AssetFactSnapshotResponse])
async def get_latest_asset_facts(
    target_type: str,
    target_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail=f"不支持的 target_type: {target_type}")

    snapshot = (
        db.query(AssetFactSnapshot)
        .filter(
            AssetFactSnapshot.target_type == target_type,
            AssetFactSnapshot.target_id == target_id,
        )
        .order_by(AssetFactSnapshot.collected_at.desc())
        .first()
    )
    if not snapshot:
        return None

    values = (
        db.query(AssetFactValue)
        .filter(AssetFactValue.snapshot_id == snapshot.id)
        .order_by(AssetFactValue.fact_key)
        .all()
    )
    snapshot.values = values
    return snapshot


@router.get("/assets/{target_type}/{target_id}/facts/history", response_model=List[AssetFactSnapshotSummary])
async def get_asset_fact_history(
    target_type: str,
    target_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail=f"不支持的 target_type: {target_type}")

    return (
        db.query(AssetFactSnapshot)
        .filter(
            AssetFactSnapshot.target_type == target_type,
            AssetFactSnapshot.target_id == target_id,
        )
        .order_by(AssetFactSnapshot.collected_at.desc())
        .limit(limit)
        .all()
    )


# ============================================================================
# Phase 3.3A — Asset Drift endpoints
# ============================================================================


@router.get("/assets/{target_type}/{target_id}/drifts", response_model=List[AssetDriftRecordResponse])
async def get_asset_drifts(
    target_type: str,
    target_id: int,
    is_resolved: Optional[bool] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail=f"不支持的 target_type: {target_type}")

    query = db.query(AssetDriftRecord).filter(
        AssetDriftRecord.target_type == target_type,
        AssetDriftRecord.target_id == target_id,
    )
    if is_resolved is not None:
        query = query.filter(AssetDriftRecord.is_resolved == is_resolved)
    if severity:
        query = query.filter(AssetDriftRecord.severity == severity)
    return query.order_by(AssetDriftRecord.created_at.desc()).all()


@router.get("/assets/drifts", response_model=List[AssetDriftRecordResponse])
async def list_all_asset_drifts(
    target_type: Optional[str] = Query(default=None),
    is_resolved: Optional[bool] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AssetDriftRecord)
    if target_type:
        if target_type not in ("server", "db_instance"):
            raise HTTPException(status_code=400, detail=f"不支持的 target_type: {target_type}")
        query = query.filter(AssetDriftRecord.target_type == target_type)
    if is_resolved is not None:
        query = query.filter(AssetDriftRecord.is_resolved == is_resolved)
    if severity:
        query = query.filter(AssetDriftRecord.severity == severity)
    return query.order_by(AssetDriftRecord.created_at.desc()).limit(limit).all()
