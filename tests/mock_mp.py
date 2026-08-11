"""
============================================================
模拟 MoviePilot 服务器（端到端测试 + 压力测试用）
============================================================
作用：模拟 MoviePilot v3 的 API，让缺集管家在本地就能完整联调
  - 端到端测试：python mock_mp.py  （默认端口 19000）
  - 压力测试：from tests.mock_mp import start_server; start_server(19001)

用 FastAPI + uvicorn 实现（异步服务器，能扛压力测试的大并发，
旧的 BaseHTTPRequestHandler 版本在 3 万+ 并发请求时会线程堆积挂掉）
============================================================
"""

import re
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI

# 模拟的 TMDB 数据（只有测试用的几部剧）
# tmdb_id → { 季号: [ (集号, 播出日期), ... ] }
MOCK_TMDB = {
    1399: {  # 权力的游戏
        1: [(n, "2011-04-17") for n in range(1, 7)],
        2: [(n, "2012-04-01") for n in range(1, 11)],
    },
    12345: {  # 老友记
        1: [(n, "1994-09-22") for n in range(1, 25)],
    },
    63351: {  # 毒枭
        1: [(n, "2015-08-28") for n in range(1, 9)],
        2: [(n, "2016-09-02") for n in range(1, 11)],
    },
}

# 已创建的订阅记录
subscribes = []
_next_id = [1]


# ============================================================
# 动态生成 TMDB 数据（压力测试用：任意剧都能返回数据）
# 规则是确定性的，同样的 tmdb_id 每次生成一样的结果
# ============================================================

def _seasons_for(tmdb_id: int):
    """已知测试数据直接返回；未知剧生成 1~3 季"""
    if tmdb_id in MOCK_TMDB:
        return sorted(MOCK_TMDB[tmdb_id].keys())
    return list(range(1, 2 + tmdb_id % 3))


def _episodes_for(tmdb_id: int, season: int):
    """已知测试数据直接返回；未知剧生成 8~12 集（已播出）"""
    if tmdb_id in MOCK_TMDB and season in MOCK_TMDB[tmdb_id]:
        return MOCK_TMDB[tmdb_id][season]
    n = 8 + (tmdb_id + season) % 5
    return [(i, "2020-01-01") for i in range(1, n + 1)]


# ============================================================
# 模拟服务器
# ============================================================

def build_app() -> FastAPI:
    # redirect_slashes=False：不把 /api/v1/subscribe/ 301 到无斜杠（MoviePilot 客户端固定带斜杠）
    app = FastAPI(title="mock-moviepilot", redirect_slashes=False)

    @app.get("/api/v1/system/version")
    def version():
        return {"version": "v3.0.0-mock"}

    @app.get("/api/v1/subscribe/list")
    def subscribe_list():
        return subscribes

    @app.get("/api/v1/subscribe/search/{mp_id}")
    def subscribe_search(mp_id: int):
        return {"success": True, "message": "开始搜索"}

    @app.get("/api/v1/tmdb/seasons/{tmdb_id}")
    def tmdb_seasons(tmdb_id: int):
        return [{"season_number": s, "episode_count": len(_episodes_for(tmdb_id, s))}
                for s in _seasons_for(tmdb_id)]

    @app.get("/api/v1/tmdb/{tmdb_id}/{season}")
    def tmdb_episodes(tmdb_id: int, season: int):
        return [{"episode_number": n, "air_date": d, "name": f"EP{n}"}
                for n, d in _episodes_for(tmdb_id, season)]

    @app.post("/api/v1/subscribe/")
    def create_subscribe(body: dict):
        tmdb_id = body.get("tmdbid")
        season = body.get("season")
        # 模拟"重复订阅"检查（和真实 MP 一致）
        for s in subscribes:
            if s.get("tmdbid") == tmdb_id and s.get("season") == season:
                return {"success": False, "message": "该媒体已订阅"}
        sub = {
            "id": _next_id[0],
            "name": body.get("name", ""),
            "year": body.get("year", ""),
            "type": body.get("type", "TV"),
            "tmdbid": tmdb_id,
            "season": season,
            "state": "R",
            "total_episode": body.get("total_episode", 0),
            "lack_episode": body.get("total_episode", 0),
        }
        _next_id[0] += 1
        subscribes.append(sub)
        return {"success": True, "message": "创建订阅成功", "data": {"id": sub["id"]}}

    @app.delete("/api/v1/subscribe/{mp_id}")
    def delete_subscribe(mp_id: int):
        global subscribes
        subscribes = [s for s in subscribes if s.get("id") != mp_id]
        return {"success": True, "message": "删除成功"}

    @app.delete("/reset")
    def reset():
        """测试用：重置所有模拟数据（清空订阅列表）"""
        global subscribes
        subscribes = []
        _next_id[0] = 1
        return {"success": True, "message": "已重置"}

    return app


def start_server(port: int = 19000, wait: bool = True):
    """
    在后台线程启动模拟 MoviePilot 服务器
    wait=True 时等待服务器就绪再返回（默认）
    返回 uvicorn.Server 实例
    """
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    if wait:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/api/v1/system/version", timeout=1)
                return server
            except Exception:
                time.sleep(0.1)
    return server


def stop_server(server: uvicorn.Server):
    """停止模拟服务器"""
    try:
        server.should_exit = True
    except Exception:
        pass


if __name__ == "__main__":
    print("Mock MoviePilot 已启动: http://127.0.0.1:19000")
    uvicorn.run(build_app(), host="127.0.0.1", port=19000, log_level="info")
