"""
Show 模型 —— 一部剧的基本信息

对应数据库 `shows` 表。
每部剧由 TMDB 编号唯一标识（全球唯一），可能来自多个扫描源。
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class Show(Base):
    __tablename__ = "shows"

    # ========== 主键 ==========
    tmdb_id = Column(Integer, primary_key=True, comment="TMDB 编号（全球唯一标识一部剧）")

    # ========== 基本信息 ==========
    name = Column(String(300), nullable=False, comment="剧名（优先 TMDB 官方名，其次目录名）")
    year = Column(String(10), comment="首播年份，如 '2011'")
    poster = Column(String(500), comment="海报路径，如 '/abc123.jpg'")
    overview = Column(Text, comment="剧情简介")

    # ========== 状态 ==========
    status = Column(String(20), nullable=False, default="ok",
                    comment="ok=正常扫描  error=扫描过程出错")

    # ========== 用户操作 ==========
    ignore_entire = Column(Boolean, nullable=False, default=False,
                           comment="用户是否标记'忽略整部剧'")

    # ========== 来源追溯 ==========
    # 存 [1, 3] 表示这部剧中部分集来自源 1 和源 3
    source_ids = Column(JSON, nullable=False, default=list,
                        comment="来自哪些扫描源的 ID 列表")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="首次入库时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    # ========== ORM 关联关系（方便用 selectinload 批量加载） ==========
    # 注意：这些字段不会在数据库里创建新列，仅用于 ORM 查询
    seasons = relationship(
        "Season",
        back_populates="show",
        lazy="selectin",                     # 查询时自动 JOIN 加载
        cascade="all, delete-orphan",        # 删除 Show 时自动删除相关 Season
    )
    subscriptions = relationship(
        "Subscription",
        back_populates="show",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Show tmdb_id={self.tmdb_id} name='{self.name}'>"
