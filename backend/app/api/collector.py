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
    AssetDriftsResponse,
    AssetFactSnapshotResponse,
    AssetFactValueResponse,
    AssetFactsHistoryResponse,
    AssetFactsLatestResponse,
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
    db_type_code: Optional[str] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialProfile as CredentialProfileModel

    query = db.query(CredentialProfileModel)
    if credential_type:
        query = query.filter(CredentialProfileModel.credential_type == credential_type)
    if db_type_code:
        query = query.filter(CredentialProfileModel.db_type_code == db_type_code)
    if is_enabled is not None:
        query = query.filter(CredentialProfileModel.is_enabled == is_enabled)
    rows = query.order_by(CredentialProfileModel.created_at.desc()).all()
    return [
        CredentialProfileResponse(
            id=int(r.id),
            profile_code=r.profile_code,
            profile_name=r.profile_name,
            credential_type=r.credential_type,
            awx_credential_id=r.awx_credential_id,
            awx_credential_name=r.awx_credential_name,
            db_type_code=r.db_type_code,
            os_family=r.os_family,
            default_database=r.default_database,
            is_enabled=bool(r.is_enabled),
            remark=r.remark,
            extra_attrs=r.extra_attrs or {},
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/credentials/profiles", response_model=CredentialProfileResponse)
async def create_credential_profile(
    payload: CredentialProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialProfile as CredentialProfileModel

    existing = db.query(CredentialProfileModel).filter(
        CredentialProfileModel.profile_code == payload.profile_code
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="profile_code 已存在")

    profile = CredentialProfileModel(
        profile_code=payload.profile_code,
        profile_name=payload.profile_name,
        credential_type=payload.credential_type,
        awx_credential_id=payload.awx_credential_id,
        awx_credential_name=payload.awx_credential_name,
        db_type_code=payload.db_type_code,
        os_family=payload.os_family,
        default_database=payload.default_database,
        is_enabled=payload.is_enabled,
        remark=payload.remark,
        extra_attrs=payload.extra_attrs,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return CredentialProfileResponse(
        id=int(profile.id),
        profile_code=profile.profile_code,
        profile_name=profile.profile_name,
        credential_type=profile.credential_type,
        awx_credential_id=profile.awx_credential_id,
        awx_credential_name=profile.awx_credential_name,
        db_type_code=profile.db_type_code,
        os_family=profile.os_family,
        default_database=profile.default_database,
        is_enabled=bool(profile.is_enabled),
        remark=profile.remark,
        extra_attrs=profile.extra_attrs or {},
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/credentials/profiles/{profile_id}", response_model=CredentialProfileResponse)
async def update_credential_profile(
    profile_id: int,
    payload: CredentialProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialProfile as CredentialProfileModel

    profile = db.query(CredentialProfileModel).filter(CredentialProfileModel.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="profile 不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return CredentialProfileResponse(
        id=int(profile.id),
        profile_code=profile.profile_code,
        profile_name=profile.profile_name,
        credential_type=profile.credential_type,
        awx_credential_id=profile.awx_credential_id,
        awx_credential_name=profile.awx_credential_name,
        db_type_code=profile.db_type_code,
        os_family=profile.os_family,
        default_database=profile.default_database,
        is_enabled=bool(profile.is_enabled),
        remark=profile.remark,
        extra_attrs=profile.extra_attrs or {},
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ============================================================================
# Phase 3.3A — Credential Binding endpoints
# ============================================================================


@router.get("/credentials/bindings", response_model=List[CredentialBindingResponse])
async def list_credential_bindings(
    profile_id: Optional[int] = Query(default=None, ge=1),
    binding_role: Optional[str] = Query(default=None),
    binding_target_type: Optional[str] = Query(default=None),
    binding_target_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialBinding as CredentialBindingModel

    query = db.query(CredentialBindingModel)
    if profile_id:
        query = query.filter(CredentialBindingModel.profile_id == profile_id)
    if binding_role:
        query = query.filter(CredentialBindingModel.binding_role == binding_role)
    if binding_target_type:
        query = query.filter(CredentialBindingModel.binding_target_type == binding_target_type)
    if binding_target_id:
        query = query.filter(CredentialBindingModel.binding_target_id == binding_target_id)
    rows = query.order_by(CredentialBindingModel.priority.asc(), CredentialBindingModel.created_at.desc()).all()
    return [
        CredentialBindingResponse(
            id=int(r.id),
            profile_id=int(r.profile_id),
            binding_role=r.binding_role,
            binding_target_type=r.binding_target_type,
            binding_target_id=r.binding_target_id,
            network_zone=r.network_zone,
            priority=r.priority,
            is_enabled=bool(r.is_enabled),
            remark=r.remark,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/credentials/bindings", response_model=CredentialBindingResponse)
async def create_credential_binding(
    payload: CredentialBindingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialBinding as CredentialBindingModel
    from app.models.dbops_assets import CredentialProfile as CredentialProfileModel

    profile = db.query(CredentialProfileModel).filter(CredentialProfileModel.id == payload.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="credential profile 不存在")

    binding = CredentialBindingModel(
        profile_id=payload.profile_id,
        binding_role=payload.binding_role,
        binding_target_type=payload.binding_target_type,
        binding_target_id=payload.binding_target_id,
        network_zone=payload.network_zone,
        priority=payload.priority,
        is_enabled=payload.is_enabled,
        remark=payload.remark,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return CredentialBindingResponse(
        id=int(binding.id),
        profile_id=int(binding.profile_id),
        binding_role=binding.binding_role,
        binding_target_type=binding.binding_target_type,
        binding_target_id=binding.binding_target_id,
        network_zone=binding.network_zone,
        priority=binding.priority,
        is_enabled=bool(binding.is_enabled),
        remark=binding.remark,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


@router.put("/credentials/bindings/{binding_id}", response_model=CredentialBindingResponse)
async def update_credential_binding(
    binding_id: int,
    payload: CredentialBindingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialBinding as CredentialBindingModel

    binding = db.query(CredentialBindingModel).filter(CredentialBindingModel.id == binding_id).first()
    if not binding:
        raise HTTPException(status_code=404, detail="binding 不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(binding, key, value)

    db.commit()
    db.refresh(binding)
    return CredentialBindingResponse(
        id=int(binding.id),
        profile_id=int(binding.profile_id),
        binding_role=binding.binding_role,
        binding_target_type=binding.binding_target_type,
        binding_target_id=binding.binding_target_id,
        network_zone=binding.network_zone,
        priority=binding.priority,
        is_enabled=bool(binding.is_enabled),
        remark=binding.remark,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


@router.delete("/credentials/bindings/{binding_id}")
async def delete_credential_binding(
    binding_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import CredentialBinding as CredentialBindingModel

    binding = db.query(CredentialBindingModel).filter(CredentialBindingModel.id == binding_id).first()
    if not binding:
        raise HTTPException(status_code=404, detail="binding 不存在")

    db.delete(binding)
    db.commit()
    return {"detail": "deleted", "binding_id": binding_id}


# ============================================================================
# Phase 3.3A — Asset Facts endpoints
# ============================================================================


@router.get("/assets/{target_type}/{target_id}/facts/latest", response_model=AssetFactsLatestResponse)
async def get_asset_facts_latest(
    target_type: str,
    target_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import AssetFactSnapshot, AssetFactValue

    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail="target_type 必须是 server 或 db_instance")

    snapshot = (
        db.query(AssetFactSnapshot)
        .filter(
            AssetFactSnapshot.target_type == target_type,
            AssetFactSnapshot.target_id == target_id,
        )
        .order_by(AssetFactSnapshot.created_at.desc())
        .first()
    )

    if not snapshot:
        return AssetFactsLatestResponse(target_type=target_type, target_id=target_id, latest_snapshot=None)

    values = (
        db.query(AssetFactValue)
        .filter(AssetFactValue.snapshot_id == snapshot.id)
        .order_by(AssetFactValue.fact_category, AssetFactValue.fact_key)
        .all()
    )

    return AssetFactsLatestResponse(
        target_type=target_type,
        target_id=target_id,
        latest_snapshot=AssetFactSnapshotResponse(
            id=int(snapshot.id),
            snapshot_id=snapshot.snapshot_id,
            run_id=snapshot.run_id,
            collector_run_id=int(snapshot.collector_run_id),
            item_key=snapshot.item_key,
            check_code=snapshot.check_code,
            target_type=snapshot.target_type,
            target_id=int(snapshot.target_id),
            target_host=snapshot.target_host,
            target_port=snapshot.target_port,
            db_type_code=snapshot.db_type_code,
            credential_profile_id=int(snapshot.credential_profile_id) if snapshot.credential_profile_id else None,
            snapshot_status=snapshot.snapshot_status,
            error_code=snapshot.error_code,
            collected_at=snapshot.collected_at,
            created_at=snapshot.created_at,
            values=[
                AssetFactValueResponse(
                    id=int(v.id),
                    fact_key=v.fact_key,
                    fact_value=v.fact_value,
                    fact_category=v.fact_category,
                    source_query=v.source_query,
                    is_null=bool(v.is_null),
                    collected_at=v.collected_at,
                )
                for v in values
            ],
        ),
    )


@router.get("/assets/{target_type}/{target_id}/facts/history", response_model=AssetFactsHistoryResponse)
async def get_asset_facts_history(
    target_type: str,
    target_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import AssetFactSnapshot

    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail="target_type 必须是 server 或 db_instance")

    total = (
        db.query(AssetFactSnapshot)
        .filter(
            AssetFactSnapshot.target_type == target_type,
            AssetFactSnapshot.target_id == target_id,
        )
        .count()
    )

    rows = (
        db.query(AssetFactSnapshot)
        .filter(
            AssetFactSnapshot.target_type == target_type,
            AssetFactSnapshot.target_id == target_id,
        )
        .order_by(AssetFactSnapshot.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    snapshots = [
        AssetFactSnapshotResponse(
            id=int(r.id),
            snapshot_id=r.snapshot_id,
            run_id=r.run_id,
            collector_run_id=int(r.collector_run_id),
            item_key=r.item_key,
            check_code=r.check_code,
            target_type=r.target_type,
            target_id=int(r.target_id),
            target_host=r.target_host,
            target_port=r.target_port,
            db_type_code=r.db_type_code,
            credential_profile_id=int(r.credential_profile_id) if r.credential_profile_id else None,
            snapshot_status=r.snapshot_status,
            error_code=r.error_code,
            collected_at=r.collected_at,
            created_at=r.created_at,
            values=[],  # history endpoint returns summary without values
        )
        for r in rows
    ]

    return AssetFactsHistoryResponse(
        target_type=target_type,
        target_id=target_id,
        total=total,
        snapshots=snapshots,
    )


# ============================================================================
# Phase 3.3A — Asset Drifts endpoints
# ============================================================================


@router.get("/assets/drifts", response_model=AssetDriftsResponse)
async def list_asset_drifts(
    resolved: Optional[bool] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import AssetDriftRecord

    query = db.query(AssetDriftRecord)
    if resolved is not None:
        query = query.filter(AssetDriftRecord.resolved == resolved)
    if severity:
        query = query.filter(AssetDriftRecord.severity == severity)

    total = query.count()
    rows = query.order_by(AssetDriftRecord.created_at.desc()).offset(offset).limit(limit).all()

    return AssetDriftsResponse(
        total=total,
        drifts=[
            AssetDriftRecordResponse(
                id=int(r.id),
                snapshot_id=int(r.snapshot_id),
                proposal_id=int(r.proposal_id) if r.proposal_id else None,
                target_type=r.target_type,
                target_id=int(r.target_id),
                field_path=r.field_path,
                expected_value=r.expected_value,
                actual_value=r.actual_value,
                drift_type=r.drift_type,
                severity=r.severity,
                resolved=bool(r.resolved),
                resolved_at=r.resolved_at,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.get("/assets/{target_type}/{target_id}/drifts", response_model=AssetDriftsResponse)
async def get_asset_drifts(
    target_type: str,
    target_id: int,
    resolved: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.dbops_assets import AssetDriftRecord

    if target_type not in ("server", "db_instance"):
        raise HTTPException(status_code=400, detail="target_type 必须是 server 或 db_instance")

    query = db.query(AssetDriftRecord).filter(
        AssetDriftRecord.target_type == target_type,
        AssetDriftRecord.target_id == target_id,
    )
    if resolved is not None:
        query = query.filter(AssetDriftRecord.resolved == resolved)

    total = query.count()
    rows = query.order_by(AssetDriftRecord.created_at.desc()).offset(offset).limit(limit).all()

    return AssetDriftsResponse(
        total=total,
        drifts=[
            AssetDriftRecordResponse(
                id=int(r.id),
                snapshot_id=int(r.snapshot_id),
                proposal_id=int(r.proposal_id) if r.proposal_id else None,
                target_type=r.target_type,
                target_id=int(r.target_id),
                field_path=r.field_path,
                expected_value=r.expected_value,
                actual_value=r.actual_value,
                drift_type=r.drift_type,
                severity=r.severity,
                resolved=bool(r.resolved),
                resolved_at=r.resolved_at,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )
