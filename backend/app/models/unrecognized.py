"""
UnrecognizedFile 模型 —— 未识别文件记录

对应数据库 `unrecognized_files` 表。
扫描时解析不出来的文件/目录记录在这里，
网页"未识别"页展示，方便用户手动排查。
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, func
from ..core.database import Base


class UnrecognizedFile(Base):
    __tablename__ = "unrecognized_files"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 文件信息 ==========
    path = Column(String(1000), nullable=False, comment="文件的完整路径")
    source_id = Column(
        Integer,
        ForeignKey("sources.id", ondelete="SET NULL"),
        comment="来自哪个扫描源",
    )
    reason = Column(String(500), nullable=False, comment="未识别原因（中文说明）")

    # ========== 时间戳 ==========
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    # ========== 约束 ==========
    __table_args__ = (
        UniqueConstraint("path", "source_id", name="uq_unrecognized_path_source"),
    )

    def __repr__(self):
        return f"<UnrecognizedFile path='{self.path[:50]}' reason='{self.reason}'>"
