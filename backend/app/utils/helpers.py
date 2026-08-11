"""
通用工具函数 —— 不依赖任何业务模块的纯函数

这些函数可以被项目的任何地方调用。
"""
import json
import hashlib
import secrets
from datetime import datetime, date


def make_response(success: bool, data=None, message: str = "") -> dict:
    """
    统一 JSON 响应格式

    所有 API 接口都返回这个结构，前端统一处理：
      { "success": true/false, "data": ..., "message": "..." }

    Args:
        success: 请求是否成功
        data:    业务数据（可以是 dict、list、None）
        message: 中文提示信息（成功时可为空，失败时必填）
    """
    return {
        "success": success,
        "data": data,
        "message": message or ("成功" if success else "失败"),
    }


def now_str() -> str:
    """获取当前时间的字符串表示（"2025-01-15 14:30:00" 格式）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> date:
    """获取今天的日期"""
    return date.today()


def mask_secret(value: str, show_last: int = 4) -> str:
    """
    对敏感字符串打码（Token、API Key 等）

    例："sk-abc123456789xyz" → "******wxyz"

    Args:
        value:      原始字符串
        show_last:  末尾保留几位明文
    """
    if not value or len(value) <= show_last:
        return "***"
    return "*" * (len(value) - show_last) + value[-show_last:]


def is_masked(value: str) -> bool:
    """判断一个值是否已经被打码（全星号开头）"""
    return bool(value) and all(c == "*" for c in value[:-4]) if len(value) > 4 else False


def safe_json_loads(text: str, default=None):
    """安全的 JSON 解析，失败时返回默认值而不抛异常"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default
