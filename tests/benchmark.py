"""
============================================================
压力测试脚本（模拟 10 万剧 / 百万级 STRM 文件）
用法：
  python tests/benchmark.py 1000      # 1000 部剧（快速验证）
  python tests/benchmark.py 10000     # 1 万部剧
  python tests/benchmark.py 100000    # 10 万部剧（模拟目标容量）

流程：
  1. 生成 N 部剧的假 strm 目录（每部 1~3 季，部分缺集）
  2. 启动 mock MoviePilot（内存 TMDB 数据，本机响应 ≈ 真实网络延迟的 1/10）
  3. 跑第一次扫描（冷缓存）→ 计时
  4. 跑第二次扫描（热缓存，验证磁盘缓存效果）→ 计时
  5. 输出：扫描耗时 / 内存峰值 / 数据库大小 / 缺集统计 / 每部剧平均耗时

注意：
  - 结果不含"真实 TMDB 网络延迟"（真实环境冷缓存会慢很多，受接口限速）
  - 跑完会把临时目录清理干净，不影响真实数据
============================================================
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time

# 保证能从项目根目录 import app（脚本可能在任意目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 把数据库指到临时目录（必须在导入 app.main 之前）
from app import database as _db

_BASE_DIR = tempfile.mkdtemp(prefix="queji_bench_")
_db.DATA_DIR = _BASE_DIR
_db.DB_PATH = os.path.join(_BASE_DIR, "queji.db")
_db.init_db()

from app.main import app, runner  # noqa: E402
from tests.mock_mp import start_server, stop_server  # noqa: E402

try:
    import psutil  # 可选：测量内存
    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False


def make_library(root: str, n: int):
    """
    生成 N 部剧的假 strm 目录：
      tmdb_id 从 100000 开始连续编号
      每部剧 1~3 季，每季 8~12 集，只保留一半集（制造缺集）
    """
    total_files = 0
    for i in range(n):
        tmdb_id = 100000 + i
        show_dir = os.path.join(root, f"测试剧集{i:06d} (TMDB-{tmdb_id})")
        for season in range(1, 2 + i % 3):
            season_dir = os.path.join(show_dir, f"Season {season:02d}")
            os.makedirs(season_dir, exist_ok=True)
            ep_count = 8 + (i + season) % 5
            for ep in range(1, ep_count + 1):
                # 只保留一半集（奇数的留，偶数的缺）
                if ep % 2 == 0:
                    continue
                with open(os.path.join(season_dir, f"show.S{season:02d}E{ep:02d}.strm"),
                          "w") as f:
                    f.write("")
                total_files += 1
    return total_files


def make_scan_result(n: int):
    """内存直接构建扫描结果（--light 模式用，跳过文件系统）"""
    from app.models import ScanResult
    res = ScanResult()
    for i in range(n):
        tid = 100000 + i
        seasons = {}
        for s in range(1, 2 + i % 3):
            seasons[s] = [e for e in range(1, 8 + (i + s) % 5 + 1) if e % 2 == 0]
        res.shows[tid] = {"name": f"测试剧集{i:06d}", "seasons": seasons}
    return res


def run_scan(tag: str, light: bool = False):
    """跑一次完整扫描（light=跳过文件系统，直接分析内存结果）"""
    t0 = time.time()
    if light:
        runner._analyze_all(make_scan_result(N_SHOWS))
    else:
        runner._run_scan(True)
    t1 = time.time()
    err = runner.status.get("error", "")
    print(f"  [{tag}] 耗时 {t1 - t0:.1f} 秒"
          + (f"，错误：{err}" if err else ""))
    return t1 - t0


def fs_scan_time(media_dir: str):
    """单独计时文件系统扫描阶段（不查 TMDB）"""
    from app.scanner import filesystem as fs
    t0 = time.time()
    res = fs.scan([media_dir])
    return time.time() - t0, len(res.shows)


def build_scan_result(media_dir: str):
    """从生成的目录构建扫描结果（或 --light 时内存直建）"""
    from app.scanner import filesystem as fs
    return fs.scan([media_dir])


def db_size_mb():
    size = os.path.getsize(_db.DB_PATH) if os.path.exists(_db.DB_PATH) else 0
    return size / 1024 / 1024


def mem_mb():
    if not HAVE_PSUTIL:
        return -1
    return psutil.Process().memory_info().rss / 1024 / 1024


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    light = "--light" in sys.argv          # 跳过文件生成，内存直建扫描结果（超大 N 用）
    n = int(args[0]) if args else 1000
    global N_SHOWS
    N_SHOWS = n
    print(f"==================================================")
    print(f"  缺集管家压力测试：{n} 部剧{'（无文件模式）' if light else ''}")
    print(f"==================================================")

    # 1. 生成假媒体库（--light 模式跳过）
    media_dir = os.path.join(_BASE_DIR, "media")
    total_files = 0
    if not light:
        print(f"[1/4] 生成 {n} 部剧的假 strm 目录...")
        t0 = time.time()
        total_files = make_library(media_dir, n)
        print(f"      完成：{total_files} 个 STRM 文件，耗时 {time.time() - t0:.1f} 秒")

    # 2. 启动 mock MoviePilot
    print("[2/4] 启动 mock MoviePilot（内存 TMDB 数据）...")
    mock_server = start_server(19001)
    from app.config import Config
    cfg = Config()
    cfg.set_many({
        "mp_url": "http://127.0.0.1:19001",
        "mp_token": "bench-token",
        "scan_paths": json.dumps([media_dir]),
        "auto_subscribe": "0",
    })
    cfg.reload()
    runner.config = cfg
    runner.mp = runner.mp.__class__("http://127.0.0.1:19001", "bench-token")
    runner.reset_tmdb_source()

    # 2.5 单独计时文件系统扫描（不查 TMDB）
    if not light:
        print(f"[2.5/4] 单独计时文件系统扫描...")
        fs_secs, fs_shows = fs_scan_time(media_dir)
        print(f"      文件扫描耗时 {fs_secs:.1f} 秒（{fs_secs / max(fs_shows, 1) * 1000:.2f} ms/部）")
    else:
        fs_secs, fs_shows = 0, 0

    # 3. 冷缓存扫描 + 热缓存扫描
    print(f"[3/4] 开始扫描（本机 mock TMDB，不含真实网络延迟）...")
    mem0 = mem_mb()
    cold = run_scan("冷缓存（首次扫描）", light)
    mem1 = mem_mb()
    # 重建 TMDB 数据源 = 模拟程序重启（内存缓存清空，磁盘缓存保留）
    runner.reset_tmdb_source()
    hot = run_scan("热缓存（磁盘缓存，模拟重启后再扫）", light)
    mem2 = mem_mb()

    # 4. 统计
    print(f"[4/4] 统计结果")
    shows = _db.query_one("SELECT COUNT(*) c FROM shows")["c"]
    seasons = _db.query_one("SELECT COUNT(*) c FROM seasons")["c"]
    missing = _db.query_one(
        "SELECT COALESCE(SUM(json_array_length(missing_episodes)),0) c FROM seasons "
        "WHERE missing_episodes != '[]' AND missing_episodes != ''")["c"]
    errors = _db.query_one("SELECT COUNT(*) c FROM shows WHERE status='error'")["c"]
    cache_rows = _db.query_one("SELECT COUNT(*) c FROM tmdb_cache")["c"]
    logs = _db.query_one("SELECT COUNT(*) c FROM logs")["c"]

    print("")
    print("========== 测试结果 ==========")
    print(f"剧集数:            {shows} 部")
    print(f"季数:              {seasons} 季")
    print(f"缺集总数:          {missing} 集")
    print(f"识别异常:          {errors} 部")
    print(f"TMDB 缓存条目:     {cache_rows} 条")
    print(f"日志条数(截断后):  {logs} 条")
    print(f"STRM 文件数:       {total_files if not light else '（--light 模式未生成）'} 个")
    print(f"冷缓存扫描:        {cold:.1f} 秒（{cold / max(n, 1) * 1000:.2f} ms/部）")
    print(f"热缓存扫描:        {hot:.1f} 秒（{hot / max(n, 1) * 1000:.2f} ms/部）")
    print(f"冷→热提速:         {cold / max(hot, 0.01):.1f} 倍")
    print(f"数据库大小:        {db_size_mb():.1f} MB")
    if HAVE_PSUTIL:
        print(f"内存峰值:          {max(mem0, mem1, mem2):.0f} MB（psutil）")
    else:
        print(f"内存:              （未安装 psutil，跳过）")
    print("==============================")
    print("提示：真实 TMDB 接口有请求频率限制，冷缓存扫描在真实环境会慢很多；")
    print("     热缓存扫描结果基本等于真实体验（走磁盘缓存，不请求 TMDB）。")

    # 清理
    stop_server(mock_server)
    shutil.rmtree(_BASE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
