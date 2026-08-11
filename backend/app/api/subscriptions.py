"""
订阅管理 API 路由 —— 查看/同步/删除 MoviePilot 订阅
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.subscription import Subscription
from ..utils.helpers import make_response
from .deps import get_current_user

router = APIRouter(prefix="/api/subscriptions", tags=["订阅管理"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
):
    """
    获取订阅列表

    优先从 MoviePilot 实时拉取；
    如果 MP 连不上，退回显示本地记录。
    """
    # TODO Step 3+: 从 MoviePilot 实时拉取
    # 目前先返回本地记录
    result = await db.execute(
        select(Subscription).order_by(Subscription.created_at.desc())
    )
    subs = result.scalars().all()

    items = []
    for s in subs:
        items.append({
            "id": s.id,
            "tmdb_id": s.tmdb_id,
            "season": s.season,
            "mp_id": s.mp_id,
            "name": s.name or "",
            "state": s.state,
            "auto": s.auto,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
        })

    return make_response(True, data={
        "source": "local",
        "total": len(items),
        "subscriptions": items,
    })


@router.post("/refresh")
async def refresh_subscriptions(
    db: AsyncSession = Depends(get_db),
):
    """从 MoviePilot 同步订阅状态"""
    # TODO Step 3+: 调用 MoviePilot API 同步
    return make_response(True, message="订阅状态同步完成")


@router.delete("/{mp_id}")
async def delete_subscription(
    mp_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除 MoviePilot 订阅"""
    # TODO Step 3+: 调用 MoviePilot API 删除
    result = await db.execute(
        select(Subscription).where(Subscription.mp_id == mp_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        await db.delete(sub)
        await db.commit()
    return make_response(True, message="已删除订阅")
