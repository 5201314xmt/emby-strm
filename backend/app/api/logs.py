"""
日志 API 路由 —— 查询/清空操作日志
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Optional

from ..core.database import get_db
from ..models.log import Log
from ..utils.helpers import make_response
from .deps import get_current_user

router = APIRouter(prefix="/api/logs", tags=["日志"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_logs(
    level: Optional[str] = Query(None, description="日志级别：INFO|SUCCESS|WARN|ERROR"),
    category: Optional[str] = Query(None, description="日志分类：system|scan|subscribe|tmdb"),
    search: Optional[str] = Query(None, description="搜索关键字"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(200, ge=1, le=1000, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """获取日志列表（支持按级别/分类筛选 + 关键字搜索 + 分页）"""
    query = select(Log)

    if level:
        query = query.where(Log.level == level.upper())
    if category:
        query = query.where(Log.category == category)
    if search:
        query = query.where(Log.message.ilike(f"%{search}%"))

    # 最新的排前面
    query = query.order_by(Log.id.desc())

    # 总数（包含搜索过滤）
    count_query = select(func.count(Log.id))
    if level:
        count_query = count_query.where(Log.level == level.upper())
    if category:
        count_query = count_query.where(Log.category == category)
    if search:
        count_query = count_query.where(Log.message.ilike(f"%{search}%"))
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    items = []
    for log in logs:
        items.append({
            "id": log.id,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
            "level": log.level,
            "category": log.category,
            "source": log.source,
            "message": log.message,
        })

    return make_response(True, data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    })


@router.delete("")
async def clear_logs(db: AsyncSession = Depends(get_db)):
    """清空全部日志"""
    await db.execute(delete(Log))
    await db.commit()
    return make_response(True, message="日志已清空")
