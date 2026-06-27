from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fastapi import BackgroundTasks

from app.api.deps import get_current_user, get_db
from app.models.dbops_assets import InspectionReport, InspectionInstanceReport
from app.models.user import User
from app.schemas.inspection import (
    InspectionItemCreateRequest,
    InspectionItemResponse,
    InspectionItemUpdateRequest,
    InspectionResultResponse,
    InspectionTaskCreateRequest,
    InspectionTaskCreateResponse,
    InspectionTaskResponse,
    InspectionReportResponse,
    InspectionReportListResponse,
    InspectionInstanceReportResponse,
    ValidateSqlRequest,
    ValidateSqlResponse,
    VerifySqlRequest,
    VerifySqlResponse,
    VerifySqlResultResponse,
)
from app.services import asset_event_history_service
from app.services.inspection_service import InspectionService
from app.services.report_export_service import build_docx_response, build_report_docx

router = APIRouter()


@router.get("/inspection/items", response_model=List[InspectionItemResponse])
async def list_inspection_items(
    enabled: Optional[bool] = Query(default=None),
    db_type_code: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    inspection_type: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_items(db, enabled=enabled, db_type_code=db_type_code, source=source, inspection_type=inspection_type)


@router.get("/inspection/types")
async def list_inspection_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_inspection_types(db)


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/inspection/items/{item_id}", response_model=InspectionItemResponse)
async def patch_inspection_item(
    item_id: int,
    payload: InspectionItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """P0: PATCH endpoint used for soft-disable (set enabled=false).

    A dedicated DELETE endpoint is intentionally NOT provided because
    inspection items are referenced by inspection_task.item_codes and
    inspection_result; hard-deleting would break history.
    """
    try:
        return InspectionService.update_item(db, item_id=item_id, payload=payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/inspection/items/batch-disable")
async def batch_disable_inspection_items(
    item_ids: list[int] = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch soft-disable inspection items (set enabled=false)."""
    try:
        return InspectionService.batch_disable_items(db, item_ids=item_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inspection/items/validate-sql", response_model=ValidateSqlResponse)
async def validate_inspection_sql(
    payload: ValidateSqlRequest,
    current_user: User = Depends(get_current_user),
):
    """Phase 3.5: pure SQL safety check (no DB connection)."""
    return InspectionService.validate_sql(
        db=None,
        db_type_code=payload.db_type_code,
        sql_text=payload.sql_text,
    )


@router.post("/inspection/items/verify-sql", response_model=VerifySqlResponse)
async def verify_inspection_sql(
    payload: VerifySqlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Phase 3.5: launch an AWX one-shot SQL verify against the given instance.

    Polling endpoint: GET /inspection/items/verify-sql/{verify_run_id}.
    """
    try:
        return InspectionService.verify_sql(
            db,
            instance_ids=payload.instance_ids,
            db_type_code=payload.db_type_code,
            sql_text=payload.sql_text,
            timeout_seconds=payload.timeout_seconds,
            max_rows=payload.max_rows,
            requested_by=current_user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inspection/items/verify-sql/{verify_run_id}", response_model=VerifySqlResultResponse)
async def get_verify_sql_result(
    verify_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Phase 3.5: poll the latest state of a verify-sql AWX run."""
    try:
        return InspectionService.get_verify_sql_result(db, verify_run_id=verify_run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


# =========================================================================
# v5.1 Report endpoints
# =========================================================================


@router.get("/inspection/reports", response_model=InspectionReportListResponse)
async def list_inspection_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    health_level: Optional[str] = Query(default=None),
    report_status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    health_levels = [h.strip() for h in health_level.split(",")] if health_level else None
    return InspectionService.list_reports(
        db, page=page, page_size=page_size,
        health_level=health_levels, report_status=report_status,
    )


@router.get("/inspection/reports/task/{task_id}", response_model=InspectionReportResponse)
async def get_inspection_report_by_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.get_report(db, task_id=task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/inspection/reports/{report_id}", response_model=InspectionReportResponse)
async def get_inspection_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    return InspectionService._report_to_dict(report)


@router.get("/inspection/reports/{report_id}/instances", response_model=List[InspectionInstanceReportResponse])
async def list_instance_reports(
    report_id: int,
    health_level: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InspectionService.list_instance_reports(
        db, report_id=report_id, health_level=health_level,
    )


@router.get("/inspection/reports/{report_id}/instances/{target_type}/{target_id}/results", response_model=List[InspectionResultResponse])
async def get_instance_report_results(
    report_id: int,
    target_type: str,
    target_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return InspectionService.get_instance_report_results(
            db, report_id=report_id, target_type=target_type, target_id=target_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inspection/reports/{report_id}/regenerate")
async def regenerate_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    payload = InspectionService.regenerate_report(
        db, task_id=int(report.task_id), generated_by=current_user.username,
    )
    asset_event_history_service.record_event(
        db,
        asset_type="inspection_report",
        asset_id=int(report.id),
        event_type="report.regenerated",
        reason=f"task_id={report.task_id}",
        operator=current_user.username,
        changed_fields={
            "report_status": payload.get("report_status"),
            "health_level": payload.get("health_level"),
            "health_score": payload.get("health_score"),
        },
    )
    db.commit()
    return payload


@router.post("/inspection/reports/{report_id}/export")
async def export_inspection_report(
    report_id: int,
    background_tasks: BackgroundTasks,
    include_evidence: bool = Query(default=False, description="包含原始 evidence 行（仅 admin）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """plan §8: 导出巡检报告 DOCX。

    原始 evidence (rows/findings 原文) 仅 admin 角色可导出；其他角色导出会
    在表格中标注「(需 admin 角色)」占位字符串。审计事件 report.exported
    / report.evidence_exported 落 asset_event_history。
    """
    report = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")

    is_admin = (current_user.role or "").lower() == "admin"
    include_raw = bool(include_evidence and is_admin)

    instance_count = db.query(InspectionInstanceReport).filter(
        InspectionInstanceReport.report_id == int(report.id)
    ).count()
    if instance_count > 500:
        raise HTTPException(
            status_code=400,
            detail=f"实例数 {instance_count} 超过单次导出上限 500，请使用分页或筛选后再导出",
        )

    document = build_report_docx(db, report=report, include_raw_evidence=include_raw)
    response = build_docx_response(
        report_code=report.report_code or f"REPORT-{report.id}",
        document=document,
        background_tasks=background_tasks,
        single_instance=None,
    )

    asset_event_history_service.record_event(
        db,
        asset_type="inspection_report",
        asset_id=int(report.id),
        event_type="report.evidence_exported" if include_raw else "report.exported",
        reason=f"task_id={report.task_id} include_evidence={include_raw} scope=full",
        operator=current_user.username,
        changed_fields={"instance_count": instance_count},
    )
    db.commit()
    return response


@router.post("/inspection/reports/{report_id}/instances/{target_type}/{target_id}/export")
async def export_inspection_instance_report(
    report_id: int,
    target_type: str,
    target_id: int,
    background_tasks: BackgroundTasks,
    include_evidence: bool = Query(default=False, description="包含原始 evidence 行（仅 admin）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export a single instance's slice of a report as DOCX (post-verification 2026-06-26).

    Mirrors ``/reports/{id}/export`` but constrains the document to one
    (target_type, target_id) tuple. The report still has to exist; we do
    not require the instance_report to have been generated yet — empty
    documents are surfaced as "无巡检结果" rather than a 404.
    """
    report = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")

    is_admin = (current_user.role or "").lower() == "admin"
    include_raw = bool(include_evidence and is_admin)

    single_instance = (target_type, int(target_id))
    document = build_report_docx(
        db, report=report, include_raw_evidence=include_raw, single_instance=single_instance
    )
    response = build_docx_response(
        report_code=report.report_code or f"REPORT-{report.id}",
        document=document,
        background_tasks=background_tasks,
        single_instance=single_instance,
    )

    asset_event_history_service.record_event(
        db,
        asset_type="inspection_report",
        asset_id=int(report.id),
        event_type="report.evidence_exported" if include_raw else "report.exported",
        reason=(
            f"task_id={report.task_id} include_evidence={include_raw} "
            f"scope=instance target_type={target_type} target_id={int(target_id)}"
        ),
        operator=current_user.username,
        changed_fields={"target_type": target_type, "target_id": int(target_id)},
    )
    db.commit()
    return response
