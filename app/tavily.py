import httpx
from app.config import Settings
from app.schemas import Source


class TavilyError(Exception):
    pass


class TavilyClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.s = settings
        self._http = http or httpx.AsyncClient(timeout=settings.request_timeout)

    async def search(self, query: str) -> list[Source]:
        """Web sources for a claim. Best-effort: returns [] on any failure."""
        if not self.s.tavily_api_key:
            return []
        try:
            resp = await self._http.post(
                f"{self.s.tavily_base_url}/search",
                json={"api_key": self.s.tavily_api_key, "query": query,
                      "search_depth": self.s.tavily_search_depth,
                      "max_results": self.s.tavily_max_results},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        results = data.get("results") or []
        return [Source(title=r.get("title") or "", url=r.get("url") or "",
                       snippet=r.get("content") or "")
                for r in results[: self.s.tavily_max_results]]
