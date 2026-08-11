"""
文件系统扫描器 —— 扫描 STRM 文件目录

复用原项目的正则匹配算法，支持多种命名格式：
  - 剧名 (TMDB-1399)/Season 01/剧名.S01E01.mkv.strm
  - [TMDB1399] 剧名/第1季/剧名.S01E05E06.strm
  - 剧名{tmdb-12345}/Specials/剧名.S00E01.strm
  - 剧名.TMDB12345.S01E03.strm（TMDB 在文件名里）
  - 剧名 (2020) (TMDB-1399)/Season 1/S01E01-E03.strm（范围）
  - {tmdbid=296915} 格式（Bero）

核心算法从原项目 app/scanner/filesystem.py 移植。
"""
import os
import re

from .base import ScanResult


# ============================================================
# 正则模式（核心解析算法，不要随意修改）
# ============================================================

# TMDB 编号识别：tmdb-1399 / tmdb_1399 / TMDBID:1399 / {tmdbid=296915}
_TMDB_PATTERN = re.compile(r"tmdb[-_.\s]?(?:id)?[-_.\s:=]*(\d{3,8})", re.IGNORECASE)

# 括号里的数字：(1399) [1399] {1399} {tmdbid=296915}
# 排除 1900-2099 的四位数（那是年份）
_BRACKET_PATTERN = re.compile(
    r"[\(\[\{](?:tmdb[-_.\s]?(?:id)?[-_.\s:=]*)?(\d{3,8})[\)\]\}]", re.IGNORECASE)
_YEAR_RANGE = range(1900, 2100)

# 季号识别：Season 01 / 第1季 / S01 / Specials
_SEASON_FOLDER_PATTERN = re.compile(r"(?:season|第)[-_.\s]?(\d{1,3})", re.IGNORECASE)
_S_FOLDER_PATTERN = re.compile(r"^s(\d{1,3})$", re.IGNORECASE)
_SPECIALS_PATTERN = re.compile(r"special", re.IGNORECASE)

# 集号识别：S01E01 / S01E01E02 / S01E01-E03 / E01
_SINGLE_EP_PATTERN = re.compile(r"[sS](\d{1,3})[eE](\d{1,4})")
_MULTI_EP_PATTERN = re.compile(r"[sS]\d{1,3}[eE](\d{1,4})[eE](\d{1,4})")
_RANGE_EP_PATTERN = re.compile(r"[sS]\d{1,3}[eE](\d{1,4})[-_][eE]?(\d{1,4})")
_EP_ONLY_PATTERN = re.compile(r"(?:^|[^\w])[eE](\d{1,4})(?:-[eE]?(\d{1,4}))?")

# 清理剧名（去掉目录名里的 (TMDB-1399)、(2011) 等尾巴）
_NAME_CLEAN_PATTERN = re.compile(
    r"\s*[\(\[\{][^\)\]\}]*?(?:tmdb|\d{4})[^\)\]\}]*?[\)\]\}]", re.IGNORECASE)

# 跳过目录（系统垃圾目录）
_SKIP_DIRS = {
    ".@__thumb", "@eadir", "#recycle", ".stfolder", ".stversions",
    "thumbnails", "thumbs", ".cache", ".trash", "$recycle.bin", "lost+found",
}


# ============================================================
# 核心解析函数
# ============================================================

def find_tmdb_id(text: str) -> int | None:
    """在一段文字里找 TMDB 编号，找不到返回 None"""
    m = _TMDB_PATTERN.search(text)
    if m:
        return int(m.group(1))
    for m in _BRACKET_PATTERN.finditer(text):
        num = int(m.group(1))
        if 1000 <= num <= 9999 and num in _YEAR_RANGE:
            continue  # 四位数且在 1900-2099 → 是年份，跳过
        return num
    return None


def find_season_in_text(text: str) -> int | None:
    """在目录名/文件名里找季号"""
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


def find_episodes_in_filename(filename: str) -> list[int]:
    """
    在文件名里找集号，返回 [集号...]（可能一集文件含多集）

    优先级：范围 > 多集 > 单集 > 迷你剧
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
    """把目录名里的 (TMDB-1399)、(2011) 等尾巴去掉"""
    name = _NAME_CLEAN_PATTERN.sub("", folder_name)
    name = re.sub(r"[\s._-]+$", "", name)
    return name.strip() or folder_name


def _should_skip_dir(dirname: str) -> bool:
    """判断这个目录要不要跳过"""
    return dirname.startswith(".") or dirname.lower() in _SKIP_DIRS


def _should_skip_file(filename: str) -> bool:
    """判断文件是否要跳过（只看 strm 文件）"""
    return not filename.lower().endswith(".strm")


# ============================================================
# 主扫描函数
# ============================================================

def scan_paths(paths: list[str], source_id: int = 0) -> ScanResult:
    """
    扫描一个或多个 STRM 目录

    Args:
        paths:     容器内路径列表，如 ["/media/139_video1", "/media/da-1"]
        source_id: 扫描源 ID（关联 sources 表）

    Returns:
        ScanResult（shows 字典 + unrecognized 列表）
    """
    result = ScanResult()
    for idx, root in enumerate(paths):
        if not root:
            continue
        _scan_one_root(root, source_id, result)
    return result


def _scan_one_root(root: str, source_id: int, result: ScanResult):
    """遍历一个目录树，解析每个 strm 文件"""
    if not root or not os.path.isdir(root):
        result.unrecognized.append({
            "path": root or "(空路径)",
            "source_id": source_id,
            "reason": "路径不存在，请检查挂载是否正确",
        })
        return

    for current_dir, dirnames, filenames in os.walk(root):
        # 跳过垃圾目录
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            if _should_skip_file(filename):
                continue

            file_path = os.path.join(current_dir, filename)
            rel_path = os.path.relpath(file_path, root)
            parts = rel_path.split(os.sep)
            _parse_one_file(root, parts, file_path, source_id, result)


def _parse_one_file(root: str, parts: list, file_path: str,
                    source_id: int, result: ScanResult):
    """
    解析单个 strm 文件：
      1. 从路径段里找 TMDB 编号
      2. 找集号（在文件名里）
      3. 找季号（文件名优先，其次目录名）
      4. 汇总到 result.shows
    """
    # 1. 找 TMDB 编号
    tmdb_id = None
    for part in parts[:-1]:
        tmdb_id = find_tmdb_id(part)
        if tmdb_id:
            break
    if tmdb_id is None:
        tmdb_id = find_tmdb_id(parts[-1])

    if tmdb_id is None:
        result.unrecognized.append({
            "path": file_path,
            "source_id": source_id,
            "reason": "没找到 TMDB 编号",
        })
        return

    # 2. 找集号
    episodes = find_episodes_in_filename(parts[-1])
    if not episodes:
        result.unrecognized.append({
            "path": file_path,
            "source_id": source_id,
            "reason": f"文件名里没认出集数（TMDB:{tmdb_id}）",
        })
        return

    # 3. 找季号
    season = None
    m = _SINGLE_EP_PATTERN.search(parts[-1])
    if m:
        season = int(m.group(1))
    else:
        for part in reversed(parts[:-1]):
            s = find_season_in_text(part)
            if s is not None:
                season = s
                break

    if season is None:
        result.unrecognized.append({
            "path": file_path,
            "source_id": source_id,
            "reason": f"没找到季号（TMDB:{tmdb_id}）",
        })
        return

    # 4. 汇总
    show = result.shows.setdefault(tmdb_id, {
        "name": "",
        "source_ids": set(),
        "seasons": {},
    })
    show["source_ids"].add(source_id)
    if not show["name"]:
        folder = parts[0] if len(parts) > 1 else parts[-1]
        show["name"] = clean_show_name(folder)
    season_set = show["seasons"].setdefault(season, [])
    for ep in episodes:
        if ep not in season_set:
            season_set.append(ep)
