"""
FastAPI 应用 - 移除 Flask 依赖
使用原生 SQLAlchemy 进行数据库操作
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import logs, servers, account_ops, websocket, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    get_settings()

    # 主机监控已禁用（7表设计不需要）
    # from app.services.host_monitor import set_db_session
    # set_db_session(SessionLocal)
    # monitor_task = asyncio.create_task(start_host_monitor())

    # Redis pub/sub 订阅者暂时不启动，后续需要任务输出时再恢复。
    redis_subscriber_task = None

    yield

    # Shutdown: 取消后台任务
    if redis_subscriber_task:
        redis_subscriber_task.cancel()
    try:
        await asyncio.sleep(0)  # 让取消得以生效
    except asyncio.CancelledError:
        pass
    if redis_subscriber_task:
        try:
            await redis_subscriber_task
        except asyncio.CancelledError:
            pass


def create_app(testing: bool = False) -> FastAPI:
    settings = get_settings()

    # 测试模式下跳过 lifespan（避免连接真实数据库和启动后台任务）
    if testing:
        app = FastAPI(title="DBOPS API", version="3.0.0")
    else:
        app = FastAPI(
            title="DBOPS API",
            version="3.0.0",
            lifespan=lifespan,
        )

    # CORS 配置
    origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(servers.router, prefix="/api/v1/servers", tags=["servers"])
    app.include_router(account_ops.router, prefix="/api", tags=["account-ops"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

    return app
