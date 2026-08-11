"""
WebSocket 端点 —— 实时推送扫描进度 + 日志 + 事件

前端连接此端点后，服务端主动推送 JSON 帧。
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.events import event_bus, EventType
from ..core.security import validate_session

router = APIRouter(tags=["WebSocket"])

# 所有活跃连接
_active_connections: list[WebSocket] = []


async def _broadcast(event_type: str, data: dict):
    """向所有已连接 WebSocket 广播事件"""
    message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    disconnected = []
    for ws in _active_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _active_connections.remove(ws)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 连接端点 —— 验证登录后保持长连接"""
    cookie_header = ws.headers.get("cookie", "")
    token = ""
    for part in cookie_header.replace(" ", "").split(";"):
        if part.startswith("queji_session="):
            token = part.split("=", 1)[1]
            break

    if not token or not await validate_session(token):
        await ws.close(code=1008, reason="未登录")
        return

    await ws.accept()
    _active_connections.append(ws)

    # 创建事件回调：收到事件后推送给此连接
    async def forward_event(data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    # 订阅到事件总线
    event_bus.subscribe(EventType.SCAN_PROGRESS, forward_event)
    event_bus.subscribe(EventType.SCAN_COMPLETED, forward_event)
    event_bus.subscribe(EventType.SCAN_FAILED, forward_event)
    event_bus.subscribe(EventType.SCAN_PAUSED, forward_event)
    event_bus.subscribe(EventType.SCAN_RESUMED, forward_event)
    event_bus.subscribe(EventType.SCAN_CANCELLED, forward_event)
    event_bus.subscribe(EventType.DASHBOARD_REFRESH, forward_event)

    await ws.send_json({"type": "connected", "data": {"message": "WebSocket 已连接"}})

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # 取消订阅所有事件
        for event_type in [
            EventType.SCAN_PROGRESS, EventType.SCAN_COMPLETED, EventType.SCAN_FAILED,
            EventType.SCAN_PAUSED, EventType.SCAN_RESUMED, EventType.SCAN_CANCELLED,
            EventType.DASHBOARD_REFRESH,
        ]:
            event_bus.unsubscribe(event_type, forward_event)
        if ws in _active_connections:
            _active_connections.remove(ws)
