"""
============================================================
文件系统扫描器 - 扫描 strm 文件目录，识别出"目前有哪些集"
============================================================
说明：
  - 自动识别各种常见的目录/文件名命名方式，小白不用配置格式
  - 支持格式举例：
      剧名 (TMDB-1399)/Season 01/剧名.S01E01.mkv.strm
      [TMDB1399] 剧名/第1季/剧名.S01E05E06.strm
      剧名{tmdb-12345}/Specials/剧名.S00E01.strm
      剧名.TMDB12345.S01E03.strm（TMDB 在文件名里）
      剧名 (2020) (TMDB-1399)/Season 1/剧名.S01E01-E03.strm（一集文件含多集）
  - 识别不了的目录/文件会记录到"未识别"列表，网页上可以看到原因
============================================================
"""

import os
import re

from ..models import ScanResult
from .. import logger

# ============================================================
# 各种命名格式的正则表达式（核心：自动识别）
# ============================================================

# 1. 明确的 TMDB 标记：tmdb-1399 / tmdb_1399 / tmdb1399 / TMDBID:1399 等
#    只要出现 "tmdb" 字样，后面跟的数字就是 TMDB 编号
_TMDB_PATTERN = re.compile(r"tmdb[-_.\s]?(?:id)?[-_.\s:]*(\d{3,8})", re.IGNORECASE)

# 2. 括号/方括号/花括号里的数字： (1399) [1399] {1399}
#    排除 1900-2099 的四位数（那是年份不是编号，如 "权力的游戏 (2011)"）
_BRACKET_PATTERN = re.compile(r"[\(\[\{](?:tmdb[-_.\s]?)?(\d{3,8})[\)\]\}]", re.IGNORECASE)
_YEAR_RANGE = range(1900, 2100)

# 3. 季号：目录里的 "Season 01" / "第1季" / "S01" / "Specials"(特别篇=0)
_SEASON_FOLDER_PATTERN = re.compile(r"(?:season|第)[-_.\s]?(\d{1,3})", re.IGNORECASE)
_S_FOLDER_PATTERN = re.compile(r"^s(\d{1,3})$", re.IGNORECASE)          # 目录名就是 S01
_SPECIALS_PATTERN = re.compile(r"special", re.IGNORECASE)

# 4. 文件名里的集数：
_SINGLE_EP_PATTERN = re.compile(r"[sS](\d{1,3})[eE](\d{1,4})")          # S01E01
_MULTI_EP_PATTERN = re.compile(r"[sS]\d{1,3}[eE](\d{1,4})[eE](\d{1,4})")  # S01E01E02（一个文件两集）
_RANGE_EP_PATTERN = re.compile(r"[sS]\d{1,3}[eE](\d{1,4})[-_][eE]?(\d{1,4})")  # S01E01-E03（一集文件含连续多集）
_EP_ONLY_PATTERN = re.compile(r"(?:^|[^\w])[eE](\d{1,4})(?:-[eE]?(\d{1,4}))?")  # E01 / E01-E03（迷你剧）

# 5. 清理剧名：去掉目录名里的 (TMDB-1399) (2011) 等尾巴，留下干净剧名
_NAME_CLEAN_PATTERN = re.compile(r"\s*[\(\[\{][^\)\]\}]*?(?:tmdb|\d{4})[^\)\]\}]*?[\)\]\}]", re.IGNORECASE)

# 6. 忽略的目录（各种系统垃圾目录，跳过不扫）
_SKIP_DIRS = {".@__thumb", "@eadir", "#recycle", ".stfolder", ".stversions",
              "thumbnails", "thumbs", ".cache", ".trash", "$recycle.bin", "lost+found"}


# ============================================================
# 核心解析函数（每个函数只做一件事，方便测试和扩展）
# ============================================================

def find_tmdb_id(text: str):
    """
    在一段文字（目录名或文件名）里找 TMDB 编号，找不到返回 None
    顺序：优先认 "tmdb" 字样，其次认括号里的数字（排除年份）
    """
    # 先找明确的 tmdb 标记
    m = _TMDB_PATTERN.search(text)
    if m:
        return int(m.group(1))
    # 再找括号/方括号/花括号里的数字
    for m in _BRACKET_PATTERN.finditer(text):
        num = int(m.group(1))
        # 4 位数且在 1900-2099 之间 → 是年份，跳过
        if 1000 <= num <= 9999 and num in _YEAR_RANGE:
            continue
        return num
    return None


def find_season_in_text(text: str):
    """
    在目录名或文件名里找季号，找不到返回 None
    例：Season 01 → 1，第3季 → 3，S02 → 2，Specials → 0
    """
    m = _SEASON_FOLDER_PATTERN.search(text)
    if m:
        return int(m.group(1))
    m = _SPECIALS_PATTERN.search(text)
    if m:
        return 0
    m = _S_FOLDER_PATTERN.search(text)
    if m:
        return int(m.group(1))
    return None


def find_episodes_in_filename(filename: str):
    """
    在文件名里找集号，返回 [集号...]（可能一集文件含多集），找不到返回空列表
    优先级：S01E01-E03(范围) > S01E01E02(两个) > S01E01(单个) > E01(迷你剧)
    """
    m = _RANGE_EP_PATTERN.search(filename)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if end >= start:
            return list(range(start, end + 1))
        return [start]
    m = _MULTI_EP_PATTERN.search(filename)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    m = _SINGLE_EP_PATTERN.search(filename)
    if m:
        return [int(m.group(2))]
    m = _EP_ONLY_PATTERN.search(filename)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if end >= start:
            return list(range(start, end + 1))
        return [start]
    return []


def clean_show_name(folder_name: str) -> str:
    """把目录名里的 (TMDB-1399)、(2011) 等尾巴去掉，得到干净剧名"""
    name = _NAME_CLEAN_PATTERN.sub("", folder_name)
    name = re.sub(r"[\s._-]+$", "", name)   # 去掉结尾多余的空格/点/横线
    return name.strip() or folder_name


def _should_skip_dir(dirname: str) -> bool:
    """判断这个目录要不要跳过（隐藏目录和系统垃圾目录）"""
    return dirname.startswith(".") or dirname.lower() in _SKIP_DIRS


def _should_skip_file(filename: str) -> bool:
    """判断文件是否要跳过（只看 strm 文件，其余一律跳过）"""
    return not filename.lower().endswith(".strm")


# ============================================================
# 主扫描函数
# ============================================================

def scan(paths: list) -> ScanResult:
    """
    扫描一个或多个 strm 目录
    参数：paths = ["/media", "/media2"] （容器内的路径，网页上配置）
    返回：ScanResult（shows 字典 + unrecognized 未识别列表）
    """
    result = ScanResult()
    # 记录"当前正在扫哪个目录"，扫描进度用
    total_dirs = len(paths)
    for idx, root in enumerate(paths):
        logger.log("INFO", "scan", f"扫描目录 {idx + 1}/{total_dirs}: {root}")
        _scan_one_root(root, result)
    return result


def _scan_one_root(root: str, result: ScanResult):
    """
    扫描一个目录树：
      对每个 strm 文件，解析出 (TMDB编号, 季号, 集号)，汇总到 result
    """
    if not root or not os.path.isdir(root):
        result.unrecognized.append({"path": root or "(空路径)", "reason": "路径不存在，请检查挂载是否正确"})
        return

    # os.walk 遍历所有子目录（prune 掉要跳过的目录）
    for current_dir, dirnames, filenames in os.walk(root):
        # 跳过垃圾目录
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            if _should_skip_file(filename):
                continue

            file_path = os.path.join(current_dir, filename)
            # 拿到从 root 开始的相对路径（拆成一段段，方便识别哪段是剧目录）
            rel_path = os.path.relpath(file_path, root)
            parts = rel_path.split(os.sep)  # 例: ["剧名 (TMDB-1399)", "Season 01", "剧名.S01E01.strm"]

            _parse_one_file(root, parts, file_path, result)


def _parse_one_file(root: str, parts: list, file_path: str, result: ScanResult):
    """
    解析单个 strm 文件：
      步骤：1. 从所有路径段里找 TMDB 编号
            2. 找季号（文件名优先，其次目录名）
            3. 找集号（在文件名里）
            4. 汇总到 result.shows
    任何一步失败 → 记入未识别列表
    """
    # ---- 1. 找 TMDB 编号（目录名里找，找不到再看文件名）----
    tmdb_id = None
    for part in parts[:-1]:          # 除文件名外的目录段
        tmdb_id = find_tmdb_id(part)
        if tmdb_id:
            break
    if tmdb_id is None:
        tmdb_id = find_tmdb_id(parts[-1])   # 文件名里找

    if tmdb_id is None:
        result.unrecognized.append({"path": file_path, "reason": "没找到 TMDB 编号（目录或文件名中都没有）"})
        return

    # ---- 2. 找集号（必须在文件名里，否则这文件不知道是哪集）----
    episodes = find_episodes_in_filename(parts[-1])
    if not episodes:
        result.unrecognized.append({"path": file_path, "reason": f"文件名里没认出集数（TMDB: {tmdb_id}）"})
        return

    # ---- 3. 找季号：文件名里的 Sxx 优先，其次看目录名 ----
    season = None
    # 文件名里找（S01E05 这种）
    m = _SINGLE_EP_PATTERN.search(parts[-1])
    if m:
        season = int(m.group(1))
    else:
        # 目录名里找（Season 01 / 第1季 / S01 / Specials）
        for part in reversed(parts[:-1]):   # 从里往外找，先看最近的目录
            s = find_season_in_text(part)
            if s is not None:
                season = s
                break

    if season is None:
        result.unrecognized.append({"path": file_path, "reason": f"没找到季号（TMDB: {tmdb_id}）"})
        return

    # ---- 4. 汇总：tmdb_id → { 季号: [集号...] } ----
    show = result.shows.setdefault(tmdb_id, {"name": "", "seasons": {}})
    if not show["name"]:
        # 用第一个目录段作为剧名（去掉 (TMDB-xxx) 尾巴）
        folder = parts[0] if len(parts) > 1 else parts[-1]
        show["name"] = clean_show_name(folder)
    season_set = show["seasons"].setdefault(season, [])
    for ep in episodes:
        if ep not in season_set:
            season_set.append(ep)
