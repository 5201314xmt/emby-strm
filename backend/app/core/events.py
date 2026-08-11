"""
跨线程事件总线 —— 用于后台任务向 WebSocket 推送消息

为什么需要这个？
  后台扫描线程（anyio task）产生的进度、日志等事件，
  需要实时推送给前端的 WebSocket 连接。
  事件总线作为中间人：后台线程发布，WebSocket 端点消费。

设计原则：
  - 订阅者模式：多个 WebSocket 连接可以同时订阅同一事件
  - 异步回调：subscribe 时传 async 函数
  - 线程安全：使用 anyio 的线程间通信（to_thread）
"""
import anyio
from collections import defaultdict
from typing import Callable, Awaitable

# 事件类型常量（方便代码里引用，不打错字）
class EventType:
    SCAN_PROGRESS = "scan.progress"         # 扫描进度更新
    SCAN_COMPLETED = "scan.completed"       # 扫描完成
    SCAN_FAILED = "scan.failed"             # 扫描失败
    SCAN_PAUSED = "scan.paused"             # 扫描暂停
    SCAN_RESUMED = "scan.resumed"           # 扫描恢复
    SCAN_CANCELLED = "scan.cancelled"       # 扫描取消
    LOG_NEW = "log.new"                     # 新日志写入
    SUBSCRIPTION_UPDATED = "subscription.updated"   # 订阅状态变化
    DASHBOARD_REFRESH = "dashboard.refresh"         # 仪表盘需要刷新


class EventBus:
    """
    事件总线

    用法：
      # 发布事件（任何线程/协程）
      await event_bus.publish(EventType.SCAN_PROGRESS, {"done": 10, "total": 100})

      # 订阅事件（WebSocket 端点）
      async def on_scan_progress(data):
          await ws.send_json({"type": "scan.progress", "data": data})
      event_bus.subscribe(EventType.SCAN_PROGRESS, on_scan_progress)
    """

    def __init__(self):
        # 订阅者字典：{事件类型: [回调函数1, 回调函数2, ...]}
        self._subscribers: dict[str, list[Callable[[dict], Awaitable[None]]]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[[dict], Awaitable[None]]):
        """
        订阅某类事件

        Args:
            event_type: 事件类型（用 EventType 常量，别手打字符串）
            callback:   异步回调函数，接收一个 dict 参数
        """
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[dict], Awaitable[None]]):
        """取消订阅（WebSocket 断开时调用）"""
        subs = self._subscribers.get(event_type, [])
        if callback in subs:
            subs.remove(callback)

    async def publish(self, event_type: str, data: dict):
        """
        发布事件 —— 通知所有订阅者

        每个订阅者的回调是独立执行的，一个抛异常不影响其他。
        后台线程需要 await publish()，事件会被推送到所有 WebSocket 连接。

        Args:
            event_type: 事件类型
            data:       事件携带的数据字典
        """
        callbacks = self._subscribers.get(event_type, [])
        for callback in callbacks:
            try:
                await callback(data)
            except Exception:
                # 一个订阅者出错不能影响其他订阅者
                pass


# ========== 全局单例 ==========
# 整个应用共用一个事件总线实例
event_bus = EventBus()
