from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.inspection import (
    InspectionItemCreateRequest,
    InspectionItemResponse,
    InspectionItemUpdateRequest,
    InspectionResultResponse,
    InspectionTaskCreateRequest,
    InspectionTaskCreateResponse,
    InspectionTaskResponse,
)
from app.services.inspection_service import InspectionService

router = APIRouter()


@router.get("/inspection/items", response_model=List[InspectionItemResponse])
async def list_inspection_items(
    enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_items(db, enabled=enabled)


@router.post("/inspection/items", response_model=InspectionItemResponse, status_code=201)
async def create_inspection_item(
    payload: InspectionItemCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.create_item(db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/inspection/items/{item_id}", response_model=InspectionItemResponse)
async def update_inspection_item(
    item_id: int,
    payload: InspectionItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.update_item(db, item_id=item_id, payload=payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inspection/tasks", response_model=InspectionTaskCreateResponse)
async def create_inspection_task(
    payload: InspectionTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.create_task(db, payload=payload, requested_by=current_user.username)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/inspection/tasks", response_model=List[InspectionTaskResponse])
async def list_inspection_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_tasks(db, limit=limit)


@router.get("/inspection/tasks/{task_id}", response_model=InspectionTaskResponse)
async def get_inspection_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.get_task(db, task_id=task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/inspection/results", response_model=List[InspectionResultResponse])
async def list_inspection_results(
    task_id: Optional[int] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    target_id: Optional[int] = Query(default=None),
    result_status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_results(
        db,
        task_id=task_id,
        target_type=target_type,
        target_id=target_id,
        result_status=result_status,
        limit=limit,
    )
