"""
扫描 API 路由 —— 控制扫描任务的启停

扫描是异步后台任务，由 tasks/ 模块执行。
API 层只负责接收请求并转给 TaskManager。

WebSocket 是最佳进度获取方式，但保留 HTTP 降级接口。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.database import get_db
from ..models.scan_job import ScanJob
from ..utils.helpers import make_response
from .deps import get_current_user

# TODO Step 4: 替换为 tasks.manager.TaskManager
# 目前用占位符，返回模拟数据
_task_manager = None

router = APIRouter(prefix="/api/scan", tags=["扫描"], dependencies=[Depends(get_current_user)])


def _get_or_create_task_manager():
    """延迟加载 TaskManager（避免循环导入）"""
    global _task_manager
    if _task_manager is None:
        from ..tasks.manager import TaskManager
        _task_manager = TaskManager()
    return _task_manager


@router.post("/start")
async def scan_start(request_body: dict = None, db: AsyncSession = Depends(get_db)):
    """
    开始扫描

    body: {"source_ids": [1, 2]}  可选，指定要扫描的源（空=全部启用源）
    """
    mgr = _get_or_create_task_manager()
    source_ids = (request_body or {}).get("source_ids")
    job_id = await mgr.start_scan(source_ids=source_ids or None)
    return make_response(True, data={"job_id": job_id}, message="扫描已开始")


@router.post("/{job_id}/pause")
async def scan_pause(job_id: int, db: AsyncSession = Depends(get_db)):
    """暂停扫描"""
    mgr = _get_or_create_task_manager()
    ok, msg = await mgr.pause(job_id)
    return make_response(ok, message=msg)


@router.post("/{job_id}/resume")
async def scan_resume(job_id: int, db: AsyncSession = Depends(get_db)):
    """继续扫描"""
    mgr = _get_or_create_task_manager()
    ok, msg = await mgr.resume(job_id)
    return make_response(ok, message=msg)


@router.post("/{job_id}/cancel")
async def scan_cancel(job_id: int, db: AsyncSession = Depends(get_db)):
    """取消扫描"""
    mgr = _get_or_create_task_manager()
    ok, msg = await mgr.cancel(job_id)
    return make_response(ok, message=msg)


@router.get("/{job_id}/status")
async def scan_status(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    获取扫描进度（HTTP 降级接口）

    正常情况前端通过 WebSocket 实时获取进度，
    此接口作为降级方案（WebSocket 连不上时使用）。
    """
    result = await db.execute(select(ScanJob).where(ScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return make_response(False, message="任务不存在")

    return make_response(True, data={
        "job_id": job.id,
        "running": job.status == "running",
        "status": job.status,
        "phase": job.phase or "",
        "progress": job.progress or 0.0,
        "done_shows": job.done_shows or 0,
        "total_shows": job.total_shows or 0,
        "current_item": job.current_item or "",
        "eta_seconds": job.eta_seconds or 0,
        "error": job.error_message or "",
    })


@router.get("/history")
async def scan_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """扫描历史列表"""
    count_result = await db.execute(select(func.count()).select_from(ScanJob))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ScanJob).order_by(ScanJob.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    jobs = result.scalars().all()

    items = []
    for job in jobs:
        items.append({
            "id": job.id,
            "status": job.status,
            "source_ids": job.source_ids or [],
            "phase": job.phase or "",
            "total_shows": job.total_shows or 0,
            "done_shows": job.done_shows or 0,
            "auto_subscribed": job.auto_subscribed or 0,
            "error_message": job.error_message,
            "started_at": job.started_at.strftime("%Y-%m-%d %H:%M:%S") if job.started_at else None,
            "completed_at": job.completed_at.strftime("%Y-%m-%d %H:%M:%S") if job.completed_at else None,
        })

    return make_response(True, data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    })
