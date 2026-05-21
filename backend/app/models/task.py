from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class TaskState:
    """任务状态（存储在 Redis 中，TTL=24h）"""
    task_id: str
    status: str  # pending / running / complete / failed
    total_hosts: int
    completed_hosts: int = 0
    started_at: str = ''
    results: dict = field(default_factory=dict)  # {ip: {status, stdout, stderr}}
    initiated_by: str = 'admin'

    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'status': self.status,
            'total_hosts': self.total_hosts,
            'completed_hosts': self.completed_hosts,
            'started_at': self.started_at,
            'results': self.results,
            'initiated_by': self.initiated_by,
        }

    def save(self, redis_client) -> None:
        """保存到 Redis，TTL=24小时"""
        key = f'task:{self.task_id}'
        redis_client.setex(key, 86400, json.dumps(self.to_dict()))

    @classmethod
    def load(cls, redis_client, task_id: str) -> Optional['TaskState']:
        """从 Redis 加载"""
        key = f'task:{task_id}'
        data = redis_client.get(key)
        if not data:
            return None
        d = json.loads(data)
        return cls(
            task_id=d['task_id'],
            status=d['status'],
            total_hosts=d['total_hosts'],
            completed_hosts=d.get('completed_hosts', 0),
            started_at=d.get('started_at', ''),
            results=d.get('results', {}),
            initiated_by=d.get('initiated_by', 'admin'),
        )
