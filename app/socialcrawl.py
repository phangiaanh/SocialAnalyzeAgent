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


_COMMENT_PATHS = {
    "tiktok": "/tiktok/post/comments",
    "reddit": "/reddit/post/comments",
    # threads has no comments endpoint
}


def _normalize(item: dict) -> Comment:
    # Response wraps each entry as {"comment": {...}}
    c = item.get("comment") or item
    text = c.get("text") or (c.get("content") or {}).get("text") or ""
    author = (c.get("author") or {}).get("username", "") or ""
    likes = int((c.get("engagement") or {}).get("likes") or c.get("likes") or 0)
    return Comment(id=str(c.get("id", "")), text=text, author=author, likes=likes)


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
            params={"url": url},
            headers={"x-api-key": self.s.socialcrawl_api_key, "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise SocialCrawlError(f"comments HTTP {resp.status_code}")
        env = resp.json()
        if not env.get("success", False):
            raise SocialCrawlError(f"api error: {env.get('error') or env}")
        items = (env.get("data") or {}).get("items") or []
        comments = sorted((_normalize(i) for i in items),
                          key=lambda c: c.likes, reverse=True)
        return comments[:limit]

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
