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
async def list_subscriptions(db: AsyncSession = Depends(get_db)):
    """获取订阅列表（从本地数据库）"""
    result = await db.execute(
        select(Subscription).order_by(Subscription.created_at.desc())
    )
    subs = result.scalars().all()
    items = [{
        "id": s.id, "tmdb_id": s.tmdb_id, "season": s.season,
        "mp_id": s.mp_id, "name": s.name or "", "state": s.state,
        "auto": s.auto,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    } for s in subs]
    return make_response(True, data={"source": "local", "total": len(items), "subscriptions": items})


@router.post("/refresh")
async def refresh_subscriptions(db: AsyncSession = Depends(get_db)):
    """从 MoviePilot 同步订阅状态到本地"""
    from ..core.app_state import mp_client
    if not mp_client.is_configured:
        return make_response(False, message="请先在设置页填写 MoviePilot 地址和 API Token")
    try:
        count = await mp_client.sync_subscribe_map()
        return make_response(True, data={"count": count}, message=f"已同步 {count} 条订阅状态")
    except Exception as e:
        return make_response(False, message=f"同步失败：{e}")


@router.delete("/{mp_id}")
async def delete_subscription(mp_id: int, db: AsyncSession = Depends(get_db)):
    """删除 MoviePilot 订阅（同时删除本地记录）"""
    from ..core.app_state import mp_client
    if not mp_client.is_configured:
        return make_response(False, message="请先在设置页填写 MoviePilot 地址和 API Token")
    if not mp_id:
        return make_response(False, message="缺少 MP 订阅 ID")
    try:
        ok, msg = await mp_client.delete_subscribe(mp_id)
        if ok:
            # 同步删除本地记录
            result = await db.execute(select(Subscription).where(Subscription.mp_id == mp_id))
            sub = result.scalar_one_or_none()
            if sub:
                await db.delete(sub)
                await db.commit()
        return make_response(ok, message=msg)
    except Exception as e:
        return make_response(False, message=f"删除失败：{e}")
