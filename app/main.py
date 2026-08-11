"""
============================================================
缺集管家 - 程序入口（FastAPI 应用 + 所有网页接口）
============================================================
说明：
  - 这个文件负责"网页和 API 的接口层"，具体干活的功能都在各个模块里
  - 每个接口都返回中文提示，出错时小白也能看懂
  - 接口一览（网页上实际用到的）：
      GET  /api/status              程序状态（首次使用引导用）
      GET  /api/overview            首页统计数字
      GET  /api/shows               缺集列表
      GET  /api/unrecognized        未识别文件列表
      POST /api/scan                开始扫描
      GET  /api/scan/status         扫描进度
      POST /api/shows/{id}/subscribe    订阅某一季
      POST /api/subscribe/all       一键订阅所有缺集
      GET  /api/subscriptions       订阅管理列表
      DELETE /api/subscriptions/{id}   删除订阅
      POST /api/subscriptions/refresh  重新同步订阅状态
      GET/POST /api/settings        设置
      POST /api/settings/test       测试连接
      GET/DELETE /api/logs          日志
============================================================
"""

import datetime
import json
import os
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import auth, database, logger
from .config import CONFIG_DEFS, Config
from .moviepilot import MoviePilotClient
from .scan_runner import ScanRunner

# ------------------------------------------------------------
# 应用初始化
# ------------------------------------------------------------

# 创建 FastAPI 应用（title 显示在浏览器标题栏）
app = FastAPI(title="缺集管家")

# 程序全局对象（启动时初始化）：
config = Config()                          # 配置管理器
mp_client = MoviePilotClient(config.get("mp_url"), config.get("mp_token"))  # MP 客户端
runner = ScanRunner(config, mp_client)     # 扫描任务管理器

# 网页文件目录
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


@app.on_event("startup")
def startup():
    """程序启动时执行：初始化数据库 + 启动定时扫描线程"""
    database.init_db()
    logger.log("INFO", "system", "缺集管家已启动，欢迎使用！")
    # 启动定时扫描线程（后台一直运行，不阻塞主程序）
    threading.Thread(target=_scheduler_loop, daemon=True).start()


def _scheduler_loop():
    """
    定时扫描线程：每隔 60 秒检查一次
    如果开了"自动扫描"且距离上次扫描超过了设置的小时数 → 自动开始扫描
    """
    while True:
        time.sleep(60)
        try:
            if not config.get_bool("auto_scan"):
                continue
            if runner.is_running():
                continue
            interval_hours = config.get_int("scan_interval", 12)
            last = config.get("last_scan")
            if not last:
                continue   # 从没扫过 → 等用户在网页上点"开始扫描"
            try:
                last_dt = datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            elapsed = (datetime.datetime.now() - last_dt).total_seconds()
            if elapsed >= interval_hours * 3600:
                logger.log("INFO", "scan", f"自动扫描触发（距离上次 {interval_hours} 小时）")
                runner.start(manual=False)
        except Exception as e:
            logger.log("WARN", "system", f"定时扫描线程出错：{e}")


# ------------------------------------------------------------
# 小工具函数
# ------------------------------------------------------------

def _ok(data=None, message: str = "成功"):
    """统一返回成功 JSON"""
    return JSONResponse({"success": True, "message": message, "data": data})


def _fail(message: str, status_code: int = 200):
    """统一返回失败 JSON（状态码默认 200，方便前端统一处理）"""
    return JSONResponse({"success": False, "message": message, "data": None},
                        status_code=status_code)


# ------------------------------------------------------------
# 登录认证（中间件）
# ------------------------------------------------------------

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    登录保护中间件：
      - 除 登录相关接口(/api/auth/*) 和 健康检查(/api/health) 外，
        所有 /api/* 接口都要求已登录
      - 没登录统一返回 401，网页会自动跳转到登录页
      - 后台扫描线程不受影响（认证只挡 HTTP 入口）
    """
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/") and path != "/api/health":
        if not auth.validate_session(request.cookies.get("queji_session")):
            return JSONResponse({"success": False, "message": "请先登录", "data": None},
                                status_code=401)
    return await call_next(request)


# ------------------------------------------------------------
# 登录认证接口
# ------------------------------------------------------------

@app.get("/api/auth/status")
def api_auth_status(request: Request):
    """登录状态：是否已初始化（首次要设置密码）、是否已登录"""
    return _ok({
        "initialized": auth.is_initialized(),
        "logged_in": auth.validate_session(request.cookies.get("queji_session")),
    })


@app.post("/api/auth/setup")
async def api_auth_setup(request: Request):
    """首次使用：设置管理员密码（只能设置一次，之后改密码在设置页）"""
    if auth.is_initialized():
        return _fail("系统已初始化，如需修改密码请到设置页")
    body = await request.json() or {}
    password = str(body.get("password", ""))
    if len(password) < 6:
        return _fail("密码至少 6 位")
    auth.set_setting("admin_password_hash", auth.hash_password(password))
    # 设置成功后自动登录，直接进入使用流程
    token = auth.create_session()
    resp = _ok(message="设置成功，请牢记你的密码")
    resp.set_cookie("queji_session", token, httponly=True, samesite="lax",
                    max_age=30 * 24 * 3600)
    logger.log("SUCCESS", "system", "管理员密码已设置")
    return resp


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """登录：密码正确后下发登录 Cookie"""
    if not auth.is_initialized():
        return _fail("系统还未初始化，请先设置管理员密码")
    body = await request.json() or {}
    password = str(body.get("password", ""))
    if not auth.verify_password(password, auth.get_setting("admin_password_hash")):
        # 错误密码稍作等待，减慢暴力破解
        time.sleep(1)
        return _fail("密码不正确")
    auth.cleanup_expired_sessions()
    token = auth.create_session()
    resp = _ok(message="登录成功")
    resp.set_cookie("queji_session", token, httponly=True, samesite="lax",
                    max_age=30 * 24 * 3600)
    return resp


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    """退出登录：销毁会话并清除 Cookie"""
    auth.destroy_session(request.cookies.get("queji_session"))
    resp = _ok(message="已退出登录")
    resp.delete_cookie("queji_session")
    return resp


@app.post("/api/auth/change-password")
async def api_auth_change_password(request: Request):
    """修改密码（需要输入当前密码验证；改完后其他设备全部重新登录）"""
    token = request.cookies.get("queji_session")
    if not auth.validate_session(token):
        return JSONResponse({"success": False, "message": "请先登录", "data": None},
                            status_code=401)
    body = await request.json() or {}
    old = str(body.get("old_password", ""))
    new = str(body.get("new_password", ""))
    if not auth.verify_password(old, auth.get_setting("admin_password_hash")):
        return _fail("当前密码不正确")
    if len(new) < 6:
        return _fail("新密码至少 6 位")
    auth.set_setting("admin_password_hash", auth.hash_password(new))
    # 让其他设备重新登录（当前设备保留）
    database.execute("DELETE FROM sessions WHERE token != ?", (token,))
    logger.log("INFO", "system", "管理员密码已修改")
    return _ok(message="密码已修改，请牢记新密码")


@app.get("/api/health")
def api_health():
    """健康检查（Docker 用，不需要登录）"""
    return _ok({"status": "ok"})


def _get_show_with_state(tmdb_id: int, show_row, season_rows: list) -> dict:
    """
    把数据库里的剧 + 季数据，组装成网页需要的结构（带订阅/忽略状态）
    """
    show = dict(show_row)
    # 该剧的订阅记录和忽略记录（一次查好，避免循环里反复查库）
    subs = {(r["season"]): r for r in database.query(
        "SELECT season, mp_id, state FROM subscribe_map WHERE tmdb_id=?", (tmdb_id,))}
    ignores = {r["season"] for r in database.query(
        "SELECT season FROM ignored WHERE tmdb_id=?", (tmdb_id,))}

    seasons = []
    for r in season_rows:
        s = dict(r)
        s["missing_episodes"] = json.loads(r["missing_episodes"] or "[]")
        s["present_episodes"] = json.loads(r["present_episodes"] or "[]")
        s["ignored"] = 1 if r["season_number"] in ignores else 0
        sub = subs.get(r["season_number"])
        s["subscribed"] = 1 if sub else 0
        s["mp_id"] = sub["mp_id"] if sub else None
        s["mp_state"] = sub["state"] if sub else ""
        seasons.append(s)

    show["ignore"] = 1 if -1 in ignores else 0
    show["seasons"] = seasons
    return show


# ------------------------------------------------------------
# 网页页面
# ------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index_page():
    """主页（浏览器打开 http://IP:8899 看到的面板）"""
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/login.html", include_in_schema=False)
def login_page():
    """登录页"""
    return FileResponse(os.path.join(WEB_DIR, "login.html"))


@app.get("/setup.html", include_in_schema=False)
def setup_page():
    """首次安装向导页"""
    return FileResponse(os.path.join(WEB_DIR, "setup.html"))


@app.get("/style.css", include_in_schema=False)
def style_css():
    return FileResponse(os.path.join(WEB_DIR, "style.css"))


@app.get("/app.js", include_in_schema=False)
def app_js():
    return FileResponse(os.path.join(WEB_DIR, "app.js"))


@app.get("/login.js", include_in_schema=False)
def login_js():
    return FileResponse(os.path.join(WEB_DIR, "login.js"))


@app.get("/setup.js", include_in_schema=False)
def setup_js():
    return FileResponse(os.path.join(WEB_DIR, "setup.js"))


# ------------------------------------------------------------
# 程序状态（首次使用引导）
# ------------------------------------------------------------

@app.get("/api/status")
def api_status():
    """程序整体状态：配置是否齐全、数据源模式等（前端引导用）"""
    complete = config.is_complete()
    return _ok({
        "config_ok": complete["ok"],
        "missing": complete["missing"],
        "tmdb_mode": runner.tmdb_source.ensure_mode(),
        "last_scan": config.get("last_scan"),
        "scan_running": runner.is_running(),
        "auto_scan": config.get_bool("auto_scan"),
        "auto_subscribe": config.get_bool("auto_subscribe"),
    })


# ------------------------------------------------------------
# 概览（首页统计）
# ------------------------------------------------------------

@app.get("/api/overview")
def api_overview():
    """首页的统计数字"""
    show_count = database.query_one("SELECT COUNT(*) c FROM shows WHERE status!='error'")["c"]
    error_count = database.query_one("SELECT COUNT(*) c FROM shows WHERE status='error'")["c"]
    missing_count = database.query_one(
        "SELECT COALESCE(SUM(json_array_length(missing_episodes)),0) c FROM seasons "
        "WHERE missing_episodes != '[]' AND missing_episodes != ''")["c"]
    full_missing_seasons = database.query_one(
        "SELECT COUNT(*) c FROM seasons WHERE status='full_missing'")["c"]
    partial_shows = database.query_one(
        "SELECT COUNT(DISTINCT tmdb_id) c FROM seasons WHERE status='partial'")["c"]
    subscribed_count = database.query_one("SELECT COUNT(*) c FROM subscribe_map")["c"]
    unrecognized_count = database.query_one("SELECT COUNT(*) c FROM unrecognized")["c"]
    return _ok({
        "show_count": show_count,
        "error_count": error_count,
        "missing_count": missing_count,
        "full_missing_seasons": full_missing_seasons,
        "partial_shows": partial_shows,
        "subscribed_count": subscribed_count,
        "unrecognized_count": unrecognized_count,
    })


# ------------------------------------------------------------
# 缺集列表
# ------------------------------------------------------------

@app.get("/api/shows")
def api_shows(filter_type: str = "all", q: str = "", limit: int = 50, offset: int = 0):
    """
    缺集列表（网页"缺集"页）
    参数：
      filter_type: all=全部 partial=缺集补全 full_missing=整季缺失
                   ignored=已忽略 complete=完整 error=异常
      q: 搜索剧名关键字
      limit/offset: 分页（一次最多返回 limit 部剧，前端"加载更多"翻页）
    """
    # 先找出符合条件的所有剧（按缺集数从多到少排，最着急的排最前）
    where = ""
    params = []
    if q:
        where += " AND sh.name LIKE ?"
        params.append(f"%{q}%")

    if filter_type == "partial":
        where += " AND sh.tmdb_id IN (SELECT tmdb_id FROM seasons WHERE status='partial')"
    elif filter_type == "full_missing":
        where += " AND sh.tmdb_id IN (SELECT tmdb_id FROM seasons WHERE status='full_missing')"
    elif filter_type == "ignored":
        where += " AND sh.tmdb_id IN (SELECT tmdb_id FROM ignored)"
    elif filter_type == "complete":
        where += (" AND sh.tmdb_id NOT IN "
                  "(SELECT tmdb_id FROM seasons WHERE status IN ('partial','full_missing'))")
    elif filter_type == "error":
        where += " AND sh.status='error'"

    # 总数（前端分页和角标用）
    total = database.query_one(
        f"SELECT COUNT(*) c FROM shows sh WHERE 1=1 {where}", tuple(params))["c"]
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    show_rows = database.query(
        f"SELECT * FROM shows sh WHERE 1=1 {where} "
        "ORDER BY (SELECT COALESCE(SUM(json_array_length(s.missing_episodes)),0) "
        "FROM seasons s WHERE s.tmdb_id=sh.tmdb_id) DESC "
        "LIMIT ? OFFSET ?",
        tuple(params) + (limit, offset),
    )

    # 组装每部剧的数据（带上季、订阅状态、忽略状态）
    shows = []
    for show_row in show_rows:
        season_rows = database.query(
            "SELECT * FROM seasons WHERE tmdb_id=? ORDER BY season_number", (show_row["tmdb_id"],))
        shows.append(_get_show_with_state(show_row["tmdb_id"], show_row, season_rows))

    return _ok({"total": total, "shows": shows})


@app.get("/api/unrecognized")
def api_unrecognized(limit: int = 100, offset: int = 0):
    """未识别列表（扫描时看不懂的文件/目录），分页返回"""
    total = database.query_one("SELECT COUNT(*) c FROM unrecognized")["c"]
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    rows = database.query(
        "SELECT * FROM unrecognized ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset))
    return _ok({"total": total, "items": [dict(r) for r in rows]})


# ------------------------------------------------------------
# 扫描
# ------------------------------------------------------------

@app.post("/api/scan")
def api_scan():
    """开始一次扫描（网页"开始扫描"按钮）"""
    ok, msg = runner.start(manual=True)
    return _ok(message=msg) if ok else _fail(msg)


@app.get("/api/scan/status")
def api_scan_status():
    """扫描进度（前端轮询这个接口刷新进度条）"""
    return _ok(runner.get_status())


# ------------------------------------------------------------
# 订阅操作
# ------------------------------------------------------------

@app.post("/api/shows/{tmdb_id}/subscribe")
async def api_subscribe(tmdb_id: int, request: Request):
    """订阅某一季（body: {"season": 1}）"""
    body = await request.json()
    season = int(body.get("season", 1))
    ok, msg = runner.subscribe_season(tmdb_id, season)
    return _ok(message=msg) if ok else _fail(msg)


@app.post("/api/shows/{tmdb_id}/ignore")
async def api_ignore(tmdb_id: int, request: Request):
    """
    忽略某一季（body: {"season": 1}）
    season = -1 表示忽略整部剧（网页上"忽略整部剧"按钮）
    """
    body = await request.json()
    season = int(body.get("season", -1))
    database.execute(
        "INSERT OR REPLACE INTO ignored (tmdb_id, season) VALUES (?, ?)",
        (tmdb_id, season),
    )
    text = "整部剧" if season == -1 else f"第 {season} 季"
    logger.log("INFO", "subscribe", f"已忽略 TMDB:{tmdb_id} {text}")
    return _ok(message=f"已忽略{text}，不会再出现在缺集列表里")


@app.post("/api/shows/{tmdb_id}/unignore")
async def api_unignore(tmdb_id: int, request: Request):
    """取消忽略（body: {"season": 1}）"""
    body = await request.json()
    season = int(body.get("season", -1))
    database.execute(
        "DELETE FROM ignored WHERE tmdb_id=? AND season=?", (tmdb_id, season))
    return _ok(message="已取消忽略")


@app.post("/api/subscribe/all")
def api_subscribe_all():
    """
    一键订阅所有缺集（还没订阅的、没被忽略的季全部创建订阅）
    适合小白：扫描完点一下，剩下的交给 MoviePilot
    数据不准（degraded）的季自动跳过，绝不因 TMDB 故障批量误订阅
    """
    rows = database.query(
        "SELECT s.tmdb_id, s.season_number, sh.name, sh.year "
        "FROM seasons s LEFT JOIN shows sh ON sh.tmdb_id=s.tmdb_id "
        "WHERE s.missing_episodes != '[]' AND s.missing_episodes != '' "
        "AND s.data_quality = 'normal' "
        "AND s.tmdb_id NOT IN (SELECT tmdb_id FROM ignored WHERE season=-1)")
    if not rows:
        return _fail("当前没有需要订阅的缺集")

    ok_count, fail_count, fail_msgs = 0, 0, []
    for row in rows:
        tmdb_id, season = row["tmdb_id"], row["season_number"]
        # 跳过已订阅/已忽略的
        if database.query_one(
                "SELECT 1 FROM subscribe_map WHERE tmdb_id=? AND season=?", (tmdb_id, season)):
            continue
        if database.query_one(
                "SELECT 1 FROM ignored WHERE tmdb_id=? AND season=?", (tmdb_id, season)):
            continue
        ok, msg = runner.subscribe_season(tmdb_id, season)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
            fail_msgs.append(msg)

    logger.log("SUCCESS", "subscribe", f"一键订阅完成：成功 {ok_count}，失败 {fail_count}")
    return _ok({"ok": ok_count, "fail": fail_count},
               message=f"完成！成功订阅 {ok_count} 个季" + (f"，{fail_count} 个失败" if fail_count else ""))


# ------------------------------------------------------------
# 订阅预览（模拟订阅，不真正提交） + 批量订阅（购物车）
# ------------------------------------------------------------

@app.get("/api/subscribe/preview")
def api_subscribe_preview():
    """
    订阅预览（模拟订阅）：列出"当前会被订阅的所有缺集"，
    只查询不提交，让小白在看之前心里有数（前端确认后才真正订阅）
    """
    rows = database.query(
        "SELECT s.tmdb_id, s.season_number, s.missing_episodes, s.data_quality, "
        "sh.name, sh.year "
        "FROM seasons s LEFT JOIN shows sh ON sh.tmdb_id=s.tmdb_id "
        "WHERE s.missing_episodes != '[]' AND s.missing_episodes != '' "
        "AND s.tmdb_id NOT IN (SELECT tmdb_id FROM ignored WHERE season=-1)")
    items = []
    degraded_ids = []
    for r in rows:
        tmdb_id, season = r["tmdb_id"], r["season_number"]
        # 跳过已订阅/已忽略的
        if database.query_one(
                "SELECT 1 FROM subscribe_map WHERE tmdb_id=? AND season=?", (tmdb_id, season)):
            continue
        if database.query_one(
                "SELECT 1 FROM ignored WHERE tmdb_id=? AND season=?", (tmdb_id, season)):
            continue
        missing = json.loads(r["missing_episodes"] or "[]")
        if not missing:
            continue
        # 数据不准（degraded）的季不会出现在"待订阅"清单里，只统计数量
        if r["data_quality"] == "degraded":
            degraded_ids.append({"tmdb_id": tmdb_id, "season": season,
                                 "name": r["name"] or f"TMDB:{tmdb_id}"})
            continue
        items.append({
            "tmdb_id": tmdb_id,
            "season": season,
            "name": r["name"] or f"TMDB:{tmdb_id}",
            "year": r["year"] or "",
            "missing_count": len(missing),
        })
    return _ok({
        "total": len(items),
        "items": items,
        "degraded_count": len(degraded_ids),
        "degraded": degraded_ids,
    })


@app.post("/api/subscribe/batch")
async def api_subscribe_batch(request: Request):
    """
    批量订阅（购物车）：一次提交多部剧的多季
    body: {"items": [{"tmdb_id": 1, "season": 2}, ...]}
    degraded 的季会被跳过并提示（防误订阅）
    """
    body = await request.json() or {}
    items = body.get("items") or []
    if not items:
        return _fail("没有选择要订阅的季")

    ok_count, fail_count, fail_msgs = 0, 0, []
    for it in items:
        try:
            tmdb_id = int(it.get("tmdb_id"))
            season = int(it.get("season"))
        except (TypeError, ValueError):
            fail_count += 1
            fail_msgs.append("参数错误")
            continue
        ok, msg = runner.subscribe_season(tmdb_id, season)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
            fail_msgs.append(msg)

    logger.log("SUCCESS", "subscribe", f"批量订阅完成：成功 {ok_count}，失败 {fail_count}")
    return _ok({"ok": ok_count, "fail": fail_count},
               message=f"完成！成功订阅 {ok_count} 个季" + (f"，{fail_count} 个失败" if fail_count else ""))


# ------------------------------------------------------------
# 订阅管理（查看 MoviePilot 的订阅）
# ------------------------------------------------------------

@app.get("/api/subscriptions")
def api_subscriptions():
    """
    订阅管理列表：优先从 MoviePilot 实时拉取
    如果 MP 连不上，退回显示本地记录
    """
    ok, data = mp_client.list_subscribes()
    if ok and isinstance(data, list):
        subs = []
        for s in data:
            subs.append({
                "mp_id": s.get("id"),
                "name": s.get("name", ""),
                "season": s.get("season"),
                "state": s.get("state", ""),
                "type": s.get("type", ""),
                "total_episode": s.get("total_episode"),
                "lack_episode": s.get("lack_episode"),
                "username": s.get("username", ""),
            })
        return _ok({"source": "mp", "total": len(subs), "subscriptions": subs})
    # MP 连不上 → 显示本地记录（并提示）
    rows = database.query(
        "SELECT * FROM subscribe_map ORDER BY created_at DESC")
    return _ok({
        "source": "local",
        "total": len(rows),
        "subscriptions": [dict(r) for r in rows],
        "warning": f"无法连接 MoviePilot：{data}",
    })


@app.post("/api/subscriptions/refresh")
def api_subscriptions_refresh():
    """手动重新同步订阅状态（网页"刷新"按钮）"""
    count = mp_client.sync_subscribe_map()
    return _ok({"count": count}, message=f"已同步 {count} 条订阅状态")


@app.delete("/api/subscriptions/{mp_id}")
def api_subscription_delete(mp_id: int):
    """删除 MoviePilot 里的一个订阅"""
    ok, msg = mp_client.delete_subscribe(mp_id)
    if ok:
        # 同时删除本地记录
        database.execute("DELETE FROM subscribe_map WHERE mp_id=?", (mp_id,))
        logger.log("INFO", "subscribe", f"已删除订阅 {mp_id}")
        return _ok(message="已删除订阅")
    return _fail(msg)


@app.post("/api/cache/refresh")
def api_cache_refresh():
    """
    手动刷新 TMDB 缓存（设置页按钮）：
    清空后下次扫描会重新获取最新数据（剧集更新/修复后使用）
    """
    count = runner.tmdb_source.clear_cache()
    logger.log("INFO", "scan", f"已清空 TMDB 缓存（{count} 条）")
    return _ok(message="已清空 TMDB 缓存，下次扫描会重新获取最新数据")


@app.post("/api/settings/check-path")
async def api_settings_check_path(request: Request):
    """
    检查 strm 目录是否存在（首次安装向导用）
    注意：这里是容器内的路径（compose 里挂载的 /media 等）
    """
    body = await request.json() or {}
    path = str(body.get("path", "")).strip()
    if not path:
        return _fail("路径不能为空")
    if not os.path.isdir(path):
        return _fail(f"找不到目录 {path}，请检查 docker-compose 里的挂载路径（容器内路径，如 /media）")
    try:
        items = os.listdir(path)
        if not items:
            return _ok(message=f"目录存在（{path}），但里面是空的")
        return _ok(message=f"目录存在（{path}），里面共有 {len(items)} 个文件/文件夹")
    except PermissionError:
        return _fail(f"目录 {path} 存在但没有读取权限，请检查 Docker 挂载权限")
    except Exception as e:
        return _fail(f"检查目录出错：{e}")


# ------------------------------------------------------------
# 设置
# ------------------------------------------------------------

@app.get("/api/settings")
def api_settings():
    """读取全部设置（网页"设置"页展示，含说明文字）"""
    items = []
    for key, (default, desc) in CONFIG_DEFS.items():
        value = config.get(key)
        # Token / API Key 这类敏感字段打码显示，防止网页泄露真实值
        masked = False
        if key in auth.MASKED_KEYS and value:
            value = auth.mask(value)
            masked = True
        items.append({"key": key, "value": value, "display": value, "desc": desc,
                      "default": default, "masked": masked})
    return _ok(items)


@app.post("/api/settings")
async def api_settings_save(request: Request):
    """保存设置（网页"保存设置"按钮）"""
    body = await request.json() or {}
    # 敏感字段如果传回来的是打码值（用户没改），跳过不保存，避免把 "******xxxx" 存进去
    for key in auth.MASKED_KEYS:
        if key in body and auth.is_masked(str(body[key])):
            body.pop(key)
    config.set_many(body)
    config.reload()
    # 重新创建 MP 客户端和 TMDB 数据源（让新配置立即生效）
    global mp_client
    mp_client = MoviePilotClient(config.get("mp_url"), config.get("mp_token"))
    runner.mp = mp_client
    runner.reset_tmdb_source()
    logger.log("INFO", "system", "设置已保存")
    return _ok(message="设置已保存")


@app.post("/api/settings/test")
async def api_settings_test(request: Request):
    """
    测试连接（网页"测试连接"按钮）：
      1. 测 MoviePilot 连不连得上
      2. 测 TMDB 数据源用哪种方式
    """
    body = await request.json() or {}
    # 用表单里还没保存的值临时测试
    url = body.get("mp_url", config.get("mp_url"))
    token = body.get("mp_token", config.get("mp_token"))
    tmdb_key = body.get("tmdb_key", config.get("tmdb_key"))
    emby_url = body.get("emby_url", config.get("emby_url"))
    emby_key = body.get("emby_api_key", config.get("emby_api_key"))

    results = []

    # 1. 测试 MoviePilot
    if url and token:
        temp_mp = MoviePilotClient(url, token)
        r = temp_mp.test_connection()
        results.append({"name": "MoviePilot", "ok": r["ok"],
                        "detail": f"{r['message']}" + (f"（版本：{r['version']}）" if r["ok"] else "")})
    else:
        results.append({"name": "MoviePilot", "ok": False, "detail": "地址或 Token 未填写"})

    # 2. 测试 TMDB 数据源
    if url and token:
        temp_src = runner.tmdb_source.__class__(temp_mp, tmdb_key, config.get("tmdb_lang"))
        mode = temp_src.ensure_mode()
        if mode == "proxy":
            results.append({"name": "TMDB 数据", "ok": True,
                            "detail": "使用 MoviePilot 代理（无需 TMDB Key）"})
        elif mode == "direct":
            results.append({"name": "TMDB 数据", "ok": True,
                            "detail": "使用直连 TMDB（自己的 API Key）"})
        else:
            results.append({"name": "TMDB 数据", "ok": False,
                            "detail": "MP 不支持代理且未填 TMDB Key，请二选一"})
    elif tmdb_key:
        results.append({"name": "TMDB 数据", "ok": True, "detail": "使用直连 TMDB（自己的 API Key）"})
    else:
        results.append({"name": "TMDB 数据", "ok": False, "detail": "MP 地址未填，且未填 TMDB Key"})

    # 3. 测试 Emby（可选）
    if emby_url and emby_key:
        try:
            from .scanner import emby as emby_scanner
            r = emby_scanner._get_json(emby_url, emby_key, "/emby/System/Info")
            results.append({"name": "Emby", "ok": True, "detail": f"连接成功（{r.get('SystemName','')}）"})
        except Exception as e:
            results.append({"name": "Emby", "ok": False, "detail": f"连接失败：{e}"})
    else:
        results.append({"name": "Emby", "ok": None, "detail": "未配置（可跳过，不影响使用）"})

    return _ok(results)


# ------------------------------------------------------------
# 日志
# ------------------------------------------------------------

@app.get("/api/logs")
def api_logs(limit: int = 200):
    """日志列表"""
    return _ok(logger.get_logs(limit))


@app.delete("/api/logs")
def api_logs_clear():
    """清空日志"""
    logger.clear_logs()
    return _ok(message="日志已清空")
