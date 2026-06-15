import httpx
from pydantic import BaseModel
from app.config import Settings


class SocialCrawlError(Exception):
    pass


class Comment(BaseModel):
    id: str = ""
    text: str = ""
    author: str = ""
    likes: int = 0


# Confirm exact paths against the live SocialCrawl reference (spec open item #1).
_COMMENT_PATHS = {
    "tiktok": "/tiktok/comments",
    "reddit": "/reddit/comments",
    "threads": "/threads/comments",
}


def _normalize(item: dict) -> Comment:
    text = item.get("text") or (item.get("content") or {}).get("text", "") or ""
    author = (item.get("author") or {}).get("username", "") or ""
    return Comment(id=str(item.get("id", "")), text=text, author=author,
                   likes=int(item.get("likes") or 0))


class SocialCrawlClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.s = settings
        self._http = http or httpx.AsyncClient(timeout=settings.request_timeout)

    async def fetch_comments(self, platform: str, post_id: str, url: str,
                             limit: int = 200) -> list[Comment]:
        path = _COMMENT_PATHS.get(platform)
        if not path:
            return []
        resp = await self._http.get(
            f"{self.s.socialcrawl_base_url}{path}",
            params={"post_id": post_id, "url": url, "limit": limit},
            headers={"x-api-key": self.s.socialcrawl_api_key, "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise SocialCrawlError(f"comments HTTP {resp.status_code}")
        env = resp.json()
        if not env.get("success", False):
            raise SocialCrawlError(f"api error: {env.get('error') or env}")
        items = (env.get("data") or {}).get("items") or (env.get("data") or {}).get("results") or []
        return [_normalize(i) for i in items][:limit]

    async def cross_reference(self, query: str, limit: int = 10) -> list[str]:
        """Texts of other posts matching a claim, for fact-check signal."""
        resp = await self._http.get(
            f"{self.s.socialcrawl_base_url}/threads/search",
            params={"query": query},
            headers={"x-api-key": self.s.socialcrawl_api_key, "Accept": "application/json"},
        )
        if resp.status_code != 200:
            return []
        env = resp.json()
        items = (env.get("data") or {}).get("items") or []
        out = []
        for i in items[:limit]:
            p = i.get("post") or i
            out.append((p.get("content") or {}).get("text", "") or "")
        return [t for t in out if t]
