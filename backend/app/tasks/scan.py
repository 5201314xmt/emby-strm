"""
扫描任务编排器 —— 完整扫描流程

在一次扫描中按顺序执行：
  1. 扫描数据源（STRM 目录 / Emby）→ 得到"目前有哪些集"
  2. 逐部剧查 TMDB 季信息 → 每季集列表
  3. 计算缺集 → 写入数据库
  4. 同步 MoviePilot 订阅状态
  5. 自动订阅（可选）

扫描过程中每处理一部剧更新进度（写入 ScanJob 表 + 推送 WebSocket）。
"""
import json
import asyncio
from datetime import datetime, date

from ..core.database import AsyncSessionLocal
from ..models.show import Show
from ..models.season import Season
from ..models.scan_job import ScanJob
from ..models.source import Source
from ..models.unrecognized import UnrecognizedFile
from ..models.tmdb_cache import TMDBCache
from ..services.scanner.filesystem import scan_paths as fs_scan
from ..services.scanner.emby import scan_emby
from ..services.tmdb import TMDBSource
from ..services.analyzer import analyze_season, build_fallback_episodes
from ..services.logger import add_log
from ..core.events import event_bus, EventType
from sqlalchemy import select, delete


# TMDB 并发查询数（同时查几部剧）
_CONCURRENCY = 6


def merge_scan_results(target, source, source_id: int):
    """
    合并两个扫描结果：同 TMDB 的季/集取并集，不覆盖。

    修复原版 bug：merged.shows.update(result.shows) 会导致后扫覆盖前扫。
    现在用集合去重、取并集，多源多路径不会丢集。
    """
    for tmdb_id, info in source.shows.items():
        if tmdb_id not in target.shows:
            target.shows[tmdb_id] = {
                "name": info.get("name", ""),
                "source_ids": info.get("source_ids", {source_id}),
                "seasons": dict(info.get("seasons", {})),
            }
        else:
            tgt = target.shows[tmdb_id]
            if hasattr(tgt["source_ids"], 'add'):
                tgt["source_ids"].add(source_id)
            else:
                tgt["source_ids"] = set(tgt["source_ids"]) | {source_id}
            if not tgt.get("name"):
                tgt["name"] = info.get("name", "")
            for season, eps in info.get("seasons", {}).items():
                season_set = tgt["seasons"].setdefault(season, [])
                for ep in eps:
                    if ep not in season_set:
                        season_set.append(ep)
    target.unrecognized.extend(source.unrecognized)


async def run_scan(job_id: int, tmdb_source: TMDBSource, mp_client,
                   auto_subscribe: bool = False,
                   include_specials: bool = False,
                   cancel_check=None, pause_check=None):
    """
    执行一次完整的扫描流程

    Args:
        job_id:           ScanJob 的 ID
        tmdb_source:      TMDB 数据源
        mp_client:        MoviePilot 客户端
        auto_subscribe:   是否扫描后自动订阅
        include_specials: 是否包含特别篇 S00
        cancel_check:     取消检查回调（返回 True 则取消）
        pause_check:      暂停检查回调（会 blocking 等待）
    """

    def _ck():
        """检查是否应该取消"""
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("扫描已取消")

    async def _update(progress: float, phase: str = "", current: str = "",
                       done: int = None, total: int = None, **kwargs):
        """更新 ScanJob 进度 + 推送 WebSocket"""
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                job.progress = progress
                if phase:
                    job.phase = phase
                if current:
                    job.current_item = current
                if done is not None:
                    job.done_shows = done
                if total is not None:
                    job.total_shows = total
                for k, v in kwargs.items():
                    setattr(job, k, v)
                await db.commit()
        await event_bus.publish(EventType.SCAN_PROGRESS, {
            "job_id": job_id, "progress": progress, "phase": phase,
            "current": current, "done": done, "total": total, **kwargs,
        })

    try:
        await _update(5, phase="扫描文件中...", current="获取扫描源列表")

        # ---- 1. 获取启用的扫描源 ----
        async with AsyncSessionLocal() as db:
            sources = (await db.execute(
                select(Source).where(Source.enabled == True)
            )).scalars().all()

        if not sources:
            raise RuntimeError("没有启用的扫描源，请先在设置页添加 STRM 目录或 Emby 源")

        _ck()

        # ---- 2. 扫描数据源，合并结果 ----
        from ..services.scanner.base import ScanResult
        merged = ScanResult()

        for src in sources:
            _ck()
            await _update(10 + sources.index(src) * 10 / len(sources),
                         phase=f"扫描 {src.name}...", current=src.path)
            if src.type == "filesystem":
                # 文件系统扫描是同步 I/O，放到线程池执行
                result = await asyncio.to_thread(fs_scan, [src.path], src.id)
                merge_scan_results(merged, result, src.id)
            elif src.type == "emby":
                if src.emby_url and src.emby_api_key:
                    result = await scan_emby(src.emby_url, src.emby_api_key, src.id)
                    merge_scan_results(merged, result, src.id)

        _ck()
        await _update(25, phase="扫描完成", total=len(merged.shows))

        # ---- 3. 写入未识别文件列表 ----
        async with AsyncSessionLocal() as db:
            await db.execute(delete(UnrecognizedFile))
            for item in merged.unrecognized:
                db.add(UnrecognizedFile(
                    path=item.get("path", ""),
                    source_id=item.get("source_id"),
                    reason=item.get("reason", "未知原因"),
                ))
            await db.commit()

        # ---- 4. 逐部剧: 查 TMDB → 算缺集 → 入库 ----
        shows_list = list(merged.shows.items())
        total_shows = len(shows_list)
        await _update(25, phase="查询 TMDB 数据", total=total_shows, done=0)

        done_count = 0
        start_time = asyncio.get_event_loop().time()
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def process_one(tmdb_id, info):
            nonlocal done_count
            async with sem:
                _ck()
                if pause_check:
                    while pause_check():
                        await asyncio.sleep(1)
                    _ck()  # 恢复后也检查一遍

                name = info.get("name", f"TMDB:{tmdb_id}")
                await _update(
                    min(25 + (done_count / max(total_shows, 1)) * 70, 95),
                    current=name, done=done_count, total=total_shows,
                )

                try:
                    await _analyze_one_show(tmdb_id, info, tmdb_source,
                                           include_specials)
                except Exception as e:
                    await add_log("ERROR", "scan", f"《{name}》分析失败：{e}")

                done_count += 1
                await _update(
                    min(25 + (done_count / max(total_shows, 1)) * 70, 95),
                    done=done_count,
                )

        # 并发处理
        tasks = [asyncio.create_task(process_one(tid, info))
                for tid, info in shows_list]
        await asyncio.gather(*tasks)

        _ck()

        # ---- 5. 同步 MP 订阅状态 ----
        await _update(95, phase="同步订阅状态")
        if mp_client and mp_client.is_configured:
            try:
                await mp_client.sync_subscribe_map()
            except Exception as e:
                await add_log("WARN", "subscribe", f"同步失败：{e}")

        # ---- 6. 自动订阅 ----
        if auto_subscribe and mp_client and mp_client.is_configured:
            await _update(97, phase="自动订阅")
            count = await _auto_subscribe(mp_client)
            async with AsyncSessionLocal() as db:
                job = await db.get(ScanJob, job_id)
                if job:
                    job.auto_subscribed = count
                    await db.commit()

        # ---- 完成 ----
        await _update(100, phase="扫描完成", status="completed",
                     completed_at=datetime.now())
        await event_bus.publish(EventType.SCAN_COMPLETED, {
            "job_id": job_id, "show_count": total_shows,
        })
        await add_log("SUCCESS", "scan", f"扫描完成！共处理 {total_shows} 部剧")

        # 记录上次扫描时间
        from ..core.database import AsyncSessionLocal
        from ..models.setting import Setting
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Setting).where(Setting.key == "last_scan"))
            setting = result.scalar_one_or_none()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if setting:
                setting.value = now_str
            else:
                db.add(Setting(key="last_scan", value=now_str))
            await db.commit()

    except asyncio.CancelledError:
        await _update(progress=0, phase="已取消", status="cancelled",
                     completed_at=datetime.now())
        raise
    except Exception as e:
        await _update(progress=0, phase=f"扫描失败：{e}", status="failed",
                     error_message=str(e), completed_at=datetime.now())
        await add_log("ERROR", "scan", f"扫描失败：{e}")
        await event_bus.publish(EventType.SCAN_FAILED, {
            "job_id": job_id, "error": str(e),
        })


async def _analyze_one_show(tmdb_id: int, info: dict, tmdb_source: TMDBSource,
                            include_specials: bool):
    """分析单部剧：查 TMDB → 每季集列表 → 算缺集 → 写库"""
    # 1. 查剧的季信息
    show, show_stale = await tmdb_source.get_show(tmdb_id)
    if show is None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Show).where(Show.tmdb_id == tmdb_id))
            existing = result.scalar_one_or_none()
            if existing:
                existing.status = "error"
                existing.updated_at = datetime.now()
            else:
                db.add(Show(
                    tmdb_id=tmdb_id,
                    name=info.get("name", ""),
                    status="error",
                ))
            await db.commit()
        return

    # 2. 逐季查询 + 计算
    present = info.get("seasons", {})
    today = date.today()
    season_results = []
    for season in show.seasons:
        sn = season.season_number
        if sn == 0 and not include_specials:
            continue
        eps, eps_stale = await tmdb_source.get_season(tmdb_id, sn)
        degraded = show_stale or eps_stale
        if not eps:
            eps = build_fallback_episodes(sn, season.episode_count)
            degraded = True
            await add_log("WARN", "scan",
                         f"《{show.name or info.get('name')}》S{sn} 查询集数失败，使用估算")
        result = analyze_season(sn, eps, present.get(sn, []), today,
                               data_quality="degraded" if degraded else "normal")
        if result:
            season_results.append(result)

    # 3. 写库（一个事务）
    now = datetime.now()
    name = show.name or info.get("name", "")
    source_ids = list(info.get("source_ids", set()))

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Show).where(Show.tmdb_id == tmdb_id))
        existing = result.scalar_one_or_none()
        if existing:
            existing.name = name or existing.name
            existing.year = show.year or existing.year
            existing.poster = show.poster or existing.poster
            existing.status = "ok"
            existing.source_ids = source_ids
            existing.updated_at = now
        else:
            db.add(Show(
                tmdb_id=tmdb_id, name=name, year=show.year,
                poster=show.poster, status="ok", source_ids=source_ids,
            ))
        # 清旧季记录，写新记录
        await db.execute(delete(Season).where(Season.tmdb_id == tmdb_id))
        await db.flush()
        for r in season_results:
            db.add(Season(
                tmdb_id=tmdb_id,
                season_number=r["season_number"],
                total_episodes=r["total_episodes"],
                aired_episodes=r["aired_episodes"],
                present_episodes=r["present_episodes"],
                missing_episodes=r["missing_episodes"],
                status=r["status"],
                data_quality=r["data_quality"],
            ))
        await db.commit()

    missing_total = sum(len(r["missing_episodes"]) for r in season_results)
    if missing_total:
        await add_log("INFO", "scan", f"《{name}》缺 {missing_total} 集")


async def _auto_subscribe(mp_client) -> int:
    """自动订阅所有缺集（跳过已订阅/已忽略/degraded）"""
    count = 0
    async with AsyncSessionLocal() as db:
        # 获取已订阅 (tmdb_id, season) 集合
        from ..models.subscription import Subscription
        from ..models.ignored import Ignored
        sub_result = await db.execute(select(Subscription.tmdb_id, Subscription.season))
        subscribed = {(r[0], r[1]) for r in sub_result.all()}
        ign_result = await db.execute(select(Ignored.tmdb_id, Ignored.season))
        ignored = {(r[0], r[1]) for r in ign_result.all()}

        season_result = await db.execute(
            select(Season).where(
                Season.status.in_(["partial", "full_missing"]),
                Season.data_quality == "normal",
            )
        )
        seasons = season_result.scalars().all()

        for s in seasons:
            key = (s.tmdb_id, s.season_number)
            if key in subscribed or key in ignored or (s.tmdb_id, -1) in ignored:
                continue
            if not s.missing_episodes:
                continue
            show_result = await db.execute(select(Show).where(Show.tmdb_id == s.tmdb_id))
            show = show_result.scalar_one_or_none()
            name = show.name if show else f"TMDB:{s.tmdb_id}"
            year = show.year if show else ""
            total_ep = s.aired_episodes or 24
            ok, data = await mp_client.create_subscribe(
                name, year, s.tmdb_id, s.season_number, total_ep)
            if ok:
                mp_id = data if isinstance(data, int) else None
                db.add(Subscription(
                    tmdb_id=s.tmdb_id, season=s.season_number,
                    mp_id=mp_id, name=name, state="R", auto=True,
                ))
                count += 1
                if mp_id:
                    await mp_client.search_subscribe(mp_id)
        await db.commit()
    return count
