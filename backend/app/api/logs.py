"""
操作日志 API
"""
from fastapi import APIRouter, Depends
from app.models.user import User
from app.api.deps import get_current_user, get_db

router = APIRouter()


@router.get("/list")
async def list_logs(current_user: User = Depends(get_current_user), db=Depends(get_db)):
    """获取最近 100 条操作日志（后续从审计模块获取）"""
    # TODO: 审计模块实现后从此模块获取
    return []
