"""
============================================================
扫描任务模块 - 编排一次完整的扫描（核心流程）
============================================================
一次扫描做的事情（按顺序）：
  1. 扫描数据源（strm 目录 / Emby）→ 得到"目前有哪些集"
  2. 确定 TMDB 数据源（MP 代理或直连）
  3. 对每部剧查 TMDB 季信息 → 每季集数 → 算缺集 → 写入数据库
  4. 同步 MoviePilot 订阅状态
  5. 如果开启了"自动订阅"，自动为缺集创建订阅
整个流程在后台线程运行，网页上能实时看到进度（scan_status）
============================================================
"""

import datetime
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import database, logger
from .analyzer import analyze_season, build_fallback_episodes
from .scanner import emby as emby_scanner, filesystem as fs_scanner
from .tmdb_source import TMDBSource

# TMDB 查询并发数（同时查几部剧，太快会被 TMDB 限流）
_CONCURRENCY = 6


class ScanRunner:
    """
    扫描任务管理器（整个程序只有一个实例，在 main.py 里创建）
    """

    def __init__(self, config, mp_client):
        self.config = config          # 配置管理器
        self.mp = mp_client           # MoviePilot 客户端
        self.tmdb_source = TMDBSource(mp_client, config.get("tmdb_key"), config.get("tmdb_lang"))
        self._thread = None           # 后台扫描线程
        # 扫描进度状态（网页轮询这个看进度）
        self.status = {
            "running": False,      # 是否正在扫描
            "phase": "",           # 当前阶段（中文描述）
            "done": 0,             # 已完成数
            "total": 0,            # 总数
            "current": "",         # 当前正在处理的内容
            "started_at": "",      # 开始时间
            "eta_seconds": 0,      # 预计剩余秒数（前端显示"预计剩余 XX 分钟"）
            "auto_subscribed": 0,  # 本次自动订阅了多少个
            "error": "",           # 整体错误信息
        }
        # ETA 计算：记录最近 N 部剧的平均处理耗时（秒），平滑波动
        self._eta_avg_seconds = 0.0
        self._eta_sample_count = 0

    # ============================================================
    # 对外接口
    # ============================================================

    def is_running(self) -> bool:
        """是否正在扫描"""
        return self.status["running"]

    def reset_tmdb_source(self):
        """
        重新创建 TMDB 数据源（修改设置后调用，让新配置立即生效）
        注意：会重新探测数据源模式（MP 代理 / 直连）
        """
        self.tmdb_source = TMDBSource(self.mp, self.config.get("tmdb_key"),
                                      self.config.get("tmdb_lang"))

    def start(self, manual: bool = True) -> tuple:
        """
        开始一次扫描
        参数：manual=True 用户手动点按钮；False 定时任务触发
        返回：(ok, msg)
        """
        if self.is_running():
            return False, "已经在扫描中了，请稍等完成后再试"
        self._thread = threading.Thread(target=self._run_scan, args=(manual,), daemon=True)
        self._thread.start()
        return True, "扫描已开始"

    def get_status(self) -> dict:
        """获取当前进度（网页用）"""
        return dict(self.status)

    # ============================================================
    # 扫描主流程
    # ============================================================

    def _run_scan(self, manual: bool):
        """
        后台执行一次完整扫描（在独立线程里跑，不卡网页）
        """
        self.status.update({
            "running": True, "phase": "准备中...", "done": 0, "total": 0,
            "current": "", "started_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "eta_seconds": 0, "auto_subscribed": 0, "error": "",
        })
        self._eta_avg_seconds = 0.0
        self._eta_sample_count = 0
        logger.log("INFO", "scan", "========== 开始扫描 ==========")

        try:
            # ---- 第一步：确定 TMDB 数据源 ----
            mode = self.tmdb_source.ensure_mode()
            if mode == "none":
                raise RuntimeError("没有可用的 TMDB 数据源。请升级 MoviePilot 到 v3，"
                                   "或在设置页填写 TMDB API Key")

            # ---- 第二步：扫描数据源，得到"目前有哪些集" ----
            self.status["phase"] = "正在扫描媒体库（strm 目录 / Emby）..."
            scan_result = self._scan_sources()

            # ---- 第三步：逐部剧计算缺集 ----
            self._analyze_all(scan_result)

            # ---- 第四步：同步 MoviePilot 订阅状态 ----
            self._sync_subscribes()

            # ---- 第五步：自动订阅（可选） ----
            if self.config.get_bool("auto_subscribe"):
                self._auto_subscribe(scan_result)

            # ---- 记录上次扫描时间 ----
            self.config.set("last_scan", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logger.log("SUCCESS", "scan", f"扫描完成！共处理 {len(scan_result.shows)} 部剧，"
                                          f"自动订阅 {self.status['auto_subscribed']} 条")

        except Exception as e:
            self.status["error"] = str(e)
            logger.log("ERROR", "scan", f"扫描失败：{e}")
        finally:
            self.status["running"] = False
            self.status["phase"] = "扫描结束"
            logger.log("INFO", "scan", "========== 扫描结束 ==========")

    # ============================================================
    # 内部步骤
    # ============================================================

    def _scan_sources(self):
        """
        扫描所有配置的数据源（strm 目录 + Emby），合并结果
        """
        from .models import ScanResult
        merged = ScanResult()

        # 1. 扫描 strm 目录（最常用）
        paths = self.config.get_paths()
        if paths:
            result = fs_scanner.scan(paths)
            merged.shows.update(result.shows)
            merged.unrecognized.extend(result.unrecognized)

        # 2. 扫描 Emby（可选）
        if self.config.get("emby_url") and self.config.get("emby_api_key"):
            logger.log("INFO", "scan", "正在通过 Emby API 扫描媒体库...")
            result = emby_scanner.scan(self.config.get("emby_url"), self.config.get("emby_api_key"))
            merged.shows.update(result.shows)
            merged.unrecognized.extend(result.unrecognized)

        # 3. 什么都没配置 → 报中文错误
        if not paths and not (self.config.get("emby_url") and self.config.get("emby_api_key")):
            raise RuntimeError("没有配置任何媒体库来源：请到设置页填写 strm 目录（或 Emby 信息）")

        logger.log("INFO", "scan", f"扫描完成，共发现 {len(merged.shows)} 部剧，"
                                   f"{len(merged.unrecognized)} 个未识别条目")

        # 4. 保存未识别列表到数据库（网页"未识别"标签页展示）
        #    用批量写入（一次性提交），未识别文件再多也不会拖慢扫描
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        database.execute("DELETE FROM unrecognized")
        if merged.unrecognized:
            database.execute_many(
                "INSERT OR REPLACE INTO unrecognized (path, reason, updated_at) VALUES (?, ?, ?)",
                [(item["path"], item["reason"], now) for item in merged.unrecognized],
            )

        return merged

    def _analyze_all(self, scan_result):
        """
        逐部剧：查 TMDB → 算缺集 → 写入数据库
        用线程池并发查询 TMDB（快），进度实时更新
        """
        shows = list(scan_result.shows.items())
        total = len(shows)
        self.status["total"] = total

        # 确认每部剧的 TMDB 编号是合法数字，否则直接标记"未识别"
        valid_shows = []
        for tmdb_id, info in shows:
            if isinstance(tmdb_id, int):
                valid_shows.append((tmdb_id, info))
            else:
                logger.log("WARN", "scan", f"TMDB 编号异常（{tmdb_id}），已跳过")

        done_count = [0]   # 用列表才能在闭包里修改
        start_time = [time.time()]   # ETA 计算用

        def process_one(item):
            tmdb_id, info = item
            self.status["current"] = info.get("name", f"TMDB:{tmdb_id}")
            try:
                self._analyze_one_show(tmdb_id, info)
            except Exception as e:
                logger.log("ERROR", "scan", f"处理剧《{info.get('name')}》失败：{e}")
                # 标记为 error，网页上能看到这部剧没分析出来
                database.execute(
                    "INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, 'error', ?) "
                    "ON CONFLICT(tmdb_id) DO UPDATE SET status='error', updated_at=excluded.updated_at",
                    (tmdb_id, info.get("name", ""), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
            finally:
                done_count[0] += 1
                self.status["done"] = done_count[0]
                # ETA：每处理一部剧，更新"平均每部耗时"，推算剩余时间
                elapsed = time.time() - start_time[0]
                avg = elapsed / done_count[0]
                if self._eta_avg_seconds <= 0:
                    self._eta_avg_seconds = avg
                else:
                    # 平滑平均（新数据权重 20%），避免个别慢剧导致数字乱跳
                    self._eta_avg_seconds = self._eta_avg_seconds * 0.8 + avg * 0.2
                remaining = total - done_count[0]
                self.status["eta_seconds"] = int(self._eta_avg_seconds * remaining)

        # 并发处理（同时查 6 部剧的 TMDB 数据）
        with ThreadPoolExecutor(max_workers=_CONCURRENCY) as pool:
            list(pool.map(process_one, valid_shows))

        self.status["phase"] = "缺集计算完成"

    def _analyze_one_show(self, tmdb_id: int, info: dict):
        """
        分析单部剧：查 TMDB 季信息 → 每季集列表 → 算缺集 → 入库
        数据质量规则（防误订阅）：
          - TMDB 数据用了旧缓存/降级估算 → 标记 degraded
          - degraded 的季不允许自动订阅（手动订阅也会在网页上提示）
        """
        include_specials = self.config.get_bool("include_specials")

        # 1. 查这部剧的季信息（旧缓存数据会标记 stale）
        show, show_stale = self.tmdb_source.get_show(tmdb_id)
        if show is None:
            database.execute(
                "INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, 'error', ?) "
                "ON CONFLICT(tmdb_id) DO UPDATE SET name=excluded.name, status='error', updated_at=excluded.updated_at",
                (tmdb_id, info.get("name", ""), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            return

        # 2. 逐季查询集列表并计算缺集
        present = info.get("seasons", {})
        today = datetime.date.today()
        season_results = []

        for season in show.seasons:
            season_num = season.season_number
            # 特别篇 S00：默认跳过（可在设置打开）
            if season_num == 0 and not include_specials:
                continue

            # 查 TMDB 该季的全部集（旧缓存数据会标记 stale）
            episodes, eps_stale = self.tmdb_source.get_season_episodes(tmdb_id, season_num)
            degraded = show_stale or eps_stale
            if not episodes:
                # 兜底：用 episode_count 生成退化列表（只有数据源彻底拿不到数据才走到这）
                episodes = build_fallback_episodes(season_num, season.episode_count)
                degraded = True
                logger.log("WARN", "scan", f"《{show.name or info.get('name')}》S{season_num} "
                                           f"查询集数失败，使用估算（数据可能不准）")

            # 计算缺集（degraded 的季标记为数据不可靠，禁止自动订阅）
            result = analyze_season(
                season_num, episodes, present.get(season_num, []), today,
                data_quality="degraded" if degraded else "normal",
            )
            if result:
                season_results.append(result)

        # 3. 写入数据库（整部剧一个事务：要么全写成功，要么全部回滚）
        #    保证扫描过程中数据库永远是"上一轮完整结果"（不会写一半）
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = show.name or info.get("name", "")
        with database.transaction() as conn:
            conn.execute(
                "INSERT INTO shows (tmdb_id, name, year, poster, status, updated_at) "
                "VALUES (?, ?, ?, ?, 'ok', ?) "
                "ON CONFLICT(tmdb_id) DO UPDATE SET name=excluded.name, year=excluded.year, "
                "poster=excluded.poster, status='ok', updated_at=excluded.updated_at",
                (tmdb_id, name, show.year, show.poster, now),
            )
            # 先删掉旧季记录（每次扫描全量重写，简单可靠）
            conn.execute("DELETE FROM seasons WHERE tmdb_id=?", (tmdb_id,))
            for r in season_results:
                conn.execute(
                    "INSERT INTO seasons (tmdb_id, season_number, total_episodes, aired_episodes, "
                    "present_episodes, missing_episodes, status, data_quality) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (tmdb_id, r["season_number"], r["total_episodes"], r["aired_episodes"],
                     json.dumps(r["present_episodes"], ensure_ascii=False),
                     json.dumps(r["missing_episodes"], ensure_ascii=False),
                     r["status"], r["data_quality"]),
                )

        # 记录一下这剧缺了多少（日志方便排查）
        missing_total = sum(len(r["missing_episodes"]) for r in season_results)
        if missing_total:
            logger.log("INFO", "scan", f"《{name}》缺 {missing_total} 集")

    def _sync_subscribes(self):
        """从 MoviePilot 同步订阅状态到本地（更新 subscribe_map 表）"""
        if not (self.mp.url and self.mp.token):
            return
        self.status["phase"] = "正在同步 MoviePilot 订阅状态..."
        try:
            self.mp.sync_subscribe_map()
        except Exception as e:
            logger.log("WARN", "subscribe", f"同步订阅状态出错：{e}")

    # ============================================================
    # 自动订阅
    # ============================================================

    def _auto_subscribe(self, scan_result):
        """
        自动订阅：对每个缺集的季，如果没订阅过、没被忽略，就自动创建订阅
        """
        self.status["phase"] = "自动订阅缺集..."
        count = 0

        # 取当前所有订阅（去重用）
        subscribed = self._get_existing_subscribes()
        ignored = self._get_ignored()

        rows = database.query(
            "SELECT s.tmdb_id, s.season_number, s.missing_episodes, s.data_quality, "
            "sh.name, sh.year "
            "FROM seasons s LEFT JOIN shows sh ON sh.tmdb_id = s.tmdb_id "
            "WHERE s.missing_episodes != '[]' AND s.missing_episodes != '' "
            "AND s.data_quality = 'normal'"   # 数据不准（degraded）的季绝不自动订阅
        )
        for row in rows:
            tmdb_id = row["tmdb_id"]
            season = row["season_number"]
            # 已订阅或已忽略 → 跳过
            if (tmdb_id, season) in subscribed or (tmdb_id, season) in ignored or (tmdb_id, -1) in ignored:
                continue
            missing = json.loads(row["missing_episodes"] or "[]")
            if not missing:
                continue
            # 创建订阅
            ok, msg = self._create_mp_subscribe(row["name"] or "", row["year"] or "", tmdb_id, season)
            if ok:
                count += 1
            else:
                logger.log("WARN", "subscribe", f"自动订阅《{row['name']}》S{season} 失败：{msg}")

        self.status["auto_subscribed"] = count
        if count:
            logger.log("SUCCESS", "subscribe", f"自动订阅完成，共创建 {count} 条订阅")

    # ============================================================
    # 手动订阅（网页按钮点"订阅"时用）
    # ============================================================

    def subscribe_season(self, tmdb_id: int, season: int) -> tuple:
        """
        手动订阅某一季（网页按钮）
        返回：(ok, msg)
        """
        # 查这季的信息（剧名、年份）
        row = database.query_one(
            "SELECT sh.name, sh.year FROM shows sh WHERE sh.tmdb_id=?", (tmdb_id,)
        )
        name = row["name"] if row else f"TMDB:{tmdb_id}"
        year = row["year"] if row else ""

        # 查这一季已播出的集数（作为 total_episode 传给 MP）
        srow = database.query_one(
            "SELECT aired_episodes, data_quality FROM seasons "
            "WHERE tmdb_id=? AND season_number=?",
            (tmdb_id, season),
        )
        total_episode = srow["aired_episodes"] if srow else 0

        # 数据不准的季：允许手动订阅，但明确提醒（数据可能不是最新的）
        if srow and srow["data_quality"] == "degraded":
            logger.log("WARN", "subscribe",
                       f"《{name}》第 {season} 季数据可能不准（TMDB 旧缓存），已提醒用户")
            ok, msg = self._create_mp_subscribe(name, year, tmdb_id, season, total_episode)
            return ok, msg + "（注意：TMDB 数据可能不是最新的，建议稍后刷新缓存再确认）"

        return self._create_mp_subscribe(name, year, tmdb_id, season, total_episode)

    # ============================================================
    # 内部工具
    # ============================================================

    def _create_mp_subscribe(self, name: str, year: str, tmdb_id: int,
                             season: int, total_episode: int = 0) -> tuple:
        """
        真正调用 MoviePilot 创建订阅，并记录到本地
        """
        if not (self.mp.url and self.mp.token):
            return False, "请先到设置页填写 MoviePilot 地址和 API Token"
        if not total_episode:
            total_episode = 24   # 兜底默认值（正常情况不会走到这）

        ok, data = self.mp.create_subscribe(name, year, tmdb_id, season, total_episode)
        if not ok:
            # 常见情况：已经订阅过了 → 记到本地，避免反复尝试
            if "已订阅" in str(data):
                self._record_subscribe(tmdb_id, season, name, 0, "R")
                return False, "已在订阅中"
            return False, data

        mp_id = data if isinstance(data, int) else None
        self._record_subscribe(tmdb_id, season, name, mp_id, "R")
        logger.log("SUCCESS", "subscribe", f"已创建订阅：《{name}》第 {season} 季")
        # 尝试让 MP 立刻搜索（老版本不支持也无妨，定时刷新也会搜）
        if mp_id:
            self.mp.search_subscribe(mp_id)
        return True, f"订阅成功：《{name}》第 {season} 季"

    def _record_subscribe(self, tmdb_id: int, season: int, name: str, mp_id, state: str):
        """
        记录订阅到本地 subscribe_map 表
        同一 (tmdb_id, season) 只能有一条记录（数据库有唯一约束），
        重复记录时只更新状态，不会插第二行（防止重复提交 MoviePilot）
        """
        database.execute(
            "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tmdb_id, season) DO UPDATE SET "
            "mp_id=excluded.mp_id, name=excluded.name, state=excluded.state",
            (tmdb_id, season, mp_id, name, state,
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

    def _get_existing_subscribes(self) -> set:
        """从本地订阅记录里取出所有 (tmdb_id, season) 集合（用于去重）"""
        rows = database.query("SELECT tmdb_id, season FROM subscribe_map")
        return {(r["tmdb_id"], r["season"]) for r in rows}

    def _get_ignored(self) -> set:
        """从忽略表里取出 (tmdb_id, season) 集合"""
        rows = database.query("SELECT tmdb_id, season FROM ignored")
        return {(r["tmdb_id"], r["season"]) for r in rows}
