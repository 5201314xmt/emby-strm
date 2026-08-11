"""
缺集管家 v2.0 —— FastAPI 主入口

启动命令：
  uvicorn app.main:app --host 0.0.0.0 --port 8899

此文件只做两件事：
  1. 组装应用（注册路由、中间件）
  2. 启动初始化（建表、定时任务）
"""
import os
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .core.security import validate_session
from .core.database import engine, Base
from .utils.helpers import make_response
from .models import Base as ModelBase

# ========== 前端静态文件目录 ==========
# Docker 多阶段构建时，npm build 输出到 /app/frontend/dist
# 本地开发时，从 backend/../frontend/dist 读取
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if not STATIC_DIR.exists():
    STATIC_DIR = Path("/app/frontend/dist")


async def _recover_scan_jobs():
    """恢复上次异常中断的扫描任务：将 running/paused 状态的 Job 标记为 failed"""
    from datetime import datetime as _dt
    from .core.database import AsyncSessionLocal as _AL
    from .models.scan_job import ScanJob
    from sqlalchemy import select
    async with _AL() as db:
        result = await db.execute(
            select(ScanJob).where(ScanJob.status.in_(["running", "paused"]))
        )
        orphaned = result.scalars().all()
        for job in orphaned:
            job.status = "failed"
            job.phase = "异常中断（容器重启）"
            job.error_message = "扫描过程中容器重启，任务未完成"
            job.completed_at = _dt.now()
            print(f"[恢复] ScanJob #{job.id} 已标记为 failed（原: running/paused）")
        if orphaned:
            await db.commit()


# ========== 应用生命周期 ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用启动和关闭时的操作

    启动：
      - 自动创建数据库表（首次运行）
      - 启动定时扫描调度器
      - 恢复未完成的扫描任务（标记为失败）

    关闭：
      - 等待后台任务完成
    """
    # ---- 启动阶段 ----
    # 自动建表（用同步 SQLAlchemy 确保建表完成）
    from sqlalchemy import create_engine as _sync_create_engine
    from .config import settings as _cfg
    _sync_url = f"sqlite:///{_cfg.database_path}"
    _sync_eng = _sync_create_engine(_sync_url, echo=False)
    ModelBase.metadata.create_all(_sync_eng)
    _sync_eng.dispose()
    print("[启动] 数据库表已就绪")

    # 初始化全局客户端（MoviePilot + TMDB）
    from .core.app_state import init_clients
    init_clients()
    print("[启动] 客户端已初始化")

    # 恢复上次意外中断的扫描任务（标记为失败）
    await _recover_scan_jobs()
    print("[启动] 扫描任务恢复检查完成")

    # 启动定时扫描调度器
    from .tasks.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()

    yield  # 应用运行期间

    # ---- 关闭阶段 ----
    await stop_scheduler()
    print("[关闭] 缺集管家已停止")


# ========== 创建应用 ==========
app = FastAPI(
    title="缺集管家",
    description="自动扫描 STRM/Emby 媒体库，查询 TMDB 集数，计算缺集并提交 MoviePilot 订阅",
    version="2.0.0",
    lifespan=lifespan,
)

# ========== 注册路由 ==========
app.include_router(api_router)

# ========== 速率限制中间件 ==========
# 对登录/设置密码接口限制频率（防暴力破解）
_RATE_LIMIT_WINDOW = 60         # 60 秒窗口
_RATE_LIMIT_MAX = 10            # 窗口内最多 10 次
_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """登录接口速率限制"""
    path = request.url.path
    if path not in ("/api/auth/login", "/api/auth/setup"):
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    # 清理过期记录
    _rate_limit_buckets[ip] = [t for t in _rate_limit_buckets[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_buckets[ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"success": False, "message": "请求过于频繁，请稍后重试", "data": None},
        )
    _rate_limit_buckets[ip].append(now)
    return await call_next(request)

# ========== 认证中间件 ==========
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    登录保护中间件

    除登录/首次安装/健康检查外，所有 /api/* 接口都要求已登录。
    未登录返回 401，前端自动跳转登录页。
    后台任务（如扫描）不受影响——中间件只挡 HTTP 入口。
    """
    path = request.url.path

    # 这些路径不需要登录
    public_paths = {"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"}
    if path in public_paths:
        return await call_next(request)

    # 静态文件不需要登录
    if path.startswith("/assets") or path.endswith((".html", ".js", ".css", ".ico", ".svg")):
        return await call_next(request)

    # 所有 /api/* 接口都要登录
    if path.startswith("/api/"):
        token = request.cookies.get("queji_session")
        if not token or not await validate_session(token):
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "请先登录", "data": None},
            )

    return await call_next(request)


# ========== 健康检查 ==========
@app.get("/api/health")
async def health_check():
    """Docker 健康检查端点（不需要登录）"""
    return make_response(True, data={"status": "ok"})


# ========== TMDB 缓存管理 ==========
@app.post("/api/cache/clear")
async def clear_tmdb_cache():
    """清空 TMDB 缓存（下次扫描时重新获取最新数据）"""
    from .core.database import AsyncSessionLocal
    from .models.tmdb_cache import TMDBCache
    from sqlalchemy import delete

    async with AsyncSessionLocal() as db:
        await db.execute(delete(TMDBCache))
        await db.commit()

    return make_response(True, message="已清空 TMDB 缓存")


# ========== 前端页面 ==========
# 如果静态文件目录存在，挂载为 /assets/
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    _INDEX_PATH = os.path.join(STATIC_DIR, "index.html")

    @app.get("/", include_in_schema=False)
    async def index_page():
        """主页"""
        if os.path.exists(_INDEX_PATH):
            return FileResponse(_INDEX_PATH)
        return JSONResponse({"message": "前端未构建，请运行 npm run build"})

    # SPA fallback: React 路由 /login /dashboard 等直接访问时返回 index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """React SPA 前端路由——非 API 请求回退到 index.html"""
        # 排除已注册的 API 路径和静态资源
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if os.path.exists(_INDEX_PATH):
            return FileResponse(_INDEX_PATH)
        return JSONResponse({"message": "前端未构建"}, status_code=404)
else:
    @app.get("/", include_in_schema=False)
    async def index_page():
        return JSONResponse({"message": "缺集管家 API 已运行，前端请访问开发服务器"})
