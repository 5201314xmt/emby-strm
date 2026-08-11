"""
Session 模型 —— 登录会话

对应数据库 `sessions` 表。
用户登录后，服务器生成一个随机 Token 存到这里，
同时写到用户的 Cookie 里。每次请求都验证 Cookie 中的 Token。
"""
from sqlalchemy import Column, String, DateTime, func
from ..core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    # ========== 主键 ==========
    token = Column(String(260), primary_key=True, comment="随机 Session Token（256 位十六进制）")

    # ========== 时间戳 ==========
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间（30 天后）")

    def __repr__(self):
        return f"<Session token='{self.token[:20]}...'>"
