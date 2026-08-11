"""
TMDBCache 模型 —— TMDB 磁盘缓存

对应数据库 `tmdb_cache` 表。
TMDB 查询结果缓存到磁盘，跨容器重启仍然有效。
缓存有效期 24 小时，过期后重新请求（失败则退回旧数据）。

主键是 (tmdb_id, season)，season=-1 表示"剧信息"缓存。
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from ..core.database import Base


class TMDBCache(Base):
    __tablename__ = "tmdb_cache"

    # ========== 联合主键 ==========
    tmdb_id = Column(Integer, primary_key=True, comment="TMDB 编号")
    season = Column(Integer, primary_key=True, comment="季号（-1=剧信息）")

    # ========== 数据 ==========
    response_json = Column(Text, nullable=False, comment="JSON 格式的缓存数据")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="缓存创建时间")

    def __repr__(self):
        return f"<TMDBCache tmdb_id={self.tmdb_id} season={self.season}>"
