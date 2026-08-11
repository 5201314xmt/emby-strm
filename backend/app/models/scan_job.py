"""
ScanJob 模型 —— 扫描任务记录

对应数据库 `scan_jobs` 表。
每次扫描（手动/自动）都创建一条记录，持久化到数据库。
即使 Docker 重启，也能知道上次扫描的状态。

状态机：
  pending → running → completed
                    → failed
                    → cancelled
           running  → paused → running
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, func
from ..core.database import Base


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 任务参数 ==========
    source_ids = Column(JSON, default=list, comment="扫描了哪些源的 ID（空=全部源）")

    # ========== 运行状态 ==========
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending=running=completed=failed=cancelled=paused",
    )
    phase = Column(
        String(50),
        comment="当前阶段：扫描文件/查询TMDB/计算缺集/同步订阅",
    )
    progress = Column(Float, default=0.0, comment="完成百分比 0.0~100.0")

    # ========== 进度详情 ==========
    total_shows = Column(Integer, default=0, comment="需要处理的剧集总数")
    done_shows = Column(Integer, default=0, comment="已处理的剧集数")
    current_item = Column(String(500), comment="当前正在处理的剧名")
    eta_seconds = Column(Integer, default=0, comment="预计剩余秒数")

    # ========== 结果 ==========
    error_message = Column(Text, comment="失败时的错误信息")
    auto_subscribed = Column(Integer, default=0, comment="本次自动订阅了多少季")

    # ========== 时间戳 ==========
    started_at = Column(DateTime, comment="开始时间")
    paused_at = Column(DateTime, comment="暂停时间")
    completed_at = Column(DateTime, comment="完成时间（成功/失败/取消都会记录）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self):
        return f"<ScanJob id={self.id} status='{self.status}'>"
