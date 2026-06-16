"""
Celery 任务队列配置。
"""
from celery import Celery
from celery.schedules import schedule

from app.config import get_settings

_settings = get_settings()

# 创建 Celery 应用
# P0-4: include all task modules so worker auto-registers them.
# Use include (not autodiscover) — autodiscover expects `tasks.py` modules
# per app and doesn't fit our collector_tasks naming.
celery = Celery(
    'dbops',
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
    include=[
        'app.tasks.account_tasks',
        'app.tasks.collector_tasks',
    ],
)

# 配置
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10分钟超时
    task_soft_time_limit=540,
    # P0-4 / P0-5: beat schedules for collector scheduler + timeout recovery.
    # Intervals are typed as int in Settings (default 15s / 60s) so a plain
    # int() cast is sufficient; no need for `or X` fallbacks (the field has
    # a server default).
    beat_schedule={
        'dispatch-scheduler': {
            'task': 'app.tasks.collector_tasks.dispatch_scheduler_task',
            'schedule': schedule(run_every=int(_settings.COLLECTOR_DISPATCH_SCHEDULER_INTERVAL)),
        },
        'timeout-recovery': {
            'task': 'app.tasks.collector_tasks.timeout_recovery_task',
            'schedule': schedule(run_every=int(_settings.COLLECTOR_TIMEOUT_RECOVERY_INTERVAL)),
        },
    },
)

# Backward-compat alias: code elsewhere imports `app` from this module.
# (Celery's `-A` flag points at `celery` now.)
app = celery
task_app = celery
