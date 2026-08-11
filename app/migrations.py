"""
============================================================
数据库迁移模块 - 版本化自动升级 + 备份/回滚方案
============================================================
设计（给未来的生产环境用）：
  - 用 SQLite 的 user_version 记录当前数据库结构版本
  - 程序启动时自动执行"未执行过的"迁移（旧版本数据库无缝自动升级）
  - 升级前自动把数据库备份到 data/backups/database_backup_xxx.db

回滚方案（万一升级后出问题）：
  1. 停止程序（docker compose down）
  2. 用 data/backups/ 里最新一份备份覆盖 queji.db
  3. 重新启动（docker compose up -d）

规则：
  - 不要修改已经发布过的迁移！要改数据库结构就"新增一个版本"
  - 每次结构变化：version + 1，并追加一条迁移
============================================================
"""

import datetime
import os
import sqlite3

# 当前数据库结构版本（每加一次结构修改 +1）
DB_VERSION = 3

# ============================================================
# 初始表结构（版本 1：与最初发布的建表语句完全一致）
# ============================================================
_SCHEMA = """
-- 设置表：保存用户配置（键值对），比如 MoviePilot 地址、API Token 等
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,   -- 配置项名称
    value TEXT                -- 配置项的值
);

-- 剧集表：扫描到的每一部剧
CREATE TABLE IF NOT EXISTS shows (
    tmdb_id    INTEGER PRIMARY KEY,  -- TMDB 编号（一部剧的唯一标识）
    name       TEXT,                 -- 剧名（优先用目录名，可后续优化为 TMDB 官方名）
    year       TEXT,                 -- 年份
    poster     TEXT,                 -- 海报地址（可空）
    status     TEXT DEFAULT 'ok',    -- 状态：ok=正常 error=TMDB查不到 unknown=未识别
    ignore     INTEGER DEFAULT 0,    -- 是否整部忽略：0=不忽略 1=忽略
    updated_at TEXT                  -- 最近更新时间
);

-- 季表：每一部剧的每一季的缺集情况
CREATE TABLE IF NOT EXISTS seasons (
    tmdb_id          INTEGER,        -- 剧的 TMDB 编号
    season_number    INTEGER,        -- 季号（第几季，0=特别篇）
    total_episodes   INTEGER,        -- TMDB 上这一季全集数（含未播出的）
    aired_episodes   INTEGER,        -- 已经播出的集数
    present_episodes TEXT,           -- 已有的集号，JSON 数组，如 [1,2,3]
    missing_episodes TEXT,           -- 缺的集号，JSON 数组，如 [4,6]
    status           TEXT,           -- 状态：complete=完整 partial=缺部分 full_missing=整季缺失
    UNIQUE(tmdb_id, season_number)   -- 同一部剧的同一季只能有一条记录
);

-- 忽略表：用户手动忽略的季（-1 表示忽略整部剧）
CREATE TABLE IF NOT EXISTS ignored (
    tmdb_id INTEGER,
    season  INTEGER DEFAULT -1,      -- -1=整部剧 其他数字=某一季
    PRIMARY KEY (tmdb_id, season)
);

-- 订阅记录表：记录本工具帮你在 MoviePilot 创建的订阅
CREATE TABLE IF NOT EXISTS subscribe_map (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id    INTEGER,              -- 剧的 TMDB 编号
    season     INTEGER,              -- 季号
    mp_id      INTEGER,              -- MoviePilot 里的订阅 ID
    name       TEXT,                 -- 剧名
    state      TEXT,                 -- 状态（从 MoviePilot 同步）：R=等待 S=搜索中 P=已完成
    created_at TEXT                  -- 创建时间
);

-- 日志表：扫描日志和操作日志（页面上的"日志"页展示）
CREATE TABLE IF NOT EXISTS logs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT,      -- 时间
    level    TEXT,      -- 级别：INFO=普通 WARN=警告 ERROR=错误 SUCCESS=成功
    category TEXT,      -- 分类：scan=扫描 subscribe=订阅 system=系统
    message  TEXT       -- 日志内容
);

-- 未识别表：扫描时遇到看不懂的文件/目录（方便用户在网页上看到并排查）
CREATE TABLE IF NOT EXISTS unrecognized (
    path       TEXT PRIMARY KEY,     -- 文件或目录路径
    reason     TEXT,                 -- 没识别出来的原因
    updated_at TEXT                  -- 更新时间
);

-- 登录会话表：记录登录状态（登录后浏览器存一个随机 Token，30 天有效）
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,     -- 会话令牌（随机生成，存在浏览器 Cookie 里）
    created_at TEXT,                 -- 创建时间
    expires_at TEXT                  -- 过期时间（超过后需要重新登录）
);
"""

# ============================================================
# 所有迁移（按版本号从小到大依次执行，永远只追加不修改）
# ============================================================
MIGRATIONS = [
    {
        "version": 1,
        "name": "初始表结构",
        "sql": _SCHEMA,
    },
    {
        "version": 2,
        "name": "WAL模式 + 查询索引 + 订阅唯一约束",
        "sql": """
-- 1. 缺集列表筛选（partial / full_missing / complete 子查询）用到的索引
CREATE INDEX IF NOT EXISTS idx_seasons_status ON seasons(status);

-- 2. 清理 subscribe_map 里的历史重复记录（保留最早一条）
--    （早期版本因为没唯一约束，同剧同季可能有多条记录）
DELETE FROM subscribe_map
WHERE id NOT IN (SELECT MIN(id) FROM subscribe_map GROUP BY tmdb_id, season);

-- 3. 订阅唯一约束：同一部剧的同一季只能有一条订阅记录
--    从根上防止重复提交 MoviePilot（业务红线）
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscribe_map_unique
    ON subscribe_map(tmdb_id, season);
""",
    },
    {
        "version": 3,
        "name": "TMDB 磁盘缓存表 + 数据质量标记",
        "sql": """
-- 1. TMDB 磁盘缓存：成功获取的剧/季数据落盘保存，
--    扫描时优先读缓存，不再反复请求 TMDB（二次扫描快 10 倍以上）
--    season = -1 表示"剧信息"缓存，>=0 表示该季集列表缓存
CREATE TABLE IF NOT EXISTS tmdb_cache (
    tmdb_id       INTEGER NOT NULL,
    season        INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at    TEXT,
    PRIMARY KEY (tmdb_id, season)
);

-- 2. 数据质量标记：normal=正常数据  degraded=使用了旧缓存/降级估算
--    （degraded 的季禁止自动订阅，防止 TMDB 异常导致误订阅）
ALTER TABLE seasons ADD COLUMN data_quality TEXT DEFAULT 'normal';
""",
    },
]


def get_version(conn) -> int:
    """读取数据库当前结构版本（没有记录 = 0 = 最老版本）"""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def backup_db() -> str:
    """
    备份数据库到 data/backups/database_backup_日期.db
    返回备份文件路径；备份失败不影响迁移继续（只警告）
    用 SQLite 官方 backup API，WAL 模式下也安全
    """
    from . import database
    backup_dir = os.path.join(database.DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    name = datetime.datetime.now().strftime("database_backup_%Y%m%d_%H%M%S.db")
    path = os.path.join(backup_dir, name)
    try:
        src = sqlite3.connect(database.DB_PATH)
        dst = sqlite3.connect(path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
        print(f"[数据库] 已自动备份到：{path}")
        return path
    except Exception as e:
        print(f"[数据库] 备份失败（不影响迁移继续）：{e}")
        return ""


def run_migrations():
    """
    执行所有未执行的迁移（自动升级到最新结构）
    - 全新数据库：直接建最新结构
    - 旧版本数据库：自动备份 → 逐版本升级
    - 已是最新：什么都不做
    迁移失败会抛出异常（宁可启动失败，也不能带损坏结构运行）
    """
    from . import database
    os.makedirs(database.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(database.DB_PATH, timeout=30)
    try:
        version = get_version(conn)
        if version >= DB_VERSION:
            # 已是最新：确保 WAL 模式开启即可
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
            return

        # 有旧数据要升级 → 先自动备份（回滚方案的基础）
        if os.path.exists(database.DB_PATH) and os.path.getsize(database.DB_PATH) > 0:
            backup_db()

        for m in MIGRATIONS:
            if m["version"] <= version:
                continue
            if m.get("sql"):
                conn.executescript(m["sql"])
            conn.execute(f"PRAGMA user_version = {int(m['version'])}")
            conn.commit()
            print(f"[数据库] 已升级到 v{m['version']}：{m['name']}")

        # 开启 WAL 模式（读写互不阻塞：扫描写库时网页不卡）
        # journal_mode=WAL 是数据库级设置，执行一次永久生效
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"数据库迁移失败：{e}") from e
    finally:
        conn.close()
