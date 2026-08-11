"""
Log 模型 —— 操作日志

对应数据库 `logs` 表。
所有系统运行日志都写入此表，网页"日志"页展示。
最多保留 5000 条（超过自动清理旧记录）。
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from ..core.database import Base


class Log(Base):
    __tablename__ = "logs"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 日志元数据 ==========
    timestamp = Column(DateTime, server_default=func.now(), comment="日志产生时间")
    level = Column(
        String(10),
        nullable=False,
        comment="日志级别：INFO / SUCCESS / WARN / ERROR",
    )
    category = Column(
        String(20),
        nullable=False,
        comment="日志分类：system / scan / subscribe / tmdb",
    )
    source = Column(String(100), comment="来源（扫描源名/组件名），可空")

    # ========== 关联信息（非必填，方便追溯） ==========
    tmdb_id = Column(Integer, comment="关联的 TMDB 编号，可空")

    # ========== 日志内容 ==========
    message = Column(Text, nullable=False, comment="日志正文")

    def __repr__(self):
        return f"<Log [{self.level}] {self.category}: {self.message[:50]}>"
