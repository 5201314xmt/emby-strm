"""
============================================================
日志模块 - 记录所有操作日志
============================================================
说明：
  - 日志写入 SQLite（网页"日志"页展示）并同时打印到终端（Docker 也能看到）
  - 只保留最近 MAX_LOG_ROWS 条，防止数据库无限变大
  - 用法：logger.log("INFO", "scan", "扫描开始")
============================================================
"""

import datetime

from . import database

# 最多保留多少条日志（超过后自动删除最旧的）
MAX_LOG_ROWS = 2000

# 每写多少条日志才清理一次最旧的（避免每条日志都全表扫描一次，
# 扫描 10 万部剧时日志写入是热点，这个优化很关键）
_TRIM_EVERY = 50
_trim_counter = 0


def log(level: str = "INFO", category: str = "system", message: str = ""):
    """
    写一条日志
    参数：
      level:   级别，INFO(普通)/WARN(警告)/ERROR(错误)/SUCCESS(成功)
      category: 分类，scan(扫描)/subscribe(订阅)/system(系统)
      message:  日志内容（中文）
    """
    global _trim_counter

    # 打印到终端（Docker 日志里能看到，方便排查问题）
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] [{category}] {message}")

    # 写入数据库
    database.execute(
        "INSERT INTO logs (ts, level, category, message) VALUES (?, ?, ?, ?)",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, category, message),
    )
    # 定期清理最旧的日志（每 50 条清理一次，防止数据库无限变大）
    _trim_counter += 1
    if _trim_counter % _TRIM_EVERY == 0:
        database.execute(
            "DELETE FROM logs WHERE id NOT IN "
            "(SELECT id FROM logs ORDER BY id DESC LIMIT ?)",
            (MAX_LOG_ROWS,),
        )


def get_logs(limit: int = 200) -> list:
    """读取最近的日志（新的在前），用于网页展示"""
    rows = database.query("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def clear_logs():
    """清空所有日志"""
    database.execute("DELETE FROM logs")
