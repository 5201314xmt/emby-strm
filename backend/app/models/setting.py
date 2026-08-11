"""
Setting 模型 —— 系统配置键值对

对应数据库 `settings` 表。
网页"设置"页的所有配置项都存这里。
"""
from sqlalchemy import Column, String, Text, DateTime, func
from ..core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    # 配置项的键名，如 "mp_url"、"auto_scan"
    key = Column(String(100), primary_key=True, comment="配置键名")

    # 配置的值（所有值都转成字符串存储）
    value = Column(Text, nullable=False, default="", comment="配置值（字符串）")

    # 最后更新时间
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="最后更新时间")

    def __repr__(self):
        return f"<Setting key='{self.key}' value='{self.value[:30]}'>"
