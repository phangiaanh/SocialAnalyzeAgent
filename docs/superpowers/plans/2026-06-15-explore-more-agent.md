# Explore More Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "Explore More" agent — a FastAPI service that, for one trending post, runs fact-check + comment-attitude + reaction-prediction and delivers a Vietnamese report back to Telegram via OpenClaw; wire the carousel "📊 Analyze" button to trigger it.

**Architecture:** A standalone async FastAPI service on a dedicated runtime accepts `POST /analyze`, runs a hybrid pipeline (Python orchestrates; the qwen sidecar reasons via strict-JSON calls), and calls back into OpenClaw's public URL to deliver the report. The pipeline is mode-agnostic: a profiles registry maps `mode_id → AnalysisProfile` (with a `DEFAULT_PROFILE`) and runs an ordered, pluggable list of steps. OpenClaw's `engine.py` `cb_analyze` handler builds the trigger payload, POSTs it, and re-renders the card with the Analyze button flipped to "⏳ Đang phân tích…".

**Tech Stack:** Python 3.11, FastAPI, httpx, Pydantic v2, pytest + pytest-asyncio. The existing `OpenClawModeSkills` is stdlib-only Python (urllib) — Part B follows that.

**Spec:** `SocialAnalyzeAgent/docs/superpowers/specs/2026-06-15-explore-more-agent-design.md`

---

## File Structure

**Part A — `SocialAnalyzeAgent/` (new service)**

| File | Responsibility |
|---|---|
| `requirements.txt` | Pin deps |
| `Dockerfile` | Containerize the service |
| `app/__init__.py` | Package marker |
| `app/config.py` | `Settings` from env (LLM, SocialCrawl, OpenClaw callback) |
| `app/schemas.py` | Pydantic models: request, post/mode/delivery/callback, step results, callback payload |
| `app/llm.py` | `LLMClient.complete_json()` → qwen sidecar; strict-JSON + retries |
| `app/socialcrawl.py` | `fetch_comments()` per-platform comment adapters |
| `app/profiles/__init__.py` | `AnalysisProfile`, `DEFAULT_PROFILE`, `resolve_profile()` |
| `app/steps/base.py` | `AnalysisContext`, `STEP_REGISTRY`, `register` |
| `app/steps/factcheck.py` | Claim extraction + SocialCrawl cross-ref + comment signal |
| `app/steps/attitude.py` | Comment sentiment distribution + themes + quotes |
| `app/steps/predict.py` | 24–48h reaction + risks + momentum |
| `app/report.py` | Assemble Vietnamese single-message report |
| `app/callback.py` | Deliver result to OpenClaw public URL |
| `app/pipeline.py` | Orchestrator: resolve profile → comments → steps → report → callback |
| `app/jobs.py` | In-memory job registry + asyncio background runner |
| `app/main.py` | FastAPI: `POST /analyze`, `GET /health` |
| `tests/…` | One test module per `app/` module |

**Part B — `OpenClawModeSkills/` (trigger, existing repo)**

| File | Responsibility |
|---|---|
| `engine.py` (modify) | `cb_analyze` → build payload, POST trigger, return flipped card |
| `agent_trigger.py` (create) | stdlib `urllib` POST to the agent `/analyze` |
| `bot-handlers.runtime.ts` (modify) | Pass `--chat-id`/`--message-id` to `handle-callback` |
| `tests/test_agent_trigger.py` (create) | Trigger payload + flipped-card behavior |

---

## Conventions

- Run all Part A commands from `SocialAnalyzeAgent/`. Run all Part B commands from `OpenClawModeSkills/`.
- Part A tests: `pytest -q`. Async tests use `@pytest.mark.anyio` with the `anyio_backend` fixture (Task A1).
- Commit after every task with the shown message.

---

## PART A — SocialAnalyzeAgent service

### Task A1: Project scaffold

**Files:**
- Create: `SocialAnalyzeAgent/requirements.txt`
- Create: `SocialAnalyzeAgent/app/__init__.py`
- Create: `SocialAnalyzeAgent/tests/__init__.py`
- Create: `SocialAnalyzeAgent/tests/conftest.py`
- Create: `SocialAnalyzeAgent/pytest.ini`

- [ ] **Step 1: Write requirements.txt**

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
pydantic>=2.6
pydantic-settings>=2.2
pytest>=8.0
anyio>=4.3
```

> `anyio` ships a pytest plugin (entry point `anyio`), so `@pytest.mark.anyio` works once it's
> installed — no separate `pytest-anyio` package exists.

- [ ] **Step 2: Create package + test markers**

`app/__init__.py`: empty file.
`tests/__init__.py`: empty file.

`pytest.ini`:
```ini
[pytest]
addopts = -q
testpaths = tests
```

`tests/conftest.py`:
```python
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 3: Create + activate venv, install**

Run:
```bash
cd SocialAnalyzeAgent && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements.txt
```
Expected: installs without error.

- [ ] **Step 4: Verify pytest collects nothing yet**

Run: `pytest`
Expected: "no tests ran" (exit 5) — scaffold works.

- [ ] **Step 5: Commit**

```bash
printf '.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n' > .gitignore
git add requirements.txt app/__init__.py tests/__init__.py tests/conftest.py pytest.ini .gitignore
git commit -m "chore: scaffold SocialAnalyzeAgent FastAPI service"
```

---

### Task A2: Config from environment

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from app.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    s = Settings()
    assert s.llm_model == "qwen/qwen3-5-27b"
    assert s.llm_base_url.endswith("/v1")
    assert s.llm_max_retries == 3


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen/other")
    monkeypatch.setenv("SOCIALCRAWL_API_KEY", "k123")
    s = Settings()
    assert s.llm_model == "qwen/other"
    assert s.socialcrawl_api_key == "k123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: app.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    llm_base_url: str = "http://localhost:18080/v1"
    llm_model: str = "qwen/qwen3-5-27b"
    llm_api_key: str = "sidecar"
    llm_timeout: float = 60.0
    llm_max_retries: int = 3

    socialcrawl_api_key: str = ""
    socialcrawl_base_url: str = "https://www.socialcrawl.dev/v1"

    request_timeout: float = 15.0


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: env-driven Settings for SocialAnalyzeAgent"
```

---

### Task A3: Pydantic schemas

**Files:**
- Create: `app/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
from app.schemas import AnalyzeRequest, CallbackPayload

SAMPLE = {
    "job_id": "j1",
    "mode": {"id": "esports", "label": "Esports", "icon": "🎯"},
    "topic": {"id": "esports", "label": "Esports", "icon": "🎯"},
    "tick_id": "1781489278",
    "post": {
        "platform": "tiktok", "post_id": "p1", "url": "https://t/p1",
        "text": "hello", "author": "@a", "language": "en",
        "likes": 10, "views": 100, "comments": 5, "shares": 2,
        "score": 0.04, "age_hours": 1.5,
    },
    "delivery": {"chat_id": 717110884, "message_id": 1234},
    "callback": {"url": "https://oc.example", "token": "tok"},
}


def test_parse_analyze_request():
    req = AnalyzeRequest.model_validate(SAMPLE)
    assert req.post.platform == "tiktok"
    assert req.delivery.chat_id == 717110884
    assert req.mode.label == "Esports"


def test_callback_payload_roundtrip():
    p = CallbackPayload(job_id="j1", status="ok", report_text="hi",
                        delivery={"chat_id": 1, "message_id": 2})
    assert p.model_dump()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: app.schemas`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/schemas.py
from typing import Literal
from pydantic import BaseModel


class ModeRef(BaseModel):
    id: str
    label: str
    icon: str = "📌"


class Post(BaseModel):
    platform: str
    post_id: str
    url: str
    text: str = ""
    author: str = ""
    language: str = ""
    likes: int = 0
    views: int = 0
    comments: int = 0
    shares: int = 0
    score: float = 0.0
    age_hours: float = 0.0


class Delivery(BaseModel):
    chat_id: int
    message_id: int


class Callback(BaseModel):
    url: str
    token: str


class AnalyzeRequest(BaseModel):
    job_id: str
    mode: ModeRef
    topic: ModeRef
    tick_id: str
    post: Post
    delivery: Delivery
    callback: Callback


# ---- step result models ----
class Claim(BaseModel):
    text: str
    label: Literal["supported", "disputed", "unverifiable"]
    confidence: Literal["low", "medium", "high"]
    evidence: str = ""


class FactCheckResult(BaseModel):
    claims: list[Claim] = []
    overall_confidence: Literal["low", "medium", "high"] = "low"


class Theme(BaseModel):
    name: str
    count: int = 0


class AttitudeResult(BaseModel):
    sampled: int = 0
    positive_pct: int = 0
    neutral_pct: int = 0
    negative_pct: int = 0
    themes: list[Theme] = []
    quotes: list[str] = []


class Prediction(BaseModel):
    direction: Literal["up", "steady", "down"] = "steady"
    text: str = ""
    risk: str = ""
    momentum: Literal["rising", "steady", "fading"] = "steady"


class CallbackPayload(BaseModel):
    job_id: str
    status: Literal["ok", "error"]
    report_text: str
    delivery: Delivery
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py tests/test_schemas.py
git commit -m "feat: request/result/callback schemas"
```

---

### Task A4: LLM client (strict-JSON + retries)

**Files:**
- Create: `app/llm.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: app.llm`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/llm.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/llm.py tests/test_llm.py
git commit -m "feat: LLM client with strict-JSON validation and repair retries"
```

---

### Task A5: SocialCrawl comment client

> NOTE (spec open item #1): exact comment endpoint paths are confirmed at impl via the live
> SocialCrawl API reference. The paths below (`/{platform}/comments`) are the integration
> point; tests mock the HTTP layer so they are path-independent. When confirming, change only
> the `_COMMENT_PATHS` table.

**Files:**
- Create: `app/socialcrawl.py`
- Test: `tests/test_socialcrawl.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_socialcrawl.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_socialcrawl.py -v`
Expected: FAIL — `ModuleNotFoundError: app.socialcrawl`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/socialcrawl.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_socialcrawl.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/socialcrawl.py tests/test_socialcrawl.py
git commit -m "feat: SocialCrawl comment + cross-reference client"
```

---

### Task A6: Profiles registry (mode-agnostic core)

**Files:**
- Create: `app/profiles/__init__.py`
- Test: `tests/test_profiles.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profiles.py
from app.profiles import AnalysisProfile, DEFAULT_PROFILE, resolve_profile, PROFILES


def test_unknown_mode_uses_default():
    p = resolve_profile("does-not-exist")
    assert p is DEFAULT_PROFILE
    assert p.steps == ["factcheck", "attitude", "predict"]
    assert p.language == "vi"


def test_known_mode_uses_its_profile():
    PROFILES["finance"] = AnalysisProfile(domain_hint="tài chính",
                                          comment_sample_size=120)
    p = resolve_profile("finance")
    assert p.domain_hint == "tài chính"
    assert p.comment_sample_size == 120
    # still defaults the rest
    assert p.steps == ["factcheck", "attitude", "predict"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: app.profiles`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/profiles/__init__.py
from pydantic import BaseModel, Field


class AnalysisProfile(BaseModel):
    domain_hint: str = "chủ đề xã hội"
    comment_sample_size: int = 200
    steps: list[str] = Field(default_factory=lambda: ["factcheck", "attitude", "predict"])
    language: str = "vi"
    prompt_overrides: dict[str, str] = Field(default_factory=dict)


DEFAULT_PROFILE = AnalysisProfile()

# mode_id -> profile. New modes work with zero entries (fall back to DEFAULT_PROFILE).
PROFILES: dict[str, AnalysisProfile] = {
    "esports": AnalysisProfile(domain_hint="esports/gaming"),
}


def resolve_profile(mode_id: str) -> AnalysisProfile:
    return PROFILES.get(mode_id, DEFAULT_PROFILE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profiles.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/profiles/__init__.py tests/test_profiles.py
git commit -m "feat: mode-agnostic analysis profiles registry"
```

---

### Task A7: Step base + registry

**Files:**
- Create: `app/steps/__init__.py` (empty)
- Create: `app/steps/base.py`
- Test: `tests/test_steps_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_steps_base.py
import pytest
from app.steps.base import AnalysisContext, STEP_REGISTRY, register


def test_register_and_lookup():
    @register("dummy")
    async def _dummy(ctx, llm):
        return {"ok": True}
    assert "dummy" in STEP_REGISTRY
    assert STEP_REGISTRY["dummy"] is _dummy


def test_context_holds_state():
    ctx = AnalysisContext(request=None, profile=None, comments=[], results={})
    ctx.results["x"] = 1
    assert ctx.results["x"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_steps_base.py -v`
Expected: FAIL — `ModuleNotFoundError: app.steps.base`.

- [ ] **Step 3: Write minimal implementation**

`app/steps/__init__.py`: empty file.

```python
# app/steps/base.py
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class AnalysisContext:
    request: Any
    profile: Any
    comments: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    sc: Any = None  # SocialCrawlClient handle (steps may cross-reference)


Step = Callable[[AnalysisContext, Any], Awaitable[Any]]
STEP_REGISTRY: dict[str, Step] = {}


def register(name: str):
    def deco(fn: Step) -> Step:
        STEP_REGISTRY[name] = fn
        return fn
    return deco
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_steps_base.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/steps/__init__.py app/steps/base.py tests/test_steps_base.py
git commit -m "feat: step base context + registry"
```

---

### Task A8: Fact-check step

**Files:**
- Create: `app/steps/factcheck.py`
- Test: `tests/test_factcheck.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_factcheck.py
import pytest
from app.schemas import FactCheckResult
from app.steps.base import AnalysisContext
from app.steps import factcheck
from app.profiles import DEFAULT_PROFILE


class FakeLLM:
    def __init__(self, out): self.out = out; self.calls = []
    async def complete_json(self, *, system, user, schema, temperature=0.2):
        self.calls.append((system, user))
        return self.out


class FakeSC:
    def __init__(self): self.queries = []
    async def cross_reference(self, query, limit=10):
        self.queries.append(query)
        return ["bài liên quan A", "bài liên quan B"]


class Req:
    class post:  # noqa
        text = "AURORA won IEM Cologne"
        platform = "tiktok"


@pytest.mark.anyio
async def test_factcheck_returns_result_and_injects_domain():
    out = FactCheckResult(claims=[], overall_confidence="medium")
    llm = FakeLLM(out)
    ctx = AnalysisContext(request=Req(), profile=DEFAULT_PROFILE, comments=[], results={})
    res = await factcheck.run(ctx, llm)
    assert res.overall_confidence == "medium"
    assert DEFAULT_PROFILE.domain_hint in llm.calls[0][0]


@pytest.mark.anyio
async def test_factcheck_uses_cross_reference():
    llm = FakeLLM(FactCheckResult())
    sc = FakeSC()
    ctx = AnalysisContext(request=Req(), profile=DEFAULT_PROFILE, comments=[], results={}, sc=sc)
    await factcheck.run(ctx, llm)
    assert sc.queries == ["AURORA won IEM Cologne"]
    assert "bài liên quan A" in llm.calls[0][1]  # related posts fed into the prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_factcheck.py -v`
Expected: FAIL — `ModuleNotFoundError: app.steps.factcheck`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/steps/factcheck.py
from app.schemas import FactCheckResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn là trợ lý kiểm chứng thông tin cho lĩnh vực {domain}. "
    "Trích các tuyên bố có thể kiểm chứng trong bài đăng, đánh giá mỗi tuyên bố là "
    "supported/disputed/unverifiable dựa trên bằng chứng được cung cấp (bài liên quan và "
    "tín hiệu từ bình luận). Trả lời bằng tiếng Việt trong trường evidence."
)


def _render_user(ctx: AnalysisContext, related: list[str]) -> str:
    comments = "\n".join(f"- {c.text}" for c in ctx.comments[:50])
    refs = "\n".join(f"- {t}" for t in related)
    return (f"BÀI ĐĂNG:\n{ctx.request.post.text}\n\n"
            f"BÀI LIÊN QUAN (đối chiếu):\n{refs or '(không có)'}\n\n"
            f"BÌNH LUẬN (mẫu):\n{comments or '(không có)'}")


@register("factcheck")
async def run(ctx: AnalysisContext, llm) -> FactCheckResult:
    related: list[str] = []
    if ctx.sc is not None:
        try:
            related = await ctx.sc.cross_reference(ctx.request.post.text, limit=10)
        except Exception:  # degrade: cross-reference is best-effort
            related = []
    system = _SYSTEM.format(domain=ctx.profile.domain_hint)
    return await llm.complete_json(system=system, user=_render_user(ctx, related),
                                   schema=FactCheckResult)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_factcheck.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/steps/factcheck.py tests/test_factcheck.py
git commit -m "feat: fact-check step"
```

---

### Task A9: Attitude step

**Files:**
- Create: `app/steps/attitude.py`
- Test: `tests/test_attitude.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_attitude.py
import pytest
from app.schemas import AttitudeResult, Theme
from app.socialcrawl import Comment
from app.steps.base import AnalysisContext
from app.steps import attitude
from app.profiles import DEFAULT_PROFILE


class FakeLLM:
    def __init__(self, out): self.out = out; self.calls = []
    async def complete_json(self, *, system, user, schema, temperature=0.2):
        self.calls.append(user)
        return self.out


class Req:
    class post:  # noqa
        text = "x"


@pytest.mark.anyio
async def test_attitude_samples_and_returns():
    out = AttitudeResult(sampled=2, positive_pct=50, neutral_pct=25, negative_pct=25,
                         themes=[Theme(name="hype", count=2)], quotes=["nice"])
    llm = FakeLLM(out)
    ctx = AnalysisContext(request=Req(), profile=DEFAULT_PROFILE,
                          comments=[Comment(text="nice"), Comment(text="meh")], results={})
    res = await attitude.run(ctx, llm)
    assert res.positive_pct == 50
    assert "nice" in llm.calls[0]


@pytest.mark.anyio
async def test_attitude_no_comments_returns_zero():
    ctx = AnalysisContext(request=Req(), profile=DEFAULT_PROFILE, comments=[], results={})
    res = await attitude.run(ctx, FakeLLM(None))
    assert res.sampled == 0 and res.positive_pct == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_attitude.py -v`
Expected: FAIL — `ModuleNotFoundError: app.steps.attitude`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/steps/attitude.py
from app.schemas import AttitudeResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn phân tích thái độ bình luận cho lĩnh vực {domain}. Dựa trên mẫu bình luận, "
    "ước lượng phân bố cảm xúc (positive/neutral/negative, tổng 100), liệt kê chủ đề nổi bật "
    "kèm số lượng, và trích 2-3 câu tiêu biểu. Trả lời bằng tiếng Việt."
)


@register("attitude")
async def run(ctx: AnalysisContext, llm) -> AttitudeResult:
    sample = ctx.comments[: ctx.profile.comment_sample_size]
    if not sample:
        return AttitudeResult(sampled=0)
    body = "\n".join(f"- {c.text}" for c in sample if c.text)
    res = await llm.complete_json(
        system=_SYSTEM.format(domain=ctx.profile.domain_hint),
        user=f"BÌNH LUẬN ({len(sample)} mẫu):\n{body}",
        schema=AttitudeResult,
    )
    res.sampled = len(sample)
    return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_attitude.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/steps/attitude.py tests/test_attitude.py
git commit -m "feat: comment attitude step"
```

---

### Task A10: Prediction step

**Files:**
- Create: `app/steps/predict.py`
- Test: `tests/test_predict.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_predict.py
import pytest
from app.schemas import Prediction, AttitudeResult, FactCheckResult
from app.steps.base import AnalysisContext
from app.steps import predict
from app.profiles import DEFAULT_PROFILE


class FakeLLM:
    def __init__(self, out): self.out = out; self.calls = []
    async def complete_json(self, *, system, user, schema, temperature=0.2):
        self.calls.append(user)
        return self.out


class Post:
    text = "x"; score = 0.04; age_hours = 1.0; likes = 10; comments = 5; shares = 2
class Req:
    post = Post()


@pytest.mark.anyio
async def test_predict_uses_prior_results():
    out = Prediction(direction="up", text="tiếp tục trending", risk="tranh cãi",
                     momentum="rising")
    llm = FakeLLM(out)
    ctx = AnalysisContext(request=Req(), profile=DEFAULT_PROFILE, comments=[], results={
        "attitude": AttitudeResult(positive_pct=64),
        "factcheck": FactCheckResult(overall_confidence="medium"),
    })
    res = await predict.run(ctx, llm)
    assert res.direction == "up"
    assert "64" in llm.calls[0]  # attitude fed into prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_predict.py -v`
Expected: FAIL — `ModuleNotFoundError: app.steps.predict`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/steps/predict.py
from app.schemas import Prediction, AttitudeResult, FactCheckResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn dự đoán phản ứng cộng đồng trong 24–48 giờ tới cho lĩnh vực {domain}. "
    "Dựa trên quỹ đạo bài đăng (điểm, tuổi, tương tác), thái độ bình luận và kết quả kiểm "
    "chứng, đưa ra hướng (up/steady/down), mô tả ngắn, rủi ro chính và đà (rising/steady/"
    "fading). Trả lời bằng tiếng Việt."
)


@register("predict")
async def run(ctx: AnalysisContext, llm) -> Prediction:
    att: AttitudeResult | None = ctx.results.get("attitude")
    fc: FactCheckResult | None = ctx.results.get("factcheck")
    p = ctx.request.post
    user = (
        f"QUỸ ĐẠO: score={p.score} age_hours={p.age_hours} likes={p.likes} "
        f"comments={p.comments} shares={p.shares}\n"
        f"THÁI ĐỘ: positive={getattr(att, 'positive_pct', 'n/a')} "
        f"neutral={getattr(att, 'neutral_pct', 'n/a')} "
        f"negative={getattr(att, 'negative_pct', 'n/a')}\n"
        f"KIỂM CHỨNG: độ tin={getattr(fc, 'overall_confidence', 'n/a')} "
        f"số tuyên bố tranh cãi={sum(1 for c in getattr(fc, 'claims', []) if c.label=='disputed')}"
    )
    return await llm.complete_json(system=_SYSTEM.format(domain=ctx.profile.domain_hint),
                                   user=user, schema=Prediction)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_predict.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add app/steps/predict.py tests/test_predict.py
git commit -m "feat: reaction prediction step"
```

---

### Task A11: Vietnamese report formatter

**Files:**
- Create: `app/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
from app.schemas import (AnalyzeRequest, FactCheckResult, Claim, AttitudeResult, Theme,
                         Prediction)
from app.report import format_report
from app.profiles import DEFAULT_PROFILE
from tests.test_schemas import SAMPLE


def _req():
    return AnalyzeRequest.model_validate(SAMPLE)


def test_report_has_all_sections_and_fits():
    results = {
        "factcheck": FactCheckResult(
            claims=[Claim(text="AURORA won", label="disputed", confidence="medium",
                          evidence="3 bài đồng tình")], overall_confidence="medium"),
        "attitude": AttitudeResult(sampled=212, positive_pct=64, neutral_pct=21,
                                   negative_pct=15, themes=[Theme(name="hype", count=88)],
                                   quotes=["insane clutch"]),
        "predict": Prediction(direction="up", text="tiếp tục trending", risk="tranh cãi",
                              momentum="rising"),
    }
    text = format_report(_req(), results, DEFAULT_PROFILE)
    assert "KIỂM CHỨNG" in text
    assert "THÁI ĐỘ BÌNH LUẬN" in text
    assert "DỰ ĐOÁN PHẢN ỨNG" in text
    assert "64%" in text
    assert len(text) <= 4096


def test_report_degrades_missing_sections():
    text = format_report(_req(), {}, DEFAULT_PROFILE)
    assert "không thể phân tích" in text.lower()
    assert len(text) <= 4096
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: app.report`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/report.py
from app.schemas import AnalyzeRequest, FactCheckResult, AttitudeResult, Prediction

_PLATFORM = {"tiktok": "TikTok", "reddit": "Reddit", "threads": "Threads"}
_LABEL = {"supported": "✅ xác nhận", "disputed": "⚠️ tranh cãi", "unverifiable": "❓ chưa rõ"}
_ARROW = {"up": "↑", "steady": "→", "down": "↓"}
_NA = "  • không thể phân tích phần này"


def _factcheck(fc: FactCheckResult | None) -> str:
    if not fc:
        return f"✅ KIỂM CHỨNG\n{_NA}"
    lines = [f"✅ KIỂM CHỨNG  (độ tin: {fc.overall_confidence})"]
    if not fc.claims:
        lines.append("  • Không có tuyên bố cần kiểm chứng")
    for c in fc.claims[:5]:
        lines.append(f'• "{c.text}" — {_LABEL.get(c.label, c.label)}')
        if c.evidence:
            lines.append(f"  {c.evidence}")
    return "\n".join(lines)


def _attitude(a: AttitudeResult | None) -> str:
    if not a or a.sampled == 0:
        return f"💬 THÁI ĐỘ BÌNH LUẬN\n{_NA}"
    themes = ", ".join(f"{t.name} ({t.count})" for t in a.themes[:5])
    quotes = " · ".join(f'"{q}"' for q in a.quotes[:2])
    return ("\n".join([
        f"💬 THÁI ĐỘ BÌNH LUẬN  ({a.sampled} mẫu)",
        f"🟢 Tích cực {a.positive_pct}%  🟡 Trung lập {a.neutral_pct}%  🔴 Tiêu cực {a.negative_pct}%",
        f"Chủ đề nổi bật: {themes}" if themes else "",
        quotes,
    ])).strip()


def _predict(p: Prediction | None) -> str:
    if not p:
        return f"🔮 DỰ ĐOÁN PHẢN ỨNG (24–48h)\n{_NA}"
    out = [f"🔮 DỰ ĐOÁN PHẢN ỨNG (24–48h)", f"{_ARROW.get(p.direction, '→')} {p.text}"]
    if p.risk:
        out.append(f"Rủi ro: {p.risk}")
    out.append(f"🔥 đà: {p.momentum}")
    return "\n".join(out)


def format_report(req: AnalyzeRequest, results: dict, profile) -> str:
    platform = _PLATFORM.get(req.post.platform, req.post.platform.title())
    snippet = req.post.text.replace("\n", " ")
    if len(snippet) > 90:
        snippet = snippet[:89] + "…"
    header = f'🔍 Explore More — {req.mode.label} · {platform}\n"{snippet}"'
    body = "\n\n".join([
        "—" * 20,
        _factcheck(results.get("factcheck")),
        _attitude(results.get("attitude")),
        _predict(results.get("predict")),
    ])
    text = f"{header}\n{body}"
    return text[:4096]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/report.py tests/test_report.py
git commit -m "feat: Vietnamese single-message report formatter"
```

---

### Task A12: Callback delivery to OpenClaw

> NOTE (spec open item #2/#3): exact OpenClaw send route is confirmed at impl. `deliver()`
> POSTs to `{callback.url}{SEND_PATH}` with the gateway token; tests mock the transport so they
> are route-independent. When confirming, change only `SEND_PATH` and the body mapping.

**Files:**
- Create: `app/callback.py`
- Test: `tests/test_callback.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_callback.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_callback.py -v`
Expected: FAIL — `ModuleNotFoundError: app.callback`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/callback.py
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
                               headers={"Authorization": f"Bearer {callback.token}"},
                               json=body)
        resp.raise_for_status()
    finally:
        if owns:
            await http.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_callback.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add app/callback.py tests/test_callback.py
git commit -m "feat: deliver report back to OpenClaw via public URL"
```

---

### Task A13: Pipeline orchestrator

**Files:**
- Create: `app/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import pytest
from app.schemas import (AnalyzeRequest, FactCheckResult, AttitudeResult, Prediction,
                         CallbackPayload)
from app.socialcrawl import Comment
from app import pipeline
from tests.test_schemas import SAMPLE


class FakeSC:
    async def fetch_comments(self, platform, post_id, url, limit=200):
        return [Comment(text="nice"), Comment(text="bad")]
    async def cross_reference(self, query, limit=10):
        return ["other post"]


class FakeLLM:
    async def complete_json(self, *, system, user, schema, temperature=0.2):
        return schema()  # default-constructed result for each step


@pytest.mark.anyio
async def test_run_job_delivers_report(monkeypatch):
    captured = {}
    async def fake_deliver(payload, callback, **kw):
        captured["payload"] = payload
    monkeypatch.setattr(pipeline, "deliver", fake_deliver)

    req = AnalyzeRequest.model_validate(SAMPLE)
    await pipeline.run_job(req, sc=FakeSC(), llm=FakeLLM())

    p: CallbackPayload = captured["payload"]
    assert p.status == "ok"
    assert "THÁI ĐỘ BÌNH LUẬN" in p.report_text
    assert p.delivery.chat_id == req.delivery.chat_id


@pytest.mark.anyio
async def test_run_job_reports_error_on_failure(monkeypatch):
    captured = {}
    async def fake_deliver(payload, callback, **kw):
        captured["payload"] = payload
    monkeypatch.setattr(pipeline, "deliver", fake_deliver)

    class BoomSC(FakeSC):
        async def fetch_comments(self, *a, **k):
            raise RuntimeError("boom")

    # comment failure must NOT kill the job (degrades); force a deeper failure instead
    class BoomLLM:
        async def complete_json(self, **kw):
            raise RuntimeError("llm down")

    req = AnalyzeRequest.model_validate(SAMPLE)
    await pipeline.run_job(req, sc=BoomSC(), llm=BoomLLM())
    # comments degrade to empty, steps degrade individually -> still ok with N/A sections
    assert captured["payload"].status == "ok"
    assert "không thể phân tích" in captured["payload"].report_text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: app.pipeline`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/pipeline.py
import logging
from app.schemas import AnalyzeRequest, CallbackPayload
from app.profiles import resolve_profile
from app.steps.base import AnalysisContext, STEP_REGISTRY
from app.report import format_report
from app.callback import deliver
# ensure steps self-register
from app.steps import factcheck, attitude, predict  # noqa: F401

log = logging.getLogger("pipeline")


async def _gather_comments(sc, req, profile):
    try:
        return await sc.fetch_comments(req.post.platform, req.post.post_id,
                                       req.post.url, limit=profile.comment_sample_size)
    except Exception as e:  # degrade: no comments
        log.warning("comment fetch failed: %s", e)
        return []


async def run_job(req: AnalyzeRequest, *, sc, llm) -> None:
    profile = resolve_profile(req.mode.id)
    comments = await _gather_comments(sc, req, profile)
    ctx = AnalysisContext(request=req, profile=profile, comments=comments, results={}, sc=sc)
    for name in profile.steps:
        step = STEP_REGISTRY.get(name)
        if not step:
            continue
        try:
            ctx.results[name] = await step(ctx, llm)
        except Exception as e:  # degrade: missing section
            log.warning("step %s failed: %s", name, e)
    report = format_report(req, ctx.results, profile)
    payload = CallbackPayload(job_id=req.job_id, status="ok", report_text=report,
                              delivery=req.delivery)
    await deliver(payload, req.callback)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator with graceful degradation"
```

---

### Task A14: Job registry + background runner

**Files:**
- Create: `app/jobs.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jobs.py
import asyncio
import pytest
from app.jobs import JobRegistry


@pytest.mark.anyio
async def test_dedup_and_completion():
    reg = JobRegistry()
    ran = []

    async def work():
        await asyncio.sleep(0.01)
        ran.append(1)

    assert reg.start("j1", work()) is True
    # duplicate while active -> rejected (close the coroutine we won't run)
    dup = work()
    assert reg.start("j1", dup) is False
    dup.close()
    await reg.wait_all()
    assert ran == [1]
    assert reg.is_active("j1") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: app.jobs`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/jobs.py
import asyncio
import logging

log = logging.getLogger("jobs")


class JobRegistry:
    def __init__(self):
        self._active: dict[str, asyncio.Task] = {}

    def is_active(self, job_id: str) -> bool:
        return job_id in self._active

    def start(self, job_id: str, coro) -> bool:
        if job_id in self._active:
            return False
        task = asyncio.create_task(self._wrap(job_id, coro))
        self._active[job_id] = task
        return True

    async def _wrap(self, job_id: str, coro):
        try:
            await coro
        except Exception as e:  # never crash the loop
            log.exception("job %s failed: %s", job_id, e)
        finally:
            self._active.pop(job_id, None)

    async def wait_all(self):
        while self._active:
            await asyncio.gather(*list(self._active.values()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_jobs.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add app/jobs.py tests/test_jobs.py
git commit -m "feat: in-memory job registry with dedup"
```

---

### Task A15: FastAPI app

**Files:**
- Create: `app/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
import httpx
import pytest
from app import main, pipeline
from tests.test_schemas import SAMPLE


@pytest.mark.anyio
async def test_health():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_analyze_enqueues(monkeypatch):
    seen = {}
    async def fake_run_job(req, **kw):
        seen["job"] = req.job_id
    monkeypatch.setattr(main, "run_job", fake_run_job)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/analyze", json=SAMPLE)
    assert r.status_code == 202
    assert r.json()["job_id"] == "j1"
    await main.registry.wait_all()
    assert seen["job"] == "j1"


@pytest.mark.anyio
async def test_analyze_dedup(monkeypatch):
    async def slow_run_job(req, **kw):
        import asyncio; await asyncio.sleep(0.05)
    monkeypatch.setattr(main, "run_job", slow_run_job)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r1 = await c.post("/analyze", json={**SAMPLE, "job_id": "dup"})
        r2 = await c.post("/analyze", json={**SAMPLE, "job_id": "dup"})
    assert r1.status_code == 202 and r2.status_code == 409
    await main.registry.wait_all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: app.main`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/main.py
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.schemas import AnalyzeRequest
from app.jobs import JobRegistry
from app.pipeline import run_job
from app.llm import LLMClient
from app.socialcrawl import SocialCrawlClient

app = FastAPI(title="SocialAnalyzeAgent")
registry = JobRegistry()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    async def job():
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.request_timeout) as http:
            sc = SocialCrawlClient(settings, http=http)
            llm = LLMClient(settings, http=http)
            await run_job(req, sc=sc, llm=llm)

    if not registry.start(req.job_id, job()):
        return JSONResponse(status_code=409, content={"job_id": req.job_id,
                                                      "status": "already_running"})
    return JSONResponse(status_code=202, content={"job_id": req.job_id, "status": "accepted"})
```

> Note: `run_job` is imported into `main` so tests can monkeypatch `main.run_job`. The inner
> `job()` calls the module-level name, so patching `main.run_job` takes effect.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: FastAPI /analyze + /health endpoints"
```

---

### Task A16: Dockerfile + README + run docs

**Files:**
- Create: `SocialAnalyzeAgent/Dockerfile`
- Modify: `SocialAnalyzeAgent/README.md`

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write README**

```markdown
# SocialAnalyzeAgent

"Explore More" agent: for one trending post, runs fact-check + comment-attitude +
reaction-prediction and delivers a Vietnamese report back to Telegram via OpenClaw.

## Run

    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000

## Env

| Var | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:18080/v1` | qwen sidecar (OpenAI-compatible) |
| `LLM_MODEL` | `qwen/qwen3-5-27b` | model name |
| `LLM_API_KEY` | `sidecar` | sidecar token (usually ignored) |
| `LLM_MAX_RETRIES` | `3` | strict-JSON repair attempts |
| `SOCIALCRAWL_API_KEY` | — | SocialCrawl `x-api-key` |

## Test

    pytest

## API

`POST /analyze` (202 + job_id) — see `app/schemas.py:AnalyzeRequest`. `GET /health`.
```

- [ ] **Step 3: Verify build (optional if docker available)**

Run: `docker build -t socialanalyze . ` (skip if docker unavailable)
Expected: image builds.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile README.md
git commit -m "docs: Dockerfile + README for SocialAnalyzeAgent"
```

---

## PART B — OpenClaw trigger wiring

> Run from `OpenClawModeSkills/`. This repo is stdlib-only Python; do not add deps.

### Task B1: Agent trigger client (stdlib)

**Files:**
- Create: `OpenClawModeSkills/agent_trigger.py`
- Test: `OpenClawModeSkills/tests/test_agent_trigger.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_trigger.py
import json
import agent_trigger


def test_build_payload_shape():
    snap_post = {"platform": "tiktok", "post_id": "p1", "url": "u", "text": "t",
                 "author": "@a", "language": "en", "likes": 1, "views": 2,
                 "comments": 3, "shares": 4, "score": 0.04, "age_hours": 1.0}
    payload = agent_trigger.build_payload(
        job_id="j1",
        mode={"id": "esports", "label": "Esports", "icon": "🎯"},
        topic={"id": "esports", "label": "Esports", "icon": "🎯"},
        tick_id="123", post=snap_post, chat_id=7, message_id=9,
        callback_url="https://oc", callback_token="TOK", agent_url="https://agent/analyze")
    assert payload["job_id"] == "j1"
    assert payload["post"]["platform"] == "tiktok"
    assert payload["delivery"] == {"chat_id": 7, "message_id": 9}
    assert payload["callback"] == {"url": "https://oc", "token": "TOK"}


def test_post_uses_urlopen(monkeypatch):
    sent = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"status":"accepted"}'
    def fake_urlopen(req, timeout=0, context=None):
        sent["url"] = req.full_url
        sent["data"] = json.loads(req.data.decode())
        return FakeResp()
    monkeypatch.setattr(agent_trigger.urllib.request, "urlopen", fake_urlopen)
    out = agent_trigger.post_job("https://agent/analyze", {"job_id": "j1"})
    assert sent["url"] == "https://agent/analyze"
    assert out["status"] == "accepted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_trigger.py -v`
Expected: FAIL — `ModuleNotFoundError: agent_trigger`.

- [ ] **Step 3: Write minimal implementation**

```python
# agent_trigger.py
"""Fire-and-202 trigger to the SocialAnalyzeAgent /analyze endpoint (stdlib only)."""
import json
import os
import ssl
import urllib.error
import urllib.request


def agent_url() -> str:
    return os.environ.get("EPAPHRAS_AGENT_URL", "")


def callback_url() -> str:
    return os.environ.get("OPENCLAW_PUBLIC_URL", "")


def callback_token() -> str:
    return os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")


def build_payload(*, job_id, mode, topic, tick_id, post, chat_id, message_id,
                  callback_url, callback_token, agent_url):
    return {
        "job_id": job_id,
        "mode": mode,
        "topic": topic,
        "tick_id": tick_id,
        "post": {
            "platform": post.get("platform", ""), "post_id": post.get("post_id", ""),
            "url": post.get("url", ""), "text": post.get("text", ""),
            "author": post.get("author", ""), "language": post.get("language", ""),
            "likes": post.get("likes", 0), "views": post.get("views", 0),
            "comments": post.get("comments", 0), "shares": post.get("shares", 0),
            "score": post.get("score", 0.0), "age_hours": post.get("age_hours", 0.0),
        },
        "delivery": {"chat_id": chat_id, "message_id": message_id},
        "callback": {"url": callback_url, "token": callback_token},
    }


def post_job(url: str, payload: dict, timeout: int = 8) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"status": "trigger_failed", "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_trigger.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add agent_trigger.py tests/test_agent_trigger.py
git commit -m "feat: stdlib trigger client for SocialAnalyzeAgent"
```

---

### Task B2: Wire `cb_analyze` to trigger + flip button

**Files:**
- Modify: `OpenClawModeSkills/engine.py` (the `cb_analyze` branch, currently ~line 710-717)
- Modify: `OpenClawModeSkills/engine.py` (`handle_callback` signature + `main()` arg parsing)
- Test: `OpenClawModeSkills/tests/test_engine.py` (add cases)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py`:

```python
def test_cb_analyze_flips_button_and_triggers(monkeypatch, cfg):
    import engine, agent_trigger, json as _json
    data = engine.load_config(cfg)
    snap = {
        "tick_id": "123",
        "topic_order": ["esports"],
        "topic_meta": {"esports": {"label": "Esports", "icon": "🎯"}},
        "topics": {"esports": [{
            "platform": "tiktok", "rank": 1, "post_id": "p1", "url": "https://t/p1",
            "text": "hi", "author": "@a", "language": "en", "likes": 1, "views": 2,
            "comments": 3, "shares": 4, "score": 0.04, "age_hours": 1.0,
        }]},
    }
    monkeypatch.setattr(engine, "load_snapshot", lambda: snap)
    sent = {}
    monkeypatch.setattr(agent_trigger, "agent_url", lambda: "https://agent/analyze")
    monkeypatch.setattr(agent_trigger, "post_job",
                        lambda url, payload, timeout=8: sent.update(payload) or {"status": "accepted"})

    out = engine.handle_callback(data, "cb_analyze:123:esports:0",
                                 chat_id=7, message_id=9)
    # button flipped: an inline button now says processing + is inert
    flat = [b for row in out["buttons"] for b in row]
    assert any("Đang phân tích" in b["text"] for b in flat)
    assert any(b.get("callback_data") == "cb_noop" for b in flat)
    # trigger fired with correct delivery
    assert sent["delivery"] == {"chat_id": 7, "message_id": 9}
    assert sent["post"]["post_id"] == "p1"


def test_cb_analyze_stale_snapshot(monkeypatch, cfg):
    import engine
    data = engine.load_config(cfg)
    monkeypatch.setattr(engine, "load_snapshot", lambda: {"tick_id": "999"})
    out = engine.handle_callback(data, "cb_analyze:123:esports:0", chat_id=7, message_id=9)
    assert "hết hạn" in out["text"].lower() or "expired" in out["text"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine.py::test_cb_analyze_flips_button_and_triggers -v`
Expected: FAIL — `handle_callback() got an unexpected keyword argument 'chat_id'`.

- [ ] **Step 3: Update `handle_callback` signature**

In `engine.py`, change the definition (currently `def handle_callback(data, cb):`) to:

```python
def handle_callback(data, cb, chat_id=None, message_id=None):
```

- [ ] **Step 4: Replace the `cb_analyze` branch**

In `engine.py`, replace the existing `if verb == "cb_analyze":` block (the one returning
`{"toast": "📊 Analyze coming soon"}`) with:

```python
    if verb == "cb_analyze":
        import uuid
        import agent_trigger
        snap = load_snapshot()
        parts = arg.split(":", 2)
        tick_id_cb = parts[0] if parts else ""
        if snap is None or snap.get("tick_id") != tick_id_cb:
            return {"text": "⏳ Snapshot đã hết hạn — xem bài mới nhất.",
                    "buttons": [], "inline_keyboard": []}
        topic_id = parts[1] if len(parts) > 1 else ""
        try:
            idx = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, TypeError):
            idx = 0
        posts = snap.get("topics", {}).get(topic_id, [])
        if idx >= len(posts):
            return {"text": "⏳ Snapshot đã hết hạn — xem bài mới nhất.",
                    "buttons": [], "inline_keyboard": []}
        post = posts[idx]
        meta = snap.get("topic_meta", {}).get(topic_id, {"label": topic_id, "icon": DEFAULT_ICON})
        mode_ref = {"id": topic_id, "label": meta.get("label", topic_id),
                    "icon": meta.get("icon", DEFAULT_ICON)}
        url = agent_trigger.agent_url()
        if url and chat_id is not None and message_id is not None:
            payload = agent_trigger.build_payload(
                job_id=str(uuid.uuid4()), mode=mode_ref, topic=mode_ref,
                tick_id=tick_id_cb, post=post, chat_id=chat_id, message_id=message_id,
                callback_url=agent_trigger.callback_url(),
                callback_token=agent_trigger.callback_token(), agent_url=url)
            agent_trigger.post_job(url, payload)
        # re-render the card with the Analyze button flipped + inert
        card = build_carousel_card(snap, topic_id, idx)
        for row in card.get("buttons", []):
            for btn in row:
                if str(btn.get("callback_data", "")).startswith("cb_analyze:"):
                    btn["text"] = "⏳ Đang phân tích…"
                    btn["callback_data"] = "cb_noop"
        card["inline_keyboard"] = card["buttons"]
        return card
```

- [ ] **Step 5: Pass `chat_id`/`message_id` from `main()`**

In `engine.py` `main()`, find the `handle-callback` branch (currently
`out = handle_callback(data, args.arg)`) and replace with:

```python
            out = handle_callback(data, args.arg,
                                  chat_id=args.chat_id, message_id=args.message_id)
```

Then add these arguments near the other `parser.add_argument(...)` calls:

```python
    parser.add_argument("--chat-id", type=int, dest="chat_id", default=None)
    parser.add_argument("--message-id", type=int, dest="message_id", default=None)
```

- [ ] **Step 6: Run the new tests + full suite**

Run: `pytest tests/test_engine.py -k cb_analyze -v && pytest`
Expected: new tests PASS; full suite PASS.

- [ ] **Step 7: Commit**

```bash
git add engine.py tests/test_engine.py
git commit -m "feat: cb_analyze triggers Explore agent and flips button to processing"
```

---

### Task B3: Pass message context from the gateway patch

> The in-process gateway patch (`bot-handlers.runtime.ts`, the `_EPAPHRAS_CB_INTERCEPT_TS`
> block) currently calls `engine.py handle-callback <data>`. It must also pass the chat + message
> ids so `cb_analyze` can build the delivery target.

**Files:**
- Modify: `OpenClawModeSkills` patch script that injects `_EPAPHRAS_CB_INTERCEPT_TS`
  (the `full_patch_v2.py` used during deploy) **and** the live
  `/app/extensions/telegram/src/bot-handlers.runtime.ts` block.

- [ ] **Step 1: Locate the spawn call in the patch**

The intercept currently runs:
```ts
const _epProc = _epCp.spawnSync("python3", [
  "/root/.openclaw/workspace/skills/OpenClawModeSkills/engine.py",
  "handle-callback", data
], { encoding: "utf-8", timeout: 10000 });
```

- [ ] **Step 2: Add chat + message ids to the args**

Replace the args array with:
```ts
const _epProc = _epCp.spawnSync("python3", [
  "/root/.openclaw/workspace/skills/OpenClawModeSkills/engine.py",
  "handle-callback", data,
  "--chat-id", String(callbackMessage.chat.id),
  "--message-id", String(callbackMessage.message_id)
], { encoding: "utf-8", timeout: 10000 });
```

- [ ] **Step 3: Update the deploy patch script**

Apply the same change in the patch generator (`full_patch_v2.py`) so a container restart
reproduces it. Update the embedded TS string to include the two extra args.

- [ ] **Step 4: Re-apply patch + restart gateway (manual deploy step)**

On the pod:
```bash
python3 /tmp/full_patch_v2.py
kill 17 2>/dev/null   # current openclaw-gateway PID; start.sh keeps the container alive
openclaw gateway --allow-unconfigured > /tmp/gateway.log 2>&1 &
```
Expected: gateway restarts; `bot-handlers.runtime.ts` recompiles with the new args.

- [ ] **Step 5: Smoke-test on the pod**

```bash
python3 /root/.openclaw/workspace/skills/OpenClawModeSkills/engine.py \
  handle-callback "cb_analyze:<live_tick>:esports:0" --chat-id 717110884 --message-id 1
```
Expected: JSON with a `⏳ Đang phân tích…` button and `cb_noop` callback_data (the trigger
POST will fail until `EPAPHRAS_AGENT_URL` is set — that is expected at this stage).

- [ ] **Step 6: Commit the patch generator change**

```bash
git add full_patch_v2.py
git commit -m "feat: pass chat/message ids to engine for cb_analyze trigger"
```

---

## Deployment notes (post-implementation)

1. Deploy `SocialAnalyzeAgent` to the GreenNode runtime; note its public `/analyze` URL.
2. On the OpenClaw pod set env for the gateway process: `EPAPHRAS_AGENT_URL=<public>/analyze`,
   `OPENCLAW_PUBLIC_URL=https://openclaw-111735-epaphras.agentbase-runtime.aiplatform.vngcloud.vn`,
   `OPENCLAW_GATEWAY_TOKEN=<token>` (already present).
3. Confirm spec open items against live systems: SocialCrawl comment paths (`_COMMENT_PATHS`),
   OpenClaw send route (`SEND_PATH` + body), and whether `editMessageReplyMarkup` is reachable
   for the optional "✅ Done" finalize.
4. End-to-end: tap "📊 Analyze" on a live card → button flips → report arrives as a reply.
