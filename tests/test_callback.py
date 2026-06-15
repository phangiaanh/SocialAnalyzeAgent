import httpx
import pytest
from app.schemas import CallbackPayload, Callback
from app.callback import deliver


@pytest.mark.anyio
async def test_deliver_posts_with_token():
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"ok": True})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = CallbackPayload(job_id="j1", status="ok", report_text="hello",
                              delivery={"chat_id": 7, "message_id": 9})
    cb = Callback(url="https://oc.example", token="TOK")
    await deliver(payload, cb, http=http)
    assert seen["url"].startswith("https://oc.example")
    assert seen["auth"] == "Bearer TOK"
    assert "hello" in seen["body"] and "\"chat_id\": 7" in seen["body"]
