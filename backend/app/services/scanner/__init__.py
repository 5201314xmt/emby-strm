"""扫描器模块 —— 从文件系统和 Emby 发现已存在的集"""
from .base import ScanResult
from . import filesystem, emby
