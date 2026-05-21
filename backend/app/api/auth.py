"""
认证 API - 登录接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.user import User
from app.database import SessionLocal
from app.api.deps import create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """用户登录"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == req.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not user.is_active:
            raise HTTPException(status_code=401, detail="账号已被禁用")

        # 验证密码
        if not user.verify_password(req.password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 生成 JWT token
        token = create_access_token(data={"sub": str(user.id)})

        return LoginResponse(
            access_token=token,
            token_type="bearer",
            user={
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "department": getattr(user, 'department', None),
                "role": getattr(user, 'role', None),
                "timezone": getattr(user, 'timezone', 'Asia/Shanghai'),
                "language": getattr(user, 'language', 'zh-CN'),
            }
        )
    finally:
        db.close()
