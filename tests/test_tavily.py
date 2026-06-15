import httpx
import pytest
from app.config import Settings
from app.tavily import TavilyClient
from app.schemas import Source


def _client(handler, **kw):
    kw.setdefault("tavily_max_results", 5)
    settings = Settings(tavily_api_key="tv-k", **kw)
    return TavilyClient(settings,
                        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.anyio
async def test_search_maps_results():
    def handler(req):
        body = req.read().decode()
        assert "tv-k" in body and "AURORA" in body
        assert req.url.path == "/search"
        return httpx.Response(200, json={"results": [
            {"title": "VnExpress", "url": "https://vn/1", "content": "won the title"},
            {"title": "Reuters", "url": "https://r/2", "content": "confirmed"},
        ]})
    out = await _client(handler).search("AURORA won")
    assert [s.url for s in out] == ["https://vn/1", "https://r/2"]
    assert out[0].title == "VnExpress" and out[0].snippet == "won the title"
    assert isinstance(out[0], Source)


@pytest.mark.anyio
async def test_search_no_api_key_returns_empty():
    settings = Settings(tavily_api_key="")
    # MockTransport raises if called, proving no request is made
    def handler(req):
        raise AssertionError("should not call API without key")
    c = TavilyClient(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await c.search("x") == []


@pytest.mark.anyio
async def test_search_non_200_returns_empty():
    out = await _client(lambda r: httpx.Response(500)).search("x")
    assert out == []


@pytest.mark.anyio
async def test_search_malformed_payload_returns_empty():
    out = await _client(lambda r: httpx.Response(200, text="not json")).search("x")
    assert out == []


@pytest.mark.anyio
async def test_search_respects_max_results():
    def handler(req):
        return httpx.Response(200, json={"results": [
            {"title": str(i), "url": f"https://u/{i}", "content": "c"} for i in range(10)]})
    out = await _client(handler, tavily_max_results=3).search("x")
    assert len(out) == 3
