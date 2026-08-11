"""
日志服务 —— 双写日志（终端 + 数据库）

所有系统日志同时输出到：
  1. 终端（print，Docker logs 可见）
  2. 数据库 logs 表（网页"日志"页展示）

数据库日志最多保留 5000 条，超过自动清理旧记录。
"""
from datetime import datetime

from ..core.database import AsyncSessionLocal
from ..models.log import Log
from sqlalchemy import delete, select, func

MAX_LOG_ROWS = 5000   # 数据库最多保留的日志条数


async def add_log(level: str, category: str, message: str, source: str = "", tmdb_id: int = None):
    """
    写入一条日志（终端 + 数据库）

    Args:
        level:    日志级别（INFO / SUCCESS / WARN / ERROR）
        category: 日志分类（system / scan / subscribe / tmdb）
        message:  日志正文（中文）
        source:   来源标识（扫描源名或组件名）
        tmdb_id:  关联的 TMDB 编号（可空）
    """
    # 1. 终端输出（Docker logs 可见）
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {category}: {message}")

    # 2. 写入数据库
    try:
        async with AsyncSessionLocal() as db:
            log_entry = Log(
                level=level,
                category=category,
                message=message,
                source=source or "",
                tmdb_id=tmdb_id,
            )
            db.add(log_entry)
            await db.commit()

            # 3. 检查是否超出最大行数，超出则清理旧记录
            count = await db.scalar(select(func.count(Log.id)))
            if count and count > MAX_LOG_ROWS:
                cutoff_id = await db.scalar(
                    select(Log.id).order_by(Log.id.desc()).offset(MAX_LOG_ROWS - 1).limit(1)
                )
                if cutoff_id:
                    await db.execute(delete(Log).where(Log.id < cutoff_id))
                    await db.commit()
    except Exception as e:
        print(f"[日志写入失败] {e}")
