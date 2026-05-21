"""
Celery 任务队列配置。
"""
from celery import Celery

from app.config import get_settings

_settings = get_settings()

# 创建 Celery 应用
app = Celery(
    'dbops',
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
)

# 配置
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10分钟超时
    task_soft_time_limit=540,
)

# 导出 celery app 供其他地方使用
task_app = app
