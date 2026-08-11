"""
扫描结果数据模型

定义扫描器返回的标准数据结构。
所有扫描器（filesystem / emby）都返回同样的 ScanResult。
"""
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    """
    一次扫描的原始结果（"目前有哪些集"）

    shows 结构：
      { tmdb_id: {
            "name": "剧名（目录名）",
            "source_ids": {1, 3},
            "seasons": { 季号: [已有集号...] }
        }
      }

    unrecognized 结构：
      [{"path": "/media/xxx.strm", "source_id": 1, "reason": "没找到TMDB编号"}]
    """
    shows: dict = field(default_factory=dict)
    unrecognized: list = field(default_factory=list)
