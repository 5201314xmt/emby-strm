"""
Ignored 模型 —— 用户忽略记录

对应数据库 `ignored` 表。
用户可以在网页上忽略"某一季"或"整部剧"，
被忽略的项不会出现在缺集列表中。
"""
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint, func
from ..core.database import Base


class Ignored(Base):
    __tablename__ = "ignored"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 业务字段 ==========
    tmdb_id = Column(
        Integer,
        ForeignKey("shows.tmdb_id", ondelete="CASCADE"),
        nullable=False,
        comment="TMDB 编号",
    )
    season = Column(Integer, nullable=False, comment="季号（-1=整部剧）")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="忽略时间")

    # ========== 约束 ==========
    __table_args__ = (
        UniqueConstraint("tmdb_id", "season", name="uq_ignored_tmdb_season"),
    )

    def __repr__(self):
        scope = "整部剧" if self.season == -1 else f"S{self.season}"
        return f"<Ignored tmdb_id={self.tmdb_id} {scope}>"
