import json
import httpx
import pytest
from pydantic import BaseModel
from app.config import Settings
from app.llm import LLMClient, LLMError


class Out(BaseModel):
    n: int


def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return LLMClient(Settings(), http=http)


def _completion(content):
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.anyio
async def test_returns_validated_model():
    def handler(req):
        return httpx.Response(200, json=_completion('{"n": 7}'))
    out = await _client(handler).complete_json(system="s", user="u", schema=Out)
    assert out.n == 7


@pytest.mark.anyio
async def test_extracts_json_from_noise():
    def handler(req):
        return httpx.Response(200, json=_completion('sure!\n{"n": 3}\nthanks'))
    out = await _client(handler).complete_json(system="s", user="u", schema=Out)
    assert out.n == 3


@pytest.mark.anyio
async def test_retries_then_raises():
    calls = {"c": 0}
    def handler(req):
        calls["c"] += 1
        return httpx.Response(200, json=_completion("not json"))
    s = Settings(llm_max_retries=2)
    with pytest.raises(LLMError):
        await LLMClient(s, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
                        ).complete_json(system="s", user="u", schema=Out)
    assert calls["c"] == 2
