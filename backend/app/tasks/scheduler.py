"""
定时扫描调度器 —— 按配置的间隔自动触发扫描

每隔 60 秒检查一次：
  - 是否开启了"自动扫描"
  - 距离上次扫描是否超过了配置的间隔
  - 当前有没有正在运行的扫描任务
条件都满足时自动启动扫描。
"""
import asyncio
from datetime import datetime, timedelta

from ..core.database import AsyncSessionLocal
from ..models.setting import Setting
from ..models.scan_job import ScanJob
from sqlalchemy import select

# 调度器任务引用（用于关闭时取消）
_scheduler_task: asyncio.Task = None


async def _get_setting_value(key: str, default: str = "") -> str:
    """从数据库读取一个配置值"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Setting.value).where(Setting.key == key)
        )
        row = result.one_or_none()
        return row[0] if row else default


async def _has_running_job() -> bool:
    """检查当前是否有正在运行的扫描任务"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScanJob.id).where(ScanJob.status == "running")
        )
        return result.scalar_one_or_none() is not None


async def _scheduler_loop():
    """
    调度器主循环 —— 每 60 秒检查一次是否需要自动扫描

    作为 asyncio 任务运行，应用关闭时取消。
    """
    while True:
        try:
            await asyncio.sleep(60)

            # 检查是否开启了自动扫描
            auto_scan = await _get_setting_value("auto_scan", "0")
            if auto_scan != "1":
                continue

            # 检查是否有正在运行的任务
            if await _has_running_job():
                continue

            # 检查距离上次扫描的时间
            last_scan_str = await _get_setting_value("last_scan", "")
            if not last_scan_str:
                continue  # 从未扫描过，等用户手动触发第一次

            try:
                last_scan = datetime.strptime(last_scan_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            interval_str = await _get_setting_value("scan_interval", "12")
            try:
                interval_hours = int(interval_str)
            except ValueError:
                interval_hours = 12

            elapsed = (datetime.now() - last_scan).total_seconds()
            if elapsed >= interval_hours * 3600:
                # 触发扫描（使用全局单例和共享实例）
                from .manager import get_task_manager
                from ..core.app_state import tmdb_source, mp_client, get_auto_subscribe, get_include_specials
                mgr = get_task_manager()
                await mgr.start_scan(
                    tmdb_source=tmdb_source,
                    mp_client=mp_client,
                    auto_subscribe=await get_auto_subscribe(),
                    include_specials=await get_include_specials(),
                )
                print(f"[调度器] 自动扫描已触发（距离上次 {interval_hours} 小时）")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[调度器] 出错：{e}")


async def start_scheduler():
    """启动定时扫描调度器"""
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    print("[调度器] 定时扫描已启动")


async def stop_scheduler():
    """停止定时扫描调度器"""
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
