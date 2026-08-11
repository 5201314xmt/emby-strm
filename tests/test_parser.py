"""
============================================================
strm 文件解析器单元测试
运行方法：在项目根目录执行  python -m pytest tests -v
============================================================
"""

import os
import tempfile

import pytest

from app.scanner import filesystem as fs


# ------------------------------------------------------------
# TMDB 编号识别测试
# ------------------------------------------------------------

class TestFindTmdbId:
    def test_tmdb_in_parentheses(self):
        """剧名 (TMDB-1399) → 1399"""
        assert fs.find_tmdb_id("权力的游戏 (TMDB-1399)") == 1399

    def test_tmdb_no_separator(self):
        """[TMDB1399] → 1399（没有横线）"""
        assert fs.find_tmdb_id("[TMDB1399] 权力的游戏") == 1399

    def test_tmdb_lowercase_underscore(self):
        """{tmdb_1399} → 1399（小写+下划线）"""
        assert fs.find_tmdb_id("show {tmdb_1399}") == 1399

    def test_bare_number_in_brackets(self):
        """(1399) → 1399（括号里只有数字）"""
        assert fs.find_tmdb_id("权力的游戏 (1399)") == 1399

    def test_year_not_treated_as_id(self):
        """(2011) 是年份，不是 TMDB 编号 → None"""
        assert fs.find_tmdb_id("权力的游戏 (2011)") is None

    def test_tmdb_in_filename(self):
        """文件名里的 TMDB 编号也能识别"""
        assert fs.find_tmdb_id("Show.Name.TMDB12345.S01E01.strm") == 12345

    def test_no_id(self):
        """没有编号 → None"""
        assert fs.find_tmdb_id("普通文件夹") is None


# ------------------------------------------------------------
# 季号识别测试
# ------------------------------------------------------------

class TestFindSeason:
    def test_season_folder(self):
        assert fs.find_season_in_text("Season 01") == 1
        assert fs.find_season_in_text("Season 12") == 12

    def test_chinese_season(self):
        assert fs.find_season_in_text("第3季") == 3

    def test_s_folder(self):
        assert fs.find_season_in_text("S02") == 2

    def test_specials(self):
        assert fs.find_season_in_text("Specials") == 0
        assert fs.find_season_in_text("special") == 0

    def test_none(self):
        assert fs.find_season_in_text("随便写") is None


# ------------------------------------------------------------
# 集号识别测试
# ------------------------------------------------------------

class TestFindEpisodes:
    def test_single(self):
        assert fs.find_episodes_in_filename("show.S01E05.mkv.strm") == [5]

    def test_range(self):
        """S01E01-E03 → 1,2,3"""
        assert fs.find_episodes_in_filename("show.S01E01-E03.mkv.strm") == [1, 2, 3]

    def test_multi(self):
        """S01E05E06 → 5,6"""
        assert fs.find_episodes_in_filename("show.S01E05E06.mkv.strm") == [5, 6]

    def test_ep_only(self):
        """E02（迷你剧）→ 2"""
        assert fs.find_episodes_in_filename("迷你剧.E02.strm") == [2]

    def test_no_episode(self):
        assert fs.find_episodes_in_filename("show.mkv.strm") == []


# ------------------------------------------------------------
# 剧名清理测试
# ------------------------------------------------------------

class TestCleanName:
    def test_strip_tmdb_suffix(self):
        assert fs.clean_show_name("权力的游戏 (TMDB-1399)") == "权力的游戏"

    def test_strip_year(self):
        assert fs.clean_show_name("Friends (1994)") == "Friends"

    def test_keep_normal(self):
        assert fs.clean_show_name("老友记") == "老友记"


# ------------------------------------------------------------
# 整体扫描测试（用临时目录模拟真实 strm 目录）
# ------------------------------------------------------------

class TestScanDirectory:
    def _make_tree(self):
        """建一个模拟的 strm 目录树，覆盖多种命名格式"""
        tmp = tempfile.mkdtemp()
        # 格式1：剧名 (TMDB-1399)/Season 01/文件名.S01E01.strm
        d1 = os.path.join(tmp, "权力的游戏 (TMDB-1399)", "Season 01")
        os.makedirs(d1)
        open(os.path.join(d1, "GoT.S01E01.mkv.strm"), "w").close()
        open(os.path.join(d1, "GoT.S01E02-E03.mkv.strm"), "w").close()

        # 格式2：[TMDB12345] 剧名/第2季/...
        d2 = os.path.join(tmp, "[TMDB12345] 老友记", "第2季")
        os.makedirs(d2)
        open(os.path.join(d2, "Friends.S02E05E06.mkv.strm"), "w").close()

        # 格式3：TMDB 在文件名里
        d3 = os.path.join(tmp, "毒枭", "Season 1")
        os.makedirs(d3)
        open(os.path.join(d3, "Narcos.TMDB63351.S01E10.mkv.strm"), "w").close()

        # 格式4：一个无法识别的文件（没有 TMDB 编号）
        d4 = os.path.join(tmp, "无法识别的剧", "Season 1")
        os.makedirs(d4)
        open(os.path.join(d4, "Unknown.S01E01.mkv.strm"), "w").close()

        # 格式5：垃圾目录应该被跳过
        d5 = os.path.join(tmp, "权力的游戏 (TMDB-1399)", "@eaDir")
        os.makedirs(d5)
        open(os.path.join(d5, "junk.strm"), "w").close()

        return tmp

    def test_scan(self):
        root = self._make_tree()
        result = fs.scan([root])

        # 应该识别出 3 部剧
        assert 1399 in result.shows
        assert 12345 in result.shows
        assert 63351 in result.shows

        # 1399 的第一季：S01E01 + S01E02-E03 → 已有 1,2,3
        assert result.shows[1399]["seasons"][1] == [1, 2, 3]
        # 剧名被清理干净
        assert result.shows[1399]["name"] == "权力的游戏"

        # 12345 的第二季：S02E05E06 → 5,6
        assert result.shows[12345]["seasons"][2] == [5, 6]
        assert result.shows[12345]["name"] == "老友记"

        # 63351 的第一季：S01E10 → 10
        assert result.shows[63351]["seasons"][1] == [10]
        assert result.shows[63351]["name"] == "毒枭"

        # 无法识别的文件进入 unrecognized 列表
        assert len(result.unrecognized) == 1
        assert "没找到 TMDB 编号" in result.unrecognized[0]["reason"]
