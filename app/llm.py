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

    async def complete_json(self, *, system: str, user: str,
                            schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        last = None
        for _ in range(self.s.llm_max_retries):
            resp = await self._http.post(
                f"{self.s.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                json={"model": self.s.llm_model, "messages": messages,
                      "temperature": temperature,
                      "response_format": {"type": "json_object"}},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
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
