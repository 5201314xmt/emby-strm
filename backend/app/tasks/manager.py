"""
任务管理器 —— 控制扫描任务的完整生命周期

功能：
  - 启动扫描（创建 ScanJob 记录，启动异步任务）
  - 暂停/继续/取消（通过标记控制任务运行）
  - 并发控制（同一时间只能有一个扫描任务运行）

状态机：
  pending → (启动) → running → (完成) → completed
                running → (暂停) → paused → (继续) → running
                running → (取消) → cancelled
                running → (异常) → failed
"""
import asyncio
import threading
from datetime import datetime

from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..models.scan_job import ScanJob
from ..services.logger import add_log
from ..core.events import event_bus, EventType

# 全局单例 —— TaskManager 用模块级变量确保唯一的实例
_instance: "TaskManager" = None
_lock = threading.Lock()


def get_task_manager() -> "TaskManager":
    """获取 TaskManager 单例（线程安全）"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = TaskManager()
    return _instance


class TaskManager:
    """全局任务管理器（单例 —— 通过 get_task_manager() 获取）"""

    def __init__(self):
        self._active_task: asyncio.Task | None = None
        self._active_job_id: int | None = None
        self._pause_flag = False
        self._cancel_flag = False

    @property
    def is_running(self) -> bool:
        return (self._active_task is not None
                and not self._active_task.done()
                and not self._cancel_flag)

    # ========== 启动扫描 ==========

    async def start_scan(self, source_ids: list[int] = None,
                         tmdb_source=None, mp_client=None,
                         auto_subscribe: bool = False,
                         include_specials: bool = False) -> int:
        """
        启动一次扫描

        Args:
            source_ids: 指定扫描的源 ID（None=全部启用源）
            tmdb_source: TMDB 数据源实例
            mp_client: MoviePilot 客户端实例
            auto_subscribe: 是否扫描后自动订阅
            include_specials: 是否包含特别篇

        Returns:
            job_id: 任务 ID
        Raises:
            RuntimeError: 已有任务在运行
        """
        if self.is_running:
            raise RuntimeError("已有扫描任务在运行中，请等待完成后再试")

        self._pause_flag = False
        self._cancel_flag = False

        # 创建 ScanJob 记录
        async with AsyncSessionLocal() as db:
            now = datetime.now()
            scan_job = ScanJob(
                status="running",
                phase="准备中...",
                progress=0.0,
                source_ids=source_ids or [],
                started_at=now,
            )
            db.add(scan_job)
            await db.commit()
            await db.refresh(scan_job)
            job_id = scan_job.id

        self._active_job_id = job_id
        self._active_task = asyncio.create_task(
            self._run_scan(job_id, tmdb_source, mp_client,
                          auto_subscribe, include_specials, source_ids)
        )

        await add_log("INFO", "scan", f"扫描任务 #{job_id} 已启动")
        return job_id

    # ========== 控制 ==========

    async def pause(self, job_id: int) -> tuple[bool, str]:
        """暂停扫描"""
        if self._active_job_id != job_id or not self.is_running:
            return False, "任务不存在或未在运行"
        self._pause_flag = True
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                job.status = "paused"
                job.phase = "已暂停"
                await db.commit()
        await event_bus.publish(EventType.SCAN_PAUSED, {"job_id": job_id})
        return True, "扫描已暂停"

    async def resume(self, job_id: int) -> tuple[bool, str]:
        """继续扫描"""
        if self._active_job_id != job_id:
            return False, "任务不存在或已完成"
        self._pause_flag = False
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                job.status = "running"
                job.phase = "扫描中..."
                await db.commit()
        await event_bus.publish(EventType.SCAN_RESUMED, {"job_id": job_id})
        return True, "扫描已继续"

    async def cancel(self, job_id: int) -> tuple[bool, str]:
        """取消扫描"""
        if self._active_job_id != job_id:
            return False, "任务不存在或已完成"
        self._cancel_flag = True
        if self._active_task:
            self._active_task.cancel()
        await event_bus.publish(EventType.SCAN_CANCELLED, {"job_id": job_id})
        return True, "扫描已取消"

    # ========== 内部执行 ==========

    async def _run_scan(self, job_id: int, tmdb_source, mp_client,
                        auto_subscribe: bool, include_specials: bool,
                        source_ids: list[int] = None):
        from .scan import run_scan
        try:
            await run_scan(
                job_id=job_id,
                tmdb_source=tmdb_source,
                mp_client=mp_client,
                auto_subscribe=auto_subscribe,
                include_specials=include_specials,
                source_ids=source_ids,
                cancel_check=lambda: self._cancel_flag,
                pause_check=lambda: self._pause_flag,
            )
        except asyncio.CancelledError:
            async with AsyncSessionLocal() as db:
                job = await db.get(ScanJob, job_id)
                if job:
                    job.status = "cancelled"
                    job.phase = "已取消"
                    job.completed_at = datetime.now()
                    await db.commit()
        except Exception as e:
            async with AsyncSessionLocal() as db:
                job = await db.get(ScanJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.now()
                    await db.commit()
        finally:
            self._active_task = None
            self._active_job_id = None
            self._pause_flag = False
            self._cancel_flag = False
