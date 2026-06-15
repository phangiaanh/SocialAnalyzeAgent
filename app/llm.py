import json
import re
import httpx
from pydantic import BaseModel, ValidationError
from app.config import Settings

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMError(Exception):
    pass


def _extract_json(text: str) -> str:
    m = _JSON_RE.search(text or "")
    if not m:
        raise ValueError("no JSON object in model output")
    return m.group(0)


class LLMClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.s = settings
        self._http = http or httpx.AsyncClient(timeout=settings.llm_timeout)

    async def _stream_chat(self, messages: list, temperature: float) -> str:
        chunks: list[str] = []
        async with self._http.stream(
            "POST",
            f"{self.s.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
            json={"model": self.s.llm_model, "messages": messages,
                  "temperature": temperature,
                  "response_format": {"type": "json_object"},
                  "stream": True},
            timeout=self.s.llm_timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                choices = data.get("choices")
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                chunks.append(delta.get("content") or "")
        return "".join(chunks)

    async def complete_json(self, *, system: str, user: str,
                            schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        last = None
        for _ in range(self.s.llm_max_retries):
            raw = await self._stream_chat(messages, temperature)
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValueError, ValidationError) as e:
                last = e
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user",
                     "content": "Trả về DUY NHẤT một JSON hợp lệ theo schema "
                                f"{json.dumps(schema.model_json_schema())}. Lỗi: {e}"},
                ]
        raise LLMError(f"LLM failed schema after {self.s.llm_max_retries} tries: {last}")
