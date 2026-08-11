"""
WebSocket 端点 —— 实时推送扫描进度 + 日志 + 事件

前端连接此端点后，服务端主动推送 JSON 帧，
前端用 useWebSocket hook 接收并更新 UI。

帧格式（每帧一个 JSON 对象）：
  {"type": "scan.progress", "data": {...}}
  {"type": "log.new", "data": {...}}
  {"type": "dashboard.refresh"}
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.events import event_bus
from ..core.security import validate_session

router = APIRouter(tags=["WebSocket"])

# 所有活跃的 WebSocket 连接
_active_connections: list[WebSocket] = []


async def _broadcast_event(event_type: str, data: dict):
    """
    向所有已连接的 WebSocket 广播事件

    连接断开的自动移除，不影响其他连接。
    """
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
    """
    WebSocket 连接端点

    前端连接后保持长连接，服务端持续推送事件。
    连接需要验证 Cookie 中的登录态。
    """
    # 从 Cookie 获取 session token 验证登录
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

    # 注册事件回调：当后台任务发布事件时，推送给这个连接
    async def on_event(data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    # 告诉前端连接成功
    await ws.send_json({"type": "connected", "data": {"message": "WebSocket 已连接"}})

    try:
        # 保持连接，等待客户端消息（如心跳 pong）
        while True:
            data = await ws.receive_text()
            # 客户端发来 ping，回复 pong
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in _active_connections:
            _active_connections.remove(ws)
