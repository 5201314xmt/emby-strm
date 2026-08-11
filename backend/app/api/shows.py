"""
缺集列表 API 路由 —— 核心功能接口

提供：
  - 缺集列表（分页 + 筛选 + 搜索）
  - 单剧详情
  - 订阅/忽略单季
  - 批量订阅/忽略
"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional

from ..core.database import get_db
from ..models.show import Show
from ..models.season import Season
from ..models.subscription import Subscription
from ..models.ignored import Ignored
from ..models.source import Source
from ..utils.helpers import make_response
from .deps import get_current_user

router = APIRouter(prefix="/api/shows", tags=["缺集列表"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_shows(
    source_id: Optional[int] = Query(None, description="按扫描源 ID 筛选"),
    status: Optional[str] = Query(None, description="partial|full_missing|complete|ignored|error"),
    search: Optional[str] = Query(None, description="搜索剧名关键字"),
    sort: str = Query("missing_count", description="排序方式：missing_count|name"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取缺集列表（支持分页、筛选、搜索）

    核心查询逻辑：
      1. 从 shows 表出发，LEFT JOIN seasons 和 subscriptions
      2. 根据筛选条件拼接 WHERE
      3. 按缺集数量降序排序（最缺的排最前）
      4. 分页返回
    """
    # ---- 构建基础查询 ----
    query = select(Show).distinct()

    # ---- 筛选条件 ----
    conditions = []

    # 按扫描源筛选（shows.source_ids 是 JSON 数组，检查是否包含指定 source_id）
    if source_id:
        from sqlalchemy import text as sa_text
        conditions.append(
            sa_text(f"json_array_length(json_extract(shows.source_ids, '$')) > 0 "
                    f"AND EXISTS (SELECT 1 FROM json_each(shows.source_ids) WHERE value = {source_id})")
        )

    # 按状态筛选
    if status == "partial":
        conditions.append(
            Show.tmdb_id.in_(
                select(Season.tmdb_id).where(Season.status == "partial").distinct()
            )
        )
    elif status == "full_missing":
        conditions.append(
            Show.tmdb_id.in_(
                select(Season.tmdb_id).where(Season.status == "full_missing").distinct()
            )
        )
    elif status == "complete":
        # 所有季都不是 partial 也不是 full_missing
        not_in_ids = select(Season.tmdb_id).where(
            Season.status.in_(["partial", "full_missing"])
        ).distinct()
        conditions.append(Show.tmdb_id.notin_(not_in_ids))
        conditions.append(Show.status == "ok")
    elif status == "ignored":
        conditions.append(Show.ignore_entire == True)
    elif status == "error":
        conditions.append(Show.status == "error")

    # 搜索
    if search:
        conditions.append(Show.name.ilike(f"%{search}%"))

    if conditions:
        query = query.where(and_(*conditions))

    # ---- 计数 ----
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # ---- 排序 ----
    if sort == "name":
        query = query.order_by(Show.name.asc())
    else:
        query = query.order_by(Show.updated_at.desc())

    # ---- 分页 ----
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    shows = result.scalars().all()

    if not shows:
        return make_response(success=True, data={
            "total": total, "page": page, "page_size": page_size, "items": []
        })

    # ---- 批量加载关联数据（防 N+1） ----
    show_ids = [s.tmdb_id for s in shows]

    # 批量查 seasons
    all_seasons = (await db.execute(
        select(Season).where(Season.tmdb_id.in_(show_ids)).order_by(Season.season_number)
    )).scalars().all()
    season_map = {}   # {tmdb_id: [Season]}
    for s in all_seasons:
        season_map.setdefault(s.tmdb_id, []).append(s)

    # 批量查 subscriptions
    all_subs = (await db.execute(
        select(Subscription).where(Subscription.tmdb_id.in_(show_ids))
    )).scalars().all()
    sub_map = {}   # {tmdb_id: {season: Subscription}}
    for s in all_subs:
        sub_map.setdefault(s.tmdb_id, {})[s.season] = s

    # 批量查 ignored
    all_ignored = (await db.execute(
        select(Ignored).where(Ignored.tmdb_id.in_(show_ids))
    )).scalars().all()
    ignored_map = {}   # {tmdb_id: {season1, season2, ..., -1}}
    for ig in all_ignored:
        ignored_map.setdefault(ig.tmdb_id, set()).add(ig.season)

    # ---- 批量查源名称 ----
    all_source_ids = set()
    for s in shows:
        all_source_ids.update(s.source_ids or [])
    source_names = {}
    if all_source_ids:
        src_rows = (await db.execute(
            select(Source.id, Source.name).where(Source.id.in_(all_source_ids))
        )).all()
        for src_id, src_name in src_rows:
            source_names[src_id] = src_name

    # ---- 组装响应 ----
    items = []
    for show in shows:
        seasons_data = []
        for season in season_map.get(show.tmdb_id, []):
            subs_for_show = sub_map.get(show.tmdb_id, {})
            sub = subs_for_show.get(season.season_number)
            ignored_set = ignored_map.get(show.tmdb_id, set())
            seasons_data.append({
                "season_number": season.season_number,
                "total_episodes": season.total_episodes,
                "aired_episodes": season.aired_episodes,
                "present_count": len(season.present_episodes or []),
                "missing_count": len(season.missing_episodes or []),
                "missing_episodes": season.missing_episodes or [],
                "status": season.status,
                "data_quality": season.data_quality,
                "subscribed": sub is not None,
                "ignored": season.season_number in ignored_set,
                "mp_state": sub.state if sub else "",
            })

        # 源名字列表
        snames = [source_names.get(sid, f"源{sid}") for sid in (show.source_ids or [])]

        items.append({
            "tmdb_id": show.tmdb_id,
            "name": show.name,
            "year": show.year or "",
            "poster": show.poster or "",
            "source_ids": show.source_ids or [],
            "source_names": snames,
            "ignore_entire": show.ignore_entire,
            "seasons": seasons_data,
        })

    return make_response(success=True, data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    })


@router.get("/{tmdb_id}")
async def get_show_detail(
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取单剧详情（抽屉展开用）"""
    result = await db.execute(select(Show).where(Show.tmdb_id == tmdb_id))
    show = result.scalar_one_or_none()
    if not show:
        return make_response(False, message="未找到该剧")

    seasons = (await db.execute(
        select(Season).where(Season.tmdb_id == tmdb_id).order_by(Season.season_number)
    )).scalars().all()
    subs = (await db.execute(
        select(Subscription).where(Subscription.tmdb_id == tmdb_id)
    )).scalars().all()
    subs_map = {s.season: s for s in subs}
    ignored_set = set()
    ignored_rows = (await db.execute(
        select(Ignored.season).where(Ignored.tmdb_id == tmdb_id)
    )).scalars().all()
    for s in ignored_rows:
        ignored_set.add(s)

    snames = []
    if show.source_ids:
        src_rows = (await db.execute(
            select(Source.name).where(Source.id.in_(show.source_ids))
        )).scalars().all()
        snames = [r[0] for r in src_rows]

    return make_response(success=True, data={
        "tmdb_id": show.tmdb_id,
        "name": show.name,
        "year": show.year or "",
        "poster": show.poster or "",
        "overview": show.overview or "",
        "source_names": snames,
        "seasons": [
            {
                "season_number": s.season_number,
                "total_episodes": s.total_episodes,
                "aired_episodes": s.aired_episodes,
                "present_episodes": s.present_episodes or [],
                "missing_episodes": s.missing_episodes or [],
                "status": s.status,
                "data_quality": s.data_quality,
                "subscribed": s.season_number in subs_map,
                "ignored": s.season_number in ignored_set,
                "mp_state": subs_map[s.season_number].state if s.season_number in subs_map else "",
            }
            for s in seasons
        ],
    })


@router.post("/{tmdb_id}/subscribe")
async def subscribe_season(
    tmdb_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    订阅某一季（向 MoviePilot 创建订阅）

    body: {"season": 1}
    """
    body = await request.json() or {}
    season = int(body.get("season", 1))

    # TODO: 调用 services/subscription.py 的 create_subscription
    return make_response(True, message=f"订阅请求已提交：TMDB:{tmdb_id} S{season}")


@router.post("/{tmdb_id}/ignore")
async def ignore_season(
    tmdb_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    忽略某季或整部剧

    body: {"season": 1}  或  {"season": -1}（-1=整部剧）
    """
    body = await request.json() or {}
    season = int(body.get("season", -1))

    # 检查是否已存在
    existing = await db.scalar(
        select(Ignored).where(Ignored.tmdb_id == tmdb_id, Ignored.season == season)
    )
    if not existing:
        db.add(Ignored(tmdb_id=tmdb_id, season=season))

    # 如果是整部剧，更新 show.ignore_entire
    if season == -1:
        show = await db.get(Show, tmdb_id)
        if show:
            show.ignore_entire = True

    await db.commit()

    scope = "整部剧" if season == -1 else f"第 {season} 季"
    return make_response(True, message=f"已忽略{scope}")


@router.delete("/{tmdb_id}/ignore")
async def unignore_season(
    tmdb_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """取消忽略"""
    body = await request.json() or {}
    season = int(body.get("season", -1))

    result = await db.execute(
        select(Ignored).where(Ignored.tmdb_id == tmdb_id, Ignored.season == season)
    )
    ignored = result.scalar_one_or_none()
    if ignored:
        await db.delete(ignored)

    if season == -1:
        show = await db.get(Show, tmdb_id)
        if show:
            show.ignore_entire = False

    await db.commit()
    return make_response(True, message="已取消忽略")


@router.post("/batch/subscribe")
async def batch_subscribe(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """批量订阅"""
    body = await request.json() or {}
    items = body.get("items") or []
    if not items:
        return make_response(False, message="没有选择要订阅的季")

    # TODO: 调用订阅服务批量创建
    return make_response(True, message=f"批量订阅已提交，共 {len(items)} 项")


@router.post("/batch/ignore")
async def batch_ignore(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """批量忽略"""
    body = await request.json() or {}
    items = body.get("items") or []
    if not items:
        return make_response(False, message="没有选择要忽略的项")

    for it in items:
        tmdb_id = int(it.get("tmdb_id"))
        season = int(it.get("season", -1))
        existing = await db.scalar(
            select(Ignored).where(Ignored.tmdb_id == tmdb_id, Ignored.season == season)
        )
        if not existing:
            db.add(Ignored(tmdb_id=tmdb_id, season=season))
        if season == -1:
            show = await db.get(Show, tmdb_id)
            if show:
                show.ignore_entire = True

    await db.commit()
    return make_response(True, message=f"已批量忽略 {len(items)} 项")
