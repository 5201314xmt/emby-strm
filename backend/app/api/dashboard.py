"""
仪表盘 API 路由 —— 聚合首页所有数据到一个接口

设计原则：
  前端只需要调一个 /api/dashboard 就能拿到首页全部数据，
  不再需要拼多个接口。后端一次性查询，减少网络往返。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from ..core.database import get_db
from ..models.show import Show
from ..models.season import Season
from ..models.subscription import Subscription
from ..models.unrecognized import UnrecognizedFile
from ..models.scan_job import ScanJob
from ..models.source import Source
from ..utils.helpers import make_response
from .deps import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """
    获取仪表盘所有数据

    一次查询返回：
      - KPI 统计数字（6 项）
      - 当前正在运行的扫描（或无）
      - 最近 3 次扫描历史
    """
    # ---- 1. KPI 统计 ----
    show_count = await db.scalar(
        select(func.count()).select_from(Show).where(Show.status == "ok")
    ) or 0

    # 缺集总数（所有季的 missing_episodes 数组长度总和）
    missing_result = await db.execute(
        text("SELECT COALESCE(SUM(json_array_length(s.missing_episodes)), 0) FROM seasons s WHERE s.missing_episodes != '[]'")
    )
    missing_count = missing_result.scalar() or 0

    # 整季缺失数
    full_missing_count = await db.scalar(
        select(func.count()).select_from(Season).where(Season.status == "full_missing")
    ) or 0

    # 部分缺失剧数（至少有一季是 partial 的剧）
    partial_count = await db.scalar(
        select(func.count(func.distinct(Season.tmdb_id)))
        .select_from(Season)
        .where(Season.status == "partial")
    ) or 0

    # 已订阅数
    subscribed_count = await db.scalar(
        select(func.count()).select_from(Subscription)
    ) or 0

    # 未识别文件数
    unrecognized_count = await db.scalar(
        select(func.count()).select_from(UnrecognizedFile)
    ) or 0

    kpi = {
        "show_count": show_count,
        "missing_count": missing_count,
        "full_missing_count": full_missing_count,
        "subscribed_count": subscribed_count,
        "partial_count": partial_count,
        "unrecognized_count": unrecognized_count,
    }

    # ---- 2. 当前正在运行的扫描 ----
    active_scan = None
    running_job = await db.scalar(
        select(ScanJob).where(ScanJob.status == "running").order_by(ScanJob.id.desc())
    )
    if running_job:
        active_scan = {
            "job_id": running_job.id,
            "status": running_job.status,
            "phase": running_job.phase or "",
            "progress": running_job.progress or 0.0,
            "done_shows": running_job.done_shows or 0,
            "total_shows": running_job.total_shows or 0,
            "current_item": running_job.current_item or "",
            "eta_seconds": running_job.eta_seconds or 0,
        }

    # ---- 3. 最近扫描历史（最近 3 次） ----
    recent_scans = []
    scan_rows = (await db.execute(
        select(ScanJob).order_by(ScanJob.id.desc()).limit(3)
    )).scalars().all()

    for sj in scan_rows:
        # 读取源名称
        source_ids = sj.source_ids or []
        source_names = []
        if source_ids:
            src_rows = (await db.execute(
                select(Source.name).where(Source.id.in_(source_ids))
            )).scalars().all()
            source_names = list(src_rows)

        duration = None
        if sj.started_at and sj.completed_at:
            duration = int((sj.completed_at - sj.started_at).total_seconds())

        recent_scans.append({
            "id": sj.id,
            "status": sj.status,
            "source_names": source_names,
            "started_at": sj.started_at.strftime("%Y-%m-%d %H:%M:%S") if sj.started_at else None,
            "duration_seconds": duration,
            "show_count": sj.done_shows or 0,
            "missing_count": 0,  # 在 scan_job 里不存，后续可扩展
        })

    return make_response(success=True, data={
        "kpi": kpi,
        "active_scan": active_scan,
        "recent_scans": recent_scans,
        "alerts": [],
    })
