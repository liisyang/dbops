from __future__ import annotations

import hmac
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi import Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.user import User
from app.schemas.collector import (
    AssetVerifyLaunchRequest,
    AssetVerifyLaunchResponse,
    CollectorCallbackRequest,
    CollectorCallbackResponse,
    CollectorRunResponse,
)
from app.services.collector_service import CollectorService

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


@router.get("/collector/instances/{instance_id}/runs", response_model=List[CollectorRunResponse])
async def list_instance_collector_runs(
    instance_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorService.list_instance_runs(db, instance_id=instance_id, limit=limit)


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
