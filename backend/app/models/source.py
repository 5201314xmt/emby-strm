"""
Source 模型 —— 扫描源配置

对应数据库 `sources` 表。
替代旧版的 scan_paths JSON 字符串，每个扫描源（目录/Emby）独立记录。

设计意图：
  - 一个源 = 一个 STRM 目录 / 一个 Emby 服务器
  - 每个源有独立的名字、路径、连接状态
  - 扫描时可以指定扫描哪些源（增量/重扫）
  - 缺集可以追溯到来自哪个源
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, func
from ..core.database import Base


class Source(Base):
    __tablename__ = "sources"

    # ========== 主键 ==========
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ========== 基本信息 ==========
    name = Column(String(100), nullable=False, comment="用户自定义名字，如'139_video1'")
    path = Column(String(500), nullable=False, comment="容器内路径，如'/media/139_video1'")
    type = Column(String(20), nullable=False, default="filesystem",
                  comment="类型：filesystem=strm文件扫描  emby=Emby API扫描")
    enabled = Column(Boolean, nullable=False, default=True,
                     comment="是否启用扫描（关闭后不会被扫到）")

    # ========== Emby 专用字段（type=emby 时才有值） ==========
    emby_url = Column(String(300), comment="Emby 服务器地址")
    emby_api_key = Column(String(200), comment="Emby API 密钥")

    # ========== 上次扫描结果（每次扫描后更新，方便网页展示） ==========
    last_scan_at = Column(DateTime, comment="上次扫描完成时间")
    last_scan_status = Column(String(20), comment="success=成功  partial=部分失败  failed=失败")
    last_error = Column(Text, comment="上次失败的错误信息")
    show_count = Column(Integer, comment="上次扫描发现的剧集数量")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    def __repr__(self):
        return f"<Source id={self.id} name='{self.name}' type='{self.type}'>"
