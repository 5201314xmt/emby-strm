"""
配置管理模块 —— 统一管理所有用户设置

设置来源优先级（从高到低）：
  1. 环境变量（QUEJI_ 前缀，如 QUEJI_MP_URL）
  2. .env 文件（docker-compose 传入）
  3. 数据库 settings 表（网页上修改）
  4. 代码默认值

用法：
  from app.config import settings
  print(settings.mp_url)  # 读取配置
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


# 项目根目录（backend/ 所在位置）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 数据存储目录（数据库文件、备份等）
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """
    全局配置类

    每个字段会自动从环境变量读取（不区分大小写），
    也支持 QUEJI_ 前缀覆盖（如 QUEJI_MP_URL）。
    """

    # ========== MoviePilot 连接 ==========
    mp_url: str = ""
    mp_token: str = ""

    # ========== TMDB 数据源 ==========
    tmdb_key: str = ""          # 自己的 TMDB API Key（MoviePilot v3 无需填写）
    tmdb_lang: str = "zh-CN"    # TMDB 获取数据的语言

    # ========== 自动化 ==========
    auto_scan: bool = False         # 是否开启定时自动扫描
    scan_interval: int = 12         # 自动扫描间隔（小时）
    auto_subscribe: bool = False    # 扫描后自动订阅缺集
    include_specials: bool = False  # 是否检测特别篇 S00

    # ========== 应用配置 ==========
    app_port: int = 8899            # 网页服务端口
    data_dir: str = str(DATA_DIR)   # 数据目录路径

    # ========== 安全 ==========
    admin_password_hash: str = ""   # 管理员密码（PBKDF2 加盐哈希，不存明文）

    # ========== 数据库路径 ==========
    @property
    def database_path(self) -> str:
        """SQLite 数据库文件的完整路径"""
        return os.path.join(self.data_dir, "queji.db")

    @property
    def database_url(self) -> str:
        """SQLAlchemy 数据库连接 URL（aiosqlite 异步驱动）"""
        return f"sqlite+aiosqlite:///{self.database_path}"

    class Config:
        env_file = ".env"           # 从 .env 文件读取
        env_prefix = "QUEJI_"       # 环境变量前缀
        extra = "ignore"            # 忽略未知字段（兼容老版本配置）


# 全局单例 —— 整个应用共享同一个配置实例
settings = Settings()
