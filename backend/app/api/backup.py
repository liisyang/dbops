"""Phase 3.5: backup status API endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.backup import (
    BackupCollectRequest,
    BackupCollectResponse,
    BackupStatusHistoryItem,
    BackupStatusLatestItem,
    ValidateBackupSqlRequest,
    ValidateBackupSqlResponse,
)
from app.services.backup_service import (
    launch_collect,
    list_history,
    list_latest,
    validate_sql,
)

router = APIRouter()


@router.post(
    "/backup/status/collect",
    response_model=BackupCollectResponse,
    status_code=202,
)
async def collect_backup_status(
    payload: BackupCollectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Launch a one-shot backup status collect via AWX."""
    try:
        return launch_collect(
            db,
            instance_ids=payload.instance_ids,
            db_type_code=payload.db_type_code,
            backup_type=payload.backup_type,
            sql_text=payload.sql_text,
            timeout_seconds=payload.timeout_seconds,
            max_rows=payload.max_rows,
            requested_by=current_user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/backup/status/latest",
    response_model=List[BackupStatusLatestItem],
)
async def get_backup_status_latest(
    db_type_code: Optional[str] = Query(default=None),
    last_status: Optional[str] = Query(default=None),
    backup_type: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest backup status per (instance, backup_type) joined with assets."""
    return list_latest(
        db,
        db_type_code=db_type_code,
        last_status=last_status,
        backup_type=backup_type,
        keyword=keyword,
        limit=limit,
    )


@router.get(
    "/backup/status/history",
    response_model=List[BackupStatusHistoryItem],
)
async def get_backup_status_history(
    instance_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Raw backup status history, newest first."""
    return list_history(db, instance_id=instance_id, limit=limit)


@router.post(
    "/backup/status/validate-sql",
    response_model=ValidateBackupSqlResponse,
)
async def validate_backup_sql(
    payload: ValidateBackupSqlRequest,
    current_user: User = Depends(get_current_user),
):
    """Pure SQL safety check, no DB connection."""
    result = validate_sql(db_type_code=payload.db_type_code, sql_text=payload.sql_text)
    return {
        "valid": bool(result.get("valid")),
        "sql_hash": str(result.get("sql_hash") or ""),
        "message": "ok" if result.get("valid") else "SQL 校验未通过",
        "errors": list(result.get("errors") or []),
    }
