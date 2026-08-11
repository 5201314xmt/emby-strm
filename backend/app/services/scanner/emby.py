"""
Emby API 扫描器 —— 通过 Emby API 遍历媒体库

复用原项目的 Emby API 对接逻辑。
在 settings 中配置了 Emby URL 和 API Key 后，
可以同时扫描 STRM 文件和 Emby 媒体库，结果合并。
"""
from .base import ScanResult


async def scan_emby(emby_url: str, emby_api_key: str, source_id: int = 0) -> ScanResult:
    """
    通过 Emby API 扫描媒体库

    Args:
        emby_url:     Emby 服务器地址（如 http://192.168.1.100:8096）
        emby_api_key: Emby API Key
        source_id:    扫描源 ID

    Returns:
        ScanResult（shows 字典 + unrecognized 列表）
    """
    result = ScanResult()
    # TODO Step 2+: 对接 Emby API 遍历逻辑
    # 原代码在 app/scanner/emby.py，遍历所有 Series 和 Episodes
    return result
