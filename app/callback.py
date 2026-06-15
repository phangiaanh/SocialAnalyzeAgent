import json
import httpx
from app.schemas import CallbackPayload, Callback

# Confirm against the running gateway (spec open item #2). Telegram-channel send.
SEND_PATH = "/api/v1/message/text"


async def deliver(payload: CallbackPayload, callback: Callback,
                  http: httpx.AsyncClient | None = None, timeout: float = 15.0) -> None:
    owns = http is None
    http = http or httpx.AsyncClient(timeout=timeout)
    try:
        body = {
            "channel": "telegram",
            "chat_id": payload.delivery.chat_id,
            "reply_to_message_id": payload.delivery.message_id,
            "text": payload.report_text,
        }
        resp = await http.post(f"{callback.url}{SEND_PATH}",
                               headers={"Authorization": f"Bearer {callback.token}",
                                        "Content-Type": "application/json"},
                               content=json.dumps(body, ensure_ascii=False))
        resp.raise_for_status()
    finally:
        if owns:
            await http.aclose()
