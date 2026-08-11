"""
Season 模型 —— 一部剧某一季的缺集详情

对应数据库 `seasons` 表。
每部剧的每一季都有一条记录，存储该季的缺集计算结果。
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, UniqueConstraint, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class Season(Base):
    __tablename__ = "seasons"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 外键 ==========
    tmdb_id = Column(
        Integer,
        ForeignKey("shows.tmdb_id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的 TMDB 编号",
    )

    # ========== 季号 ==========
    season_number = Column(Integer, nullable=False, comment="季号（0=特别篇）")

    # ========== 集数统计 ==========
    total_episodes = Column(Integer, default=0, comment="TMDB 全集数（含未播出）")
    aired_episodes = Column(Integer, default=0, comment="已播出的集数")

    # ========== 集详情（JSON 数组） ==========
    present_episodes = Column(JSON, default=list, comment="库里已有的集号列表，如 [1,2,3]")
    missing_episodes = Column(JSON, default=list, comment="缺失的集号列表，如 [4,5,6]")

    # ========== 状态 ==========
    status = Column(
        String(20),
        nullable=False,
        comment="complete=完整  partial=缺部分  full_missing=整季缺失",
    )
    data_quality = Column(
        String(20),
        default="normal",
        comment="normal=数据可靠  degraded=用了旧缓存/降级估算（禁止自动订阅）",
    )

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    # ========== ORM 关联 ==========
    show = relationship("Show", back_populates="seasons")

    # ========== 约束 ==========
    __table_args__ = (
        UniqueConstraint("tmdb_id", "season_number", name="uq_season_tmdb_season"),
    )

    def __repr__(self):
        return f"<Season tmdb_id={self.tmdb_id} S{self.season_number} status='{self.status}'>"
