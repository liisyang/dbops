"""
异步账号操作 API
"""
import uuid
from typing import Optional, List, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.tasks.account_tasks import add_user_task, chpasswd_task, check_user_task
from app.services.password import hash_password, generate_password
from app.models.task import TaskState
from app.config import get_settings
import redis as redis_lib
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


class AddUserRequest(BaseModel):
    engine: str
    host_ips: List[str]
    username: str
    profile: str
    socket_id: Optional[str] = None


class CheckUserRequest(BaseModel):
    usernames: Union[str, List[str]]
    host_ips: List[str]
    socket_id: Optional[str] = None


class ChpasswdUser(BaseModel):
    username: str
    password: Optional[str] = None


class ChpasswdRequest(BaseModel):
    engine: str
    host_ips: List[str]
    users: List[ChpasswdUser]
    socket_id: Optional[str] = None


@router.post("/users/add")
async def add_user(
    req: AddUserRequest,
    current_user: User = Depends(get_current_user),
):
    """
    异步新增用户。

    Returns:
        {'task_id': str, 'password': str}
    """
    try:
        if not req.host_ips or not req.username or not req.profile:
            raise HTTPException(status_code=400, detail="缺少必要参数")

        task_id = str(uuid.uuid4())[:8]
        initiated_by = str(current_user.id)

        # 生成随机密码并哈希
        plaintext_pwd = generate_password(12)
        pwd_hash = hash_password(plaintext_pwd)

        # 入队 Celery 任务
        add_user_task.delay(
            task_id=task_id,
            host_ips=req.host_ips,
            username=req.username,
            profile=req.profile,
            password_hash=pwd_hash,
            initiated_by=initiated_by,
            socket_id=req.socket_id,
        )

        return {"task_id": task_id, "password": plaintext_pwd}

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/check")
async def check_user(
    req: CheckUserRequest,
    current_user: User = Depends(get_current_user),
):
    """
    检查用户是否存在。

    Returns:
        {'task_id': str}
    """
    try:
        raw = req.usernames
        if isinstance(raw, str):
            usernames = [u.strip() for u in raw.split(",") if u.strip()]
        elif isinstance(raw, list):
            usernames = raw
        else:
            usernames = []

        if not req.host_ips or not usernames:
            raise HTTPException(status_code=400, detail="缺少必要参数")

        task_id = str(uuid.uuid4())[:8]
        initiated_by = str(current_user.id)

        check_user_task.delay(
            task_id=task_id,
            usernames=usernames,
            host_ips=req.host_ips,
            initiated_by=initiated_by,
            socket_id=req.socket_id,
        )

        return {"task_id": task_id}

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/chpasswd")
async def chpasswd(
    req: ChpasswdRequest,
    current_user: User = Depends(get_current_user),
):
    """
    异步修改密码。

    Returns:
        {'task_ids': [{'task_id', 'username', 'password'}]}
    """
    try:
        if not req.host_ips or not req.users:
            raise HTTPException(status_code=400, detail="缺少必要参数")

        initiated_by = str(current_user.id)
        task_ids = []

        for u in req.users:
            username = u.username
            plaintext_pwd = u.password or generate_password(12)
            pwd_hash = hash_password(plaintext_pwd)

            task_id = str(uuid.uuid4())[:8]
            task_ids.append(
                {
                    "task_id": task_id,
                    "username": username,
                    "password": plaintext_pwd,
                }
            )

            chpasswd_task.delay(
                task_id=task_id,
                host_ips=req.host_ips,
                username=username,
                password_hash=pwd_hash,
                initiated_by=initiated_by,
                socket_id=req.socket_id,
            )

        return {"task_ids": task_ids}

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取任务状态"""
    redis_conn = redis_lib.from_url(get_settings().REDIS_URL)
    state = TaskState.load(redis_conn, task_id)
    if not state:
        raise HTTPException(status_code=404, detail="not_found")
    return state.to_dict()


@router.get("/tasks/{task_id}/results")
async def get_task_results(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取任务结果"""
    redis_conn = redis_lib.from_url(get_settings().REDIS_URL)
    state = TaskState.load(redis_conn, task_id)
    if not state:
        raise HTTPException(status_code=404, detail="not_found")
    return {
        "task_id": task_id,
        "status": state.status,
        "total_hosts": state.total_hosts,
        "completed_hosts": state.completed_hosts,
        "results": state.results,
        "initiated_by": state.initiated_by,
    }
