"""
API 路由注册模块 —— 将所有路由子模块挂载到统一前缀
"""
from fastapi import APIRouter
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .shows import router as shows_router
from .scan import router as scan_router
from .subscriptions import router as subscriptions_router
from .sources import router as sources_router
from .settings import router as settings_router
from .logs import router as logs_router
from .ws import router as ws_router

# 创建统一的 API 路由器
api_router = APIRouter()

# 挂载所有子路由
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(shows_router)
api_router.include_router(scan_router)
api_router.include_router(subscriptions_router)
api_router.include_router(sources_router)
api_router.include_router(settings_router)
api_router.include_router(logs_router)
api_router.include_router(ws_router)

