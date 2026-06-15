import json
import httpx
from app.schemas import CallbackPayload, Callback

TG_API_BASE = "https://api.telegram.org"


async def deliver(payload: CallbackPayload, callback: Callback,
                  http: httpx.AsyncClient | None = None, timeout: float = 15.0) -> None:
    owns = http is None
    http = http or httpx.AsyncClient(timeout=timeout)
    try:
        if callback.bot_token:
            body = {
                "chat_id": payload.delivery.chat_id,
                "text": payload.report_text,
                "reply_to_message_id": payload.delivery.message_id,
            }
            resp = await http.post(
                f"{TG_API_BASE}/bot{callback.bot_token}/sendMessage",
                headers={"Content-Type": "application/json"},
                content=json.dumps(body, ensure_ascii=False),
            )
            resp.raise_for_status()
        else:
            body = {
                "channel": "telegram",
                "chat_id": payload.delivery.chat_id,
                "reply_to_message_id": payload.delivery.message_id,
                "text": payload.report_text,
            }
            resp = await http.post(
                f"{callback.url}/api/v1/message/text",
                headers={"Authorization": f"Bearer {callback.token}",
                         "Content-Type": "application/json"},
                content=json.dumps(body, ensure_ascii=False),
            )
            resp.raise_for_status()
    finally:
        if owns:
            await http.aclose()
