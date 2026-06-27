"""
FastAPI 应用 - 移除 Flask 依赖
使用原生 SQLAlchemy 进行数据库操作
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import logs, servers, account_ops, websocket, auth, collector, inspection, backup, ai
from app.database import SessionLocal
from app.services.dify_service import DifyService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()

    # AI Copilot（Phase 3.6）— 启动时校验配置（plan §11 P1 特征感知）
    # 校验在 __init__ 外显式调用，便于测试构造 Settings 而不触发校验
    settings.validate_ai_config()

    # 仅在任一功能开启时初始化 Dify 客户端
    if settings.dify_configured and settings.DIFY_BASE_URL:
        try:
            DifyService.init_client(
                base_url=settings.DIFY_BASE_URL,
                connect_timeout=settings.DIFY_CONNECT_TIMEOUT_SECONDS,
                timeout=settings.DIFY_CHAT_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("DifyService 初始化失败（将继续启动，但 AI 功能不可用）: %s", exc)

    # AI Copilot（Phase 3.6 C3）— 启动时清理 chat pending 中 lease 已过期的消息（plan §7 P0-5）
    # 用 asyncio.to_thread 避免阻塞事件循环；同样逻辑适用于 inspection_ai_analysis 和
    # schema_snapshot（C22 / C9 各自实现独立清理入口）
    if settings.AI_CHAT_ENABLED:
        try:
            from app.services.ai_chat_service import AiChatService

            def _run_chat_cleanup() -> int:
                cleanup_db = SessionLocal()
                try:
                    return AiChatService.cleanup_stale_pending(cleanup_db)
                finally:
                    cleanup_db.close()

            cleaned = await asyncio.to_thread(_run_chat_cleanup)
            logger.info("AI chat startup cleanup: marked %s stale pending messages", cleaned)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI chat startup cleanup failed (continuing): %s", exc)

    # 主机监控已禁用（7表设计不需要）
    # from app.services.host_monitor import set_db_session
    # set_db_session(SessionLocal)
    # monitor_task = asyncio.create_task(start_host_monitor())

    # Redis pub/sub 订阅者暂时不启动，后续需要任务输出时再恢复。
    redis_subscriber_task = None

    yield

    # Shutdown: 关闭 Dify 客户端（Phase 3.6）
    DifyService.close_client()

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
    app.include_router(collector.router, prefix="/api/v1", tags=["collector"])
    app.include_router(inspection.router, prefix="/api/v1", tags=["inspection"])
    app.include_router(backup.router, prefix="/api/v1", tags=["backup"])
    app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])  # Phase 3.6 AI Copilot
    app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

    return app
