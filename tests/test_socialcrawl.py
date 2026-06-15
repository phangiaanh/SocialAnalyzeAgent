import httpx
import pytest
from app.config import Settings
from app.socialcrawl import SocialCrawlClient, Comment


def _client(handler):
    return SocialCrawlClient(Settings(socialcrawl_api_key="k"),
                             http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.anyio
async def test_fetch_comments_normalizes():
    def handler(req):
        assert req.headers["x-api-key"] == "k"
        return httpx.Response(200, json={"success": True, "data": {"items": [
            {"id": "c1", "text": "great", "author": {"username": "u1"}, "likes": 4},
            {"id": "c2", "content": {"text": "bad"}, "author": {"username": "u2"}},
        ]}})
    out = await _client(handler).fetch_comments("tiktok", "p1", "https://t/p1", limit=10)
    assert [c.text for c in out] == ["great", "bad"]
    assert out[0].likes == 4 and out[0].author == "u1"


@pytest.mark.anyio
async def test_fetch_comments_unsupported_platform_returns_empty():
    out = await _client(lambda r: httpx.Response(200)).fetch_comments(
        "myspace", "p1", "u", limit=10)
    assert out == []
