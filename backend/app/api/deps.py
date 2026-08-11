"""
API 依赖注入模块

所有路由共享的依赖函数（数据库会话、认证校验等）。
用 FastAPI 的 Depends 机制自动注入，路由函数无需手动管理。
"""
from fastapi import Request, HTTPException, Depends

from ..core.database import get_db
from ..core.security import validate_session


# 导出数据库会话注入（直接复用 database.py 的 get_db）
# 别名保持语义一致
get_db_session = get_db


async def get_current_user(request: Request) -> str:
    """
    认证依赖 —— 验证当前用户是否已登录

    用法：
      @router.get("/api/xxx")
      async def xxx(_: None = Depends(get_current_user)):
          ...

    如果未登录，抛出 401 错误，前端自动跳转登录页。

    Returns:
        当前用户的 Session Token（一般用不到返回值，但保留）
    """
    token = request.cookies.get("queji_session")
    if not token or not await validate_session(token):
        raise HTTPException(status_code=401, detail="请先登录")
    return token
