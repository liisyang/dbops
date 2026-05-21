"""
WebSocket 处理 - 替代 Flask-SocketIO 的房间机制
通过 Redis pub/sub 接收 RQ 任务输出并广播到对应房间。
"""
import asyncio
import json
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

PUBSUB_CHANNEL = "task_output"


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str) -> None:
        """接受 WebSocket 连接并加入房间"""
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)

    def disconnect(self, websocket: WebSocket, room: str) -> None:
        """从房间断开连接"""
        if room in self.active_connections:
            if websocket in self.active_connections[room]:
                self.active_connections[room].remove(websocket)
            if not self.active_connections[room]:
                del self.active_connections[room]

    async def send_to_room(self, room: str, event: str, data: dict) -> None:
        """向房间内所有连接发送消息"""
        if room in self.active_connections:
            message = {"event": event, "data": data}
            for connection in self.active_connections[room]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast(self, event: str, data: dict) -> None:
        """广播到所有连接"""
        for room, connections in self.active_connections.items():
            message = {"event": event, "data": data}
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


# 全局连接管理器
manager = ConnectionManager()


@router.websocket("/{socket_id}")
async def websocket_endpoint(websocket: WebSocket, socket_id: str):
    """
    WebSocket 端点。
    前端连接时使用 socket_id 作为房间号。
    """
    await manager.connect(websocket, socket_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, socket_id)
    except Exception:
        manager.disconnect(websocket, socket_id)


async def start_redis_subscriber():
    """
    启动 Redis pub/sub 订阅者，接收任务输出并广播到对应房间。
    由 main.py 在启动时调用。
    """
    import redis as redis_lib
    from app.config import get_settings

    settings = get_settings()
    redis_client = redis_lib.from_url(settings.REDIS_URL)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(PUBSUB_CHANNEL)

    while True:
        try:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                socket_id = data.get("socket_id")
                event = data.get("event")
                msg_data = data.get("data")
                if socket_id and event:
                    await manager.send_to_room(socket_id, event, msg_data)
            await asyncio.sleep(0.01)
        except Exception as e:
            print(f"[redis_subscriber] error: {e}")
            await asyncio.sleep(1)


def start_redis_subscriber_task():
    """启动 Redis 订阅者后台任务"""
    return asyncio.create_task(start_redis_subscriber())
