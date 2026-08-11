"""
============================================================
配置模块 - 管理所有用户设置
============================================================
说明：
  - 配置保存在 SQLite 的 settings 表里（网页"设置"页修改）
  - 每个配置项都有默认值，没设置过就用默认值，小白不会漏配置
  - 也支持用环境变量覆盖（高级用法，一般用不上）
  - 修改配置后调用 save() 保存，页面即时生效
============================================================
"""

import json
import os

from . import database

# ============================================================
# 所有配置项的定义（key=配置名，value=[默认值, 中文说明]）
# 以后要加新配置，在这里加一行即可，非常方便扩展
# ============================================================
CONFIG_DEFS = {
    # ---------- MoviePilot 相关 ----------
    "mp_url":       ["", "MoviePilot 地址（如 http://192.168.1.100:3000）"],
    "mp_token":     ["", "MoviePilot API Token（MoviePilot 设置->安全->API令牌）"],

    # ---------- TMDB 数据源 ----------
    "tmdb_key":     ["", "TMDB API Key（备用数据源，MoviePilot v3 无需填写）"],
    "tmdb_lang":    ["zh-CN", "TMDB 语言（默认中文）"],

    # ---------- 媒体库来源 ----------
    "scan_paths":   ["[]", "strm 文件目录列表（JSON 数组，网页上填写）"],
    "emby_url":     ["", "Emby 地址（可选，如 http://192.168.1.100:8096）"],
    "emby_api_key": ["", "Emby API Key（可选，Emby 设置->高级->API密钥）"],

    # ---------- 扫描行为 ----------
    "auto_scan":        ["0", "是否自动定时扫描：1=开启 0=关闭"],
    "scan_interval":    ["12", "自动扫描间隔（小时）"],
    "auto_subscribe":   ["0", "扫描后自动订阅缺集：1=开启 0=关闭"],
    "include_specials": ["0", "是否检测特别篇 S00：1=检测 0=不检测"],

    # ---------- 其他 ----------
    "last_scan": ["", "上次扫描完成时间（系统自动记录）"],
}

# 环境变量前缀：QUEJI_xxx 可以覆盖配置（高级用法）
_ENV_PREFIX = "QUEJI_"


class Config:
    """
    配置管理器
    用法：
      cfg = Config()
      cfg.get("mp_url")          # 读取配置
      cfg.set("mp_url", "...")   # 修改并保存配置
    """

    def __init__(self):
        # 从数据库加载所有配置到内存（程序运行期间读内存，快）
        self._data = {}
        self.reload()

    # ----------------------------------------------------------
    def reload(self):
        """
        从数据库重新加载全部配置（修改配置后调用，页面即时生效）
        注意：程序刚启动、数据库还没建表时调用会失败，
        这里做了容错（第一次启动时配置表还不存在，空配置即可）
        """
        try:
            self._data = {r["key"]: r["value"] for r in database.query("SELECT * FROM settings")}
        except Exception:
            self._data = {}

    # ----------------------------------------------------------
    def get(self, key: str):
        """
        读取配置值（返回字符串）
        如果用户没设置过，返回默认值；默认值也没有返回空字符串
        """
        # 环境变量优先（高级用法）
        env_value = os.environ.get(f"{_ENV_PREFIX}{key.upper()}")
        if env_value is not None:
            return env_value
        if key in self._data:
            return self._data[key]
        if key in CONFIG_DEFS:
            return CONFIG_DEFS[key][0]
        return ""

    # ----------------------------------------------------------
    def get_int(self, key: str, default: int = 0) -> int:
        """读取整数配置（如间隔小时数）"""
        try:
            return int(self.get(key))
        except (TypeError, ValueError):
            return default

    # ----------------------------------------------------------
    def get_bool(self, key: str) -> bool:
        """读取开关配置（返回 True/False）"""
        return self.get(key) in ("1", "true", "True", "on")

    # ----------------------------------------------------------
    def get_paths(self) -> list:
        """读取 strm 目录列表（存的是 JSON 数组，这里转成 Python 列表）"""
        try:
            return json.loads(self.get("scan_paths") or "[]")
        except json.JSONDecodeError:
            return []

    # ----------------------------------------------------------
    def set(self, key: str, value):
        """修改配置并立即保存到数据库"""
        value = str(value)
        database.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._data[key] = value

    # ----------------------------------------------------------
    def set_many(self, items: dict):
        """一次保存多个配置（网页设置页点"保存"时用）"""
        for key, value in items.items():
            if key in CONFIG_DEFS:
                self.set(key, value)

    # ----------------------------------------------------------
    def is_complete(self) -> dict:
        """
        检查基本配置是否齐全（用于首次使用引导）
        返回：{"ok": True/False, "missing": ["缺什么"]}
        """
        missing = []
        if not self.get("mp_url"):
            missing.append("MoviePilot 地址")
        if not self.get("mp_token"):
            missing.append("MoviePilot API Token")
        if not self.get_paths() and not (self.get("emby_url") and self.get("emby_api_key")):
            missing.append("strm 目录或 Emby 信息")
        return {"ok": len(missing) == 0, "missing": missing}
