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
