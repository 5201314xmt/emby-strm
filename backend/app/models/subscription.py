"""
Subscription 模型 —— 本地订阅记录

对应数据库 `subscriptions` 表（原 subscribe_map）。
记录每个向 MoviePilot 提交的订阅请求的状态。

与 MoviePilot 的关系：
  mp_id 是 MoviePilot 那边的订阅 ID
  本地记录优先从 MP 同步状态，MP 连不上时退回本地记录
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 外键 ==========
    tmdb_id = Column(
        Integer,
        ForeignKey("shows.tmdb_id", ondelete="CASCADE"),
        nullable=False,
        comment="TMDB 编号",
    )

    # ========== 业务字段 ==========
    season = Column(Integer, nullable=False, comment="季号")
    mp_id = Column(Integer, comment="MoviePilot 那边的订阅 ID")
    name = Column(String(300), comment="剧名（冗余存储，方便列表展示）")
    state = Column(String(10), default="R", comment="R=等待搜索  S=搜索中  P=已完成")
    auto = Column(Boolean, default=False, comment="是否自动订阅的")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    # ========== ORM 关联 ==========
    show = relationship("Show", back_populates="subscriptions")

    # ========== 约束 ==========
    __table_args__ = (
        UniqueConstraint("tmdb_id", "season", name="uq_subscription_tmdb_season"),
    )

    def __repr__(self):
        return f"<Subscription tmdb_id={self.tmdb_id} S{self.season} state='{self.state}'>"
