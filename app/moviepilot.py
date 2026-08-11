"""
============================================================
MoviePilot 客户端 - 负责和 MoviePilot 的所有通信
============================================================
说明：
  - 用 MoviePilot 的 HTTP API（v2 / v3 通用接口，已从官方源码验证）
  - 鉴权方式：请求里带 ?token=xxx（xxx 是 MoviePilot 设置->安全->API令牌）
  - 所有方法失败时返回 (False, "中文错误原因")，方便小白看懂
============================================================
"""

import httpx

from . import logger

# 请求超时时间（秒）：MoviePilot 响应慢时多等一会
_TIMEOUT = 30


class MoviePilotClient:
    """
    MoviePilot API 客户端
    用法：
      mp = MoviePilotClient("http://192.168.1.100:3000", "你的token")
      ok, msg = mp.test_connection()          # 测试连接
      ok, data = mp.list_subscribes()          # 获取订阅列表
      ok, data = mp.create_subscribe(...)      # 创建订阅
      ok, msg = mp.delete_subscribe(订阅id)    # 删除订阅
    """

    def __init__(self, url: str = "", token: str = ""):
        # 去掉地址末尾多余的斜杠，避免拼 URL 出错
        self.url = (url or "").rstrip("/")
        self.token = token or ""
        # 共享 HTTP 客户端（复用连接池 + SSL 上下文，避免每个请求重新握手，
        # 对性能影响极大：扫描 10 万部剧时能省几十分钟）
        self._client = None

    def _get_client(self) -> httpx.Client:
        """懒创建共享 HTTP 客户端（httpx.Client 是线程安全的，可多线程复用）"""
        if self._client is None:
            self._client = httpx.Client(timeout=_TIMEOUT)
        return self._client

    # ============================================================
    # 内部工具
    # ============================================================

    def _api(self, method: str, path: str, params: dict = None, json_body: dict = None):
        """
        发送 API 请求（所有方法共用）
        返回：(ok: bool, data)   data 是解析后的 JSON 或错误信息字符串
        """
        if not self.url or not self.token:
            return False, "MoviePilot 地址或 API Token 未填写，请先到设置页配置"
        try:
            # token 通过查询参数传递（v2/v3 都支持这种鉴权）
            params = dict(params or {})
            params["token"] = self.token
            resp = self._get_client().request(
                method, self.url + path, params=params,
                json=json_body, timeout=_TIMEOUT,
            )
            # 未授权：多半是 Token 填错了
            if resp.status_code in (401, 403):
                return False, "API Token 不正确（MoviePilot 设置->安全 里查看）"
            if resp.status_code == 404:
                return False, f"接口不存在（{path}），可能是 MoviePilot 版本不支持"
            if resp.status_code >= 500:
                return False, f"MoviePilot 服务器错误（{resp.status_code}）"
            try:
                return True, resp.json()
            except Exception:
                return False, f"返回内容无法解析（{resp.text[:100]}）"
        except httpx.TimeoutException:
            return False, "连接 MoviePilot 超时，请检查地址和网络"
        except httpx.ConnectError:
            return False, "连不上 MoviePilot，请检查地址是否正确、MoviePilot 是否已启动"
        except Exception as e:
            return False, f"请求出错：{e}"

    # ============================================================
    # 连接测试
    # ============================================================

    def test_connection(self) -> dict:
        """
        测试连接，返回详细信息（设置页"测试连接"按钮用）
        返回：{"ok": True/False, "version": 版本号, "message": 说明}
        """
        ok, data = self._api("GET", "/api/v1/system/version")
        if not ok:
            # 老版本可能没有这个接口，再试试订阅列表接口
            ok2, data2 = self._api("GET", "/api/v1/subscribe/list")
            if ok2 and isinstance(data2, list):
                return {"ok": True, "version": "未知版本", "message": "连接成功（MoviePilot 版本较老，部分功能受限）"}
            return {"ok": False, "version": "", "message": data}
        version = (data or {}).get("version", "未知")
        return {"ok": True, "version": version, "message": "连接成功"}

    # ============================================================
    # 订阅管理
    # ============================================================

    def list_subscribes(self):
        """
        获取 MoviePilot 当前所有订阅
        返回：(ok, data)  成功时 data 是订阅列表
        """
        return self._api("GET", "/api/v1/subscribe/list")

    def create_subscribe(self, name: str, year: str, tmdb_id: int,
                         season: int, total_episode: int) -> tuple:
        """
        创建订阅（按季订阅，MoviePilot 会自动只下载缺失的集）
        参数：
          name         剧名
          year         年份（可空）
          tmdb_id      TMDB 编号
          season       季号
          total_episode 这一季总集数（已播出的）
        返回：(ok, msg)
        """
        body = {
            "name": name,
            "year": year or "",
            "type": "TV",
            "tmdbid": int(tmdb_id),
            "season": int(season),
            "start_episode": 1,
            "total_episode": int(total_episode),
        }
        ok, data = self._api("POST", "/api/v1/subscribe/", json_body=body)
        if not ok:
            return False, data
        # 接口统一返回 {"success": true/false, "message": "..."}
        if isinstance(data, dict) and data.get("success") is False:
            return False, data.get("message", "创建订阅失败")
        mp_id = None
        if isinstance(data, dict):
            mp_id = (data.get("data") or {}).get("id")
        return True, mp_id

    def delete_subscribe(self, mp_id: int) -> tuple:
        """删除 MoviePilot 里的一个订阅，返回 (ok, msg)"""
        return self._api("DELETE", f"/api/v1/subscribe/{int(mp_id)}")

    def search_subscribe(self, mp_id: int) -> tuple:
        """
        让 MoviePilot 立刻搜索这个订阅（不用等定时刷新）
        老版本可能不支持，失败也没关系，等定时刷新也会搜
        """
        return self._api("GET", f"/api/v1/subscribe/search/{int(mp_id)}")

    # ============================================================
    # TMDB 数据代理（MoviePilot v3 提供，用 MP 自己的 TMDB 账号查数据）
    # 这样小白就不用自己去申请 TMDB API Key 了
    # ============================================================

    def tmdb_supported(self) -> bool:
        """探测 MoviePilot 是否支持 TMDB 代理接口"""
        ok, data = self._api("GET", "/api/v1/tmdb/seasons/1399")
        return ok and isinstance(data, list)

    def tmdb_seasons(self, tmdb_id: int):
        """
        获取一部剧的所有季信息（通过 MP 代理）
        返回：(ok, data)  data 是季列表，每项含 season_number / episode_count
        """
        return self._api("GET", f"/api/v1/tmdb/seasons/{int(tmdb_id)}")

    def tmdb_episodes(self, tmdb_id: int, season: int):
        """
        获取某一季的全部集数信息（通过 MP 代理）
        返回：(ok, data)  data 是集列表，每项含 episode_number / air_date
        """
        return self._api("GET", f"/api/v1/tmdb/{int(tmdb_id)}/{int(season)}")

    # ============================================================
    # 订阅状态同步（给网页"订阅管理"页用）
    # ============================================================

    def sync_subscribe_map(self) -> int:
        """
        从 MoviePilot 拉取订阅列表，更新本地订阅记录（subscribe_map 表）
        作用：
          - 我们创建的订阅：更新最新状态（等待/搜索中/已完成）
          - 用户在 MoviePilot 网页手动创建的订阅：也会同步进来（防止重复订阅）
          - 在 MoviePilot 里已删除的订阅：本地记录同步删除（防止误以为还在订阅）
        返回：成功同步的订阅数量
        """
        ok, data = self.list_subscribes()
        if not ok or not isinstance(data, list):
            logger.log("WARN", "subscribe", f"同步订阅状态失败：{data}")
            return 0
        from . import database
        count = 0
        mp_ids = []
        for sub in data:
            tmdb_id = sub.get("tmdbid")
            season = sub.get("season") or 0
            mp_id = sub.get("id")
            mp_ids.append(mp_id)
            if not tmdb_id:
                continue
            # 本地已有一条 (tmdb_id, season) 记录 → 更新状态和 MP 订阅 id
            row = database.query_one(
                "SELECT id FROM subscribe_map WHERE tmdb_id=? AND season=?",
                (tmdb_id, season),
            )
            if row:
                database.execute(
                    "UPDATE subscribe_map SET state=?, name=?, mp_id=? WHERE id=?",
                    (sub.get("state", ""), sub.get("name", ""), mp_id, row["id"]),
                )
            else:
                # 本地没有 → 说明是用户手动建的订阅，补记一条
                database.execute(
                    "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
                    (tmdb_id, season, mp_id, sub.get("name", ""), sub.get("state", "")),
                )
            count += 1

        # 清理"在 MoviePilot 里已不存在"的本地记录（订阅被删了，本地也删掉）
        # 只清理有真实 mp_id 的记录；mp_id=0/空 的记录是"MP 拒绝重复订阅"时
        # 打的标记，保留它防止每次扫描都重复尝试提交
        for row in database.query(
                "SELECT id, mp_id FROM subscribe_map WHERE mp_id IS NOT NULL AND mp_id != 0"):
            if row["mp_id"] not in mp_ids:
                database.execute("DELETE FROM subscribe_map WHERE id=?", (row["id"],))
        return count
