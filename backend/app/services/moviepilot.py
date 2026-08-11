"""
MoviePilot 客户端 —— 封装 MoviePilot HTTP API 调用

接口一览：
  - 连接测试（版本检测）
  - TMDB 代理（获取剧信息 / 季集列表）
  - 订阅管理（创建/删除/搜索）
  - 订阅状态同步

复用原项目的 API 对接逻辑，改为 async/await 异步模式。
"""
import httpx
from ..config import settings as app_settings


class MoviePilotClient:
    """
    MoviePilot HTTP API 客户端

    所有方法都是 async，调用方需用 await。
    网络错误时返回 (False, 错误描述)。
    """

    def __init__(self, url: str = None, token: str = None):
        self.url = (url or app_settings.mp_url).rstrip("/")
        self.token = token or app_settings.mp_token
        self.version = ""
        self._client: httpx.AsyncClient = None

    def _headers(self) -> dict:
        """构造认证请求头（同时发送 Authorization 和 X-API-Key，兼容不同 MP 版本）"""
        return {
            "Authorization": self.token,
            "X-API-Key": self.token,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    @property
    def is_configured(self) -> bool:
        """是否已配置了 MP 连接信息"""
        return bool(self.url and self.token)

    async def test_connection(self) -> dict:
        """
        测试与 MoviePilot 的连接

        依次尝试多个端点来检测 MP 是否可用（某些 MP 版本不暴露根路径）。
        Returns:
            {"ok": True/False, "message": "...", "version": "..."}
        """
        if not self.is_configured:
            return {"ok": False, "message": "MoviePilot 地址或 Token 未配置", "version": ""}
        try:
            client = await self._get_client()
            headers = self._headers()

            # 尝试多个路径检测 MP 可用性（某些版本 /api/v1/ 返回 404）
            for path in ["/api/v1/", "/api/v1/tmdb/seasons/1399", "/api/v1/subscribe/"]:
                try:
                    resp = await client.get(f"{self.url}{path}", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json() if path == "/api/v1/" else {}
                        self.version = data.get("version", "") if isinstance(data, dict) else ""
                        return {
                            "ok": True,
                            "message": f"连接成功（{path}）" + (f" v{self.version}" if self.version else ""),
                            "version": self.version,
                        }
                except Exception:
                    continue

            return {"ok": False, "message": "MoviePilot 所有端点均无响应，请检查地址和 Token", "version": ""}
        except Exception as e:
            return {"ok": False, "message": f"连接失败：{e}", "version": ""}

    # ========== TMDB 代理接口（MoviePilot v3+ 支持） ==========

    async def tmdb_supported(self) -> bool:
        """检测 MP 是否支持 TMDB 代理接口"""
        if not self.is_configured:
            return False
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.url}/api/v1/tmdb/seasons/1399",
                headers=self._headers(),
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def tmdb_seasons(self, tmdb_id: int):
        """
        通过 MP 代理获取剧的季列表

        Returns:
            (ok, data): 成功时 data 为季列表，失败时 data 为错误描述
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.url}/api/v1/tmdb/seasons/{tmdb_id}",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"MP 返回 {resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def tmdb_episodes(self, tmdb_id: int, season: int):
        """
        通过 MP 代理获取某一季的集列表

        Returns:
            (ok, data): 成功时 data 为集列表，失败时 data 为错误描述
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.url}/api/v1/tmdb/episodes/{tmdb_id}/{season}",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"MP 返回 {resp.status_code}"
        except Exception as e:
            return False, str(e)

    # ========== 订阅管理 ==========

    async def list_subscribes(self):
        """
        获取 MP 中所有订阅列表

        Returns:
            (ok, data): 成功时 data 为订阅列表，失败时 data 为错误描述
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.url}/api/v1/subscribe/",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"MP 返回 {resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def create_subscribe(self, name: str, year: str, tmdb_id: int,
                               season: int, total_episode: int = 0):
        """
        向 MoviePilot 创建订阅

        Returns:
            (ok, data): 成功时 data 为订阅 ID，失败时 data 为错误描述
        """
        try:
            client = await self._get_client()
            body = {
                "name": name,
                "year": year,
                "tmdbid": tmdb_id,
                "season": season,
                "total_episode": total_episode or 24,
            }
            resp = await client.post(
                f"{self.url}/api/v1/subscribe/",
                headers=self._headers(),
                json=body,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                mp_id = data.get("id") if isinstance(data, dict) else data
                return True, mp_id
            # 常见情况：已经订阅过
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = resp.text
            if "已订阅" in detail or "already" in detail.lower():
                return False, "已在订阅中"
            return False, detail or f"创建失败（{resp.status_code}）"
        except Exception as e:
            return False, str(e)

    async def delete_subscribe(self, mp_id: int):
        """删除 MoviePilot 订阅"""
        try:
            client = await self._get_client()
            resp = await client.delete(
                f"{self.url}/api/v1/subscribe/",
                headers=self._headers(),
                params={"id": mp_id},
            )
            if resp.status_code in (200, 204):
                return True, "已删除"
            return False, f"删除失败（{resp.status_code}）"
        except Exception as e:
            return False, str(e)

    async def search_subscribe(self, mp_id: int):
        """触发 MoviePilot 立即搜索某个订阅"""
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/api/v1/subscribe/search/{mp_id}",
                headers=self._headers(),
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    async def sync_subscribe_map(self) -> int:
        """
        从 MP 同步订阅状态到本地 subscriptions 表

        Returns:
            同步成功的记录数
        """
        ok, data = await self.list_subscribes()
        if not ok or not isinstance(data, list):
            return 0

        from ..core.database import AsyncSessionLocal
        from ..models.subscription import Subscription
        from sqlalchemy import select

        count = 0
        async with AsyncSessionLocal() as db:
            for item in data:
                mp_id = item.get("id")
                if not mp_id:
                    continue
                result = await db.execute(
                    select(Subscription).where(Subscription.mp_id == mp_id)
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.state = item.get("state", sub.state)
                    sub.name = item.get("name", sub.name)
                    count += 1
            if count > 0:
                await db.commit()
        return count

    async def close(self):
        """关闭 HTTP 客户端（应用关闭时调用）"""
        if self._client:
            await self._client.aclose()
            self._client = None
