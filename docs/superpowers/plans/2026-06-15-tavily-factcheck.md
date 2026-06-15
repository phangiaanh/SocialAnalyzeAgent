# Tavily-grounded Fact-Checking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unreliable social-post-based fact-check with a two-pass, Tavily-grounded verification that attaches real cited web sources to each claim, and fix arbitrary comment sampling.

**Architecture:** The `factcheck` step runs two LLM passes around a web search: Pass 1 extracts checkable claims, then each of the top N claims is searched via a new `TavilyClient`, then Pass 2 labels each claim against its web sources. Crucially, the **real `Source` objects from search are attached to claims deterministically by the step** (not echoed by the LLM), so URLs can't be hallucinated; the LLM only returns per-claim verdicts (label/confidence/evidence). A claim with zero sources is forced to `unverifiable`.

**Tech Stack:** Python 3.11, FastAPI, httpx (async, `MockTransport` in tests), pydantic v2, pytest + anyio (asyncio backend, `@pytest.mark.anyio`).

> **Spec:** `docs/superpowers/specs/2026-06-15-tavily-factcheck-design.md`

> **Design refinement vs. spec:** The spec said Pass 2 would "echo back the sources used." During planning this was changed to **deterministic attachment** — the step zips each claim with its actual searched `Source` objects, and the LLM returns only verdicts. This removes any chance of the model fabricating or mangling URLs. The output schema (`Claim.sources`) is unchanged.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `app/config.py` | Settings incl. Tavily/factcheck knobs | Modify |
| `app/schemas.py` | Add `Source`, `Claim.sources`, `ClaimExtraction`, `ClaimVerdict`, `VerificationResult` | Modify |
| `app/tavily.py` | Tavily search client → `list[Source]`, best-effort | Create |
| `app/steps/base.py` | `AnalysisContext` gains `tv` + `settings` | Modify |
| `app/steps/factcheck.py` | Two-pass verification | Rewrite |
| `app/report.py` | Render claim sources as references | Modify |
| `app/pipeline.py` | Thread `tv` + `settings` into context | Modify |
| `app/main.py` | Construct `TavilyClient`, pass to `run_job` | Modify |
| `app/socialcrawl.py` | Sort comments by likes before truncating | Modify |
| `tests/test_tavily.py` | Tavily client tests | Create |
| `tests/test_factcheck.py` | Two-pass step tests | Rewrite |
| `tests/{test_config,test_schemas,test_report,test_socialcrawl}.py` | Extend | Modify |

---

## Task 1: Config — add Tavily & factcheck settings

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_tavily_defaults(monkeypatch):
    monkeypatch.delenv("TAVILY_SEARCH_DEPTH", raising=False)
    s = Settings()
    assert s.tavily_api_key == ""
    assert s.tavily_base_url == "https://api.tavily.com"
    assert s.tavily_search_depth == "basic"
    assert s.tavily_max_results == 5
    assert s.factcheck_max_claims == 5


def test_tavily_env_override(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-123")
    monkeypatch.setenv("FACTCHECK_MAX_CLAIMS", "3")
    s = Settings()
    assert s.tavily_api_key == "tv-123"
    assert s.factcheck_max_claims == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'tavily_api_key'`

- [ ] **Step 3: Add the settings**

In `app/config.py`, inside `class Settings`, after the `socialcrawl_base_url` line:

```python
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "basic"
    tavily_max_results: int = 5
    factcheck_max_claims: int = 5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add Tavily and factcheck settings"
```

---

## Task 2: Schemas — sources & two-pass models

**Files:**
- Modify: `app/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schemas.py`:

```python
def test_claim_has_sources_default_empty():
    from app.schemas import Claim, Source
    c = Claim(text="x", label="supported", confidence="high")
    assert c.sources == []
    c2 = Claim(text="y", label="disputed", confidence="low",
               sources=[Source(title="T", url="https://u", snippet="s")])
    assert c2.sources[0].url == "https://u"


def test_two_pass_models():
    from app.schemas import ClaimExtraction, ClaimVerdict, VerificationResult
    assert ClaimExtraction().claims == []
    assert ClaimExtraction(claims=["a", "b"]).claims == ["a", "b"]
    v = VerificationResult(verdicts=[ClaimVerdict(label="supported",
                                                  confidence="high", evidence="e")],
                           overall_confidence="high")
    assert v.verdicts[0].label == "supported"
    assert v.overall_confidence == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'Source'`

- [ ] **Step 3: Add the models**

In `app/schemas.py`, in the `# ---- step result models ----` section, **above** `class Claim`:

```python
class Source(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
```

Modify `class Claim` to add a `sources` field:

```python
class Claim(BaseModel):
    text: str
    label: Literal["supported", "disputed", "unverifiable"]
    confidence: Literal["low", "medium", "high"]
    evidence: str = ""
    sources: list[Source] = []
```

Then, **below** `class FactCheckResult`, add the two-pass models:

```python
class ClaimExtraction(BaseModel):
    claims: list[str] = []


class ClaimVerdict(BaseModel):
    label: Literal["supported", "disputed", "unverifiable"] = "unverifiable"
    confidence: Literal["low", "medium", "high"] = "low"
    evidence: str = ""


class VerificationResult(BaseModel):
    verdicts: list[ClaimVerdict] = []
    overall_confidence: Literal["low", "medium", "high"] = "low"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py tests/test_schemas.py
git commit -m "feat: add Source and two-pass factcheck schemas"
```

---

## Task 3: TavilyClient

**Files:**
- Create: `app/tavily.py`
- Test: `tests/test_tavily.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tavily.py`:

```python
import httpx
import pytest
from app.config import Settings
from app.tavily import TavilyClient
from app.schemas import Source


def _client(handler, **kw):
    settings = Settings(tavily_api_key="tv-k", tavily_max_results=5, **kw)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tavily.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tavily'`

- [ ] **Step 3: Implement the client**

Create `app/tavily.py`:

```python
import httpx
from app.config import Settings
from app.schemas import Source


class TavilyError(Exception):
    pass


class TavilyClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.s = settings
        self._http = http or httpx.AsyncClient(timeout=settings.request_timeout)

    async def search(self, query: str) -> list[Source]:
        """Web sources for a claim. Best-effort: returns [] on any failure."""
        if not self.s.tavily_api_key:
            return []
        try:
            resp = await self._http.post(
                f"{self.s.tavily_base_url}/search",
                json={"api_key": self.s.tavily_api_key, "query": query,
                      "search_depth": self.s.tavily_search_depth,
                      "max_results": self.s.tavily_max_results},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        results = data.get("results") or []
        return [Source(title=r.get("title") or "", url=r.get("url") or "",
                       snippet=r.get("content") or "")
                for r in results[: self.s.tavily_max_results]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tavily.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tavily.py tests/test_tavily.py
git commit -m "feat: add TavilyClient web-search client"
```

---

## Task 4: Context wiring — `tv` + `settings` on `AnalysisContext`

**Files:**
- Modify: `app/steps/base.py`
- Test: `tests/test_steps_base.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_steps_base.py`:

```python
def test_context_holds_tv_and_settings():
    ctx = AnalysisContext(request=None, profile=None, comments=[], results={},
                          tv="TVCLIENT", settings="SETTINGS")
    assert ctx.tv == "TVCLIENT"
    assert ctx.settings == "SETTINGS"


def test_context_tv_and_settings_default_none():
    ctx = AnalysisContext(request=None, profile=None, comments=[], results={})
    assert ctx.tv is None
    assert ctx.settings is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_steps_base.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'tv'`

- [ ] **Step 3: Add the fields**

In `app/steps/base.py`, in the `AnalysisContext` dataclass, after the `sc` field:

```python
    tv: Any = None        # TavilyClient handle (factcheck web search)
    settings: Any = None  # Settings handle (env-configured knobs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_steps_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/steps/base.py tests/test_steps_base.py
git commit -m "feat: add tv and settings to AnalysisContext"
```

---

## Task 5: Two-pass `factcheck` step

**Files:**
- Rewrite: `app/steps/factcheck.py`
- Rewrite: `tests/test_factcheck.py`

- [ ] **Step 1: Write the failing tests (full rewrite)**

Replace the entire contents of `tests/test_factcheck.py` with:

```python
import pytest
from app.schemas import (FactCheckResult, ClaimExtraction, ClaimVerdict,
                         VerificationResult, Source)
from app.steps.base import AnalysisContext
from app.steps import factcheck
from app.profiles import DEFAULT_PROFILE


class FakeLLM:
    """Returns a queued result per schema type; records calls."""
    def __init__(self, by_schema):
        self.by_schema = by_schema
        self.calls = []

    async def complete_json(self, *, system, user, schema, temperature=0.2):
        self.calls.append((schema, system, user))
        return self.by_schema[schema]


class FakeTavily:
    def __init__(self, sources):
        self.sources = sources
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return self.sources


class FakeSettings:
    factcheck_max_claims = 5


class Req:
    class post:  # noqa
        text = "AURORA won IEM Cologne 2026"
        platform = "tiktok"


def _ctx(llm_unused=None, tv=None, settings=None):
    return AnalysisContext(request=Req(), profile=DEFAULT_PROFILE, comments=[],
                           results={}, tv=tv, settings=settings)


@pytest.mark.anyio
async def test_no_claims_skips_search_and_pass2():
    llm = FakeLLM({ClaimExtraction: ClaimExtraction(claims=[])})
    tv = FakeTavily([Source(url="https://x")])
    res = await factcheck.run(_ctx(tv=tv, settings=FakeSettings()), llm)
    assert res.claims == []
    assert res.overall_confidence == "low"
    assert tv.queries == []                 # no search when no claims
    assert len(llm.calls) == 1              # only the extraction pass ran


@pytest.mark.anyio
async def test_two_pass_attaches_real_sources():
    sources = [Source(title="VnExpress", url="https://vn/1", snippet="won")]
    llm = FakeLLM({
        ClaimExtraction: ClaimExtraction(claims=["AURORA won IEM Cologne 2026"]),
        VerificationResult: VerificationResult(
            verdicts=[ClaimVerdict(label="supported", confidence="high", evidence="đúng")],
            overall_confidence="high"),
    })
    tv = FakeTavily(sources)
    res = await factcheck.run(_ctx(tv=tv, settings=FakeSettings()), llm)
    assert tv.queries == ["AURORA won IEM Cologne 2026"]
    assert len(res.claims) == 1
    c = res.claims[0]
    assert c.label == "supported" and c.confidence == "high" and c.evidence == "đúng"
    assert c.sources == sources             # real Source objects attached by the step
    assert res.overall_confidence == "high"


@pytest.mark.anyio
async def test_claim_without_sources_forced_unverifiable():
    llm = FakeLLM({
        ClaimExtraction: ClaimExtraction(claims=["unbacked claim"]),
        # LLM wrongly says supported, but there are no sources -> must be overridden
        VerificationResult: VerificationResult(
            verdicts=[ClaimVerdict(label="supported", confidence="high", evidence="x")],
            overall_confidence="low"),
    })
    tv = FakeTavily([])                      # search yields nothing
    res = await factcheck.run(_ctx(tv=tv, settings=FakeSettings()), llm)
    assert res.claims[0].label == "unverifiable"
    assert res.claims[0].sources == []


@pytest.mark.anyio
async def test_claims_beyond_cap_are_unverifiable_and_unsearched():
    class Settings3:
        factcheck_max_claims = 2
    claims = ["c1", "c2", "c3", "c4"]
    llm = FakeLLM({
        ClaimExtraction: ClaimExtraction(claims=claims),
        VerificationResult: VerificationResult(
            verdicts=[ClaimVerdict(label="supported", confidence="high", evidence="e"),
                      ClaimVerdict(label="disputed", confidence="medium", evidence="e2")],
            overall_confidence="medium"),
    })
    tv = FakeTavily([Source(url="https://u")])
    res = await factcheck.run(_ctx(tv=tv, settings=Settings3()), llm)
    assert tv.queries == ["c1", "c2"]        # only top 2 searched
    labels = [c.label for c in res.claims]
    assert labels == ["supported", "disputed", "unverifiable", "unverifiable"]


@pytest.mark.anyio
async def test_extraction_prompt_includes_domain():
    llm = FakeLLM({ClaimExtraction: ClaimExtraction(claims=[])})
    await factcheck.run(_ctx(tv=FakeTavily([]), settings=FakeSettings()), llm)
    extract_system = llm.calls[0][1]
    assert DEFAULT_PROFILE.domain_hint in extract_system
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factcheck.py -v`
Expected: FAIL — current `factcheck.run` calls `complete_json` once with `FactCheckResult` and uses `cross_reference`; the new tests reference `ClaimExtraction`/`VerificationResult` flow.

- [ ] **Step 3: Rewrite the step**

Replace the entire contents of `app/steps/factcheck.py` with:

```python
from app.schemas import FactCheckResult, Claim, ClaimExtraction, VerificationResult
from app.steps.base import AnalysisContext, register

_EXTRACT_SYSTEM = (
    "Bạn là trợ lý kiểm chứng cho lĩnh vực {domain}. Trích các tuyên bố CÓ THỂ kiểm chứng "
    "(dữ kiện khách quan) trong bài đăng; bỏ qua ý kiến và cảm xúc. "
    'Trả về JSON dạng {{"claims": ["tuyên bố 1", "tuyên bố 2"]}}.'
)
_VERIFY_SYSTEM = (
    "Bạn là trợ lý kiểm chứng cho lĩnh vực {domain}. Với mỗi tuyên bố kèm các nguồn web, "
    "gán nhãn supported/disputed/unverifiable và giải thích ngắn gọn bằng tiếng Việt trong "
    "trường evidence. Nếu không có nguồn hỗ trợ, dùng unverifiable. "
    'Trả về JSON có mảng "verdicts" THEO ĐÚNG THỨ TỰ tuyên bố (mỗi phần tử gồm label, '
    'confidence, evidence) và "overall_confidence".'
)


def _render_verify(checked: list) -> str:
    blocks = []
    for i, (claim, sources) in enumerate(checked, 1):
        refs = "\n".join(f"  - {s.title}: {s.snippet} ({s.url})" for s in sources)
        blocks.append(f"[{i}] TUYÊN BỐ: {claim}\nNGUỒN:\n{refs or '  (không có nguồn)'}")
    return "\n\n".join(blocks)


@register("factcheck")
async def run(ctx: AnalysisContext, llm) -> FactCheckResult:
    extraction = await llm.complete_json(
        system=_EXTRACT_SYSTEM.format(domain=ctx.profile.domain_hint),
        user=ctx.request.post.text,
        schema=ClaimExtraction,
    )
    claims = [c for c in extraction.claims if c and c.strip()]
    if not claims:
        return FactCheckResult(claims=[], overall_confidence="low")

    max_claims = ctx.settings.factcheck_max_claims if ctx.settings else 5
    to_check, overflow = claims[:max_claims], claims[max_claims:]

    checked = []
    for claim in to_check:
        sources = await ctx.tv.search(claim) if ctx.tv is not None else []
        checked.append((claim, sources))

    verification = await llm.complete_json(
        system=_VERIFY_SYSTEM.format(domain=ctx.profile.domain_hint),
        user=_render_verify(checked),
        schema=VerificationResult,
    )
    verdicts = verification.verdicts

    out_claims = []
    for i, (text, sources) in enumerate(checked):
        v = verdicts[i] if i < len(verdicts) else None
        # A claim with no web sources cannot be confirmed: force unverifiable.
        label = (v.label if v else "unverifiable") if sources else "unverifiable"
        out_claims.append(Claim(
            text=text,
            label=label,
            confidence=v.confidence if v else "low",
            evidence=v.evidence if v else "",
            sources=sources,
        ))
    for text in overflow:
        out_claims.append(Claim(text=text, label="unverifiable", confidence="low"))

    return FactCheckResult(claims=out_claims,
                           overall_confidence=verification.overall_confidence)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factcheck.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/steps/factcheck.py tests/test_factcheck.py
git commit -m "feat: two-pass Tavily-grounded factcheck step"
```

---

## Task 6: Report — render claim sources

**Files:**
- Modify: `app/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py` (and add `Source` to the existing import from `app.schemas`):

```python
def test_report_renders_claim_sources():
    from app.schemas import Source
    results = {
        "factcheck": FactCheckResult(
            claims=[Claim(text="AURORA won", label="supported", confidence="high",
                          evidence="xác nhận bởi 2 nguồn",
                          sources=[Source(title="VnExpress", url="https://vn/1",
                                          snippet="won"),
                                   Source(title="Reuters", url="https://r/2",
                                          snippet="confirmed")])],
            overall_confidence="high"),
    }
    text = format_report(_req(), results, DEFAULT_PROFILE)
    assert "https://vn/1" in text
    assert "VnExpress" in text
    assert len(text) <= 4096
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py -v`
Expected: FAIL — `assert 'https://vn/1' in text` (sources not rendered yet)

- [ ] **Step 3: Update the renderer**

In `app/report.py`, replace the `_factcheck` function with:

```python
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
        for i, s in enumerate(c.sources[:3], 1):
            lines.append(f"  ↳ [{i}] {s.title or s.url} — {s.url}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/report.py tests/test_report.py
git commit -m "feat: render cited sources under each factcheck claim"
```

---

## Task 7: Wire Tavily client + settings through the pipeline

**Files:**
- Modify: `app/pipeline.py`
- Modify: `app/main.py`
- Test: `tests/test_pipeline.py` (add one test; existing tests must still pass)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py`:

```python
@pytest.mark.anyio
async def test_run_job_threads_tv_and_settings_into_context(monkeypatch):
    seen = {}

    async def fake_deliver(payload, callback, **kw):
        seen["payload"] = payload

    async def spy_step(ctx, llm):
        seen["tv"] = ctx.tv
        seen["settings"] = ctx.settings
        from app.schemas import FactCheckResult
        return FactCheckResult()

    monkeypatch.setattr(pipeline, "deliver", fake_deliver)
    pipeline.STEP_REGISTRY["factcheck"] = spy_step  # override for this test

    req = AnalyzeRequest.model_validate(SAMPLE)
    await pipeline.run_job(req, sc=FakeSC(), llm=FakeLLM(), tv="TV", settings="SET")
    assert seen["tv"] == "TV"
    assert seen["settings"] == "SET"
```

> Note: this test mutates `STEP_REGISTRY`; it runs last alphabetically is not guaranteed, but the override returns a valid `FactCheckResult`, so the other pipeline tests that re-import the real step are unaffected within a normal run. If isolation is needed, save/restore `STEP_REGISTRY["factcheck"]` around the test.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `run_job() got an unexpected keyword argument 'tv'`

- [ ] **Step 3: Update `run_job`**

In `app/pipeline.py`, change the `run_job` signature and the context construction:

```python
async def run_job(req: AnalyzeRequest, *, sc, llm, tv=None, settings=None) -> None:
    profile = resolve_profile(req.mode.id)
    comments = await _gather_comments(sc, req, profile)
    ctx = AnalysisContext(request=req, profile=profile, comments=comments, results={},
                          sc=sc, tv=tv, settings=settings)
```

(Leave the rest of `run_job` unchanged.)

- [ ] **Step 4: Update `main.py` to construct and pass the client**

In `app/main.py`, add the import near the other client imports:

```python
from app.tavily import TavilyClient
```

Then in the `job()` coroutine, construct the client and pass it through:

```python
    async def job():
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.request_timeout) as http:
            sc = SocialCrawlClient(settings, http=http)
            llm = LLMClient(settings, http=http)
            tv = TavilyClient(settings, http=http)
            await run_job(req, sc=sc, llm=llm, tv=tv, settings=settings)
```

- [ ] **Step 5: Run the full pipeline + main suites to verify pass**

Run: `pytest tests/test_pipeline.py tests/test_main.py -v`
Expected: PASS (existing tests still green; new threading test passes)

- [ ] **Step 6: Commit**

```bash
git add app/pipeline.py app/main.py tests/test_pipeline.py
git commit -m "feat: wire TavilyClient and settings into the pipeline context"
```

---

## Task 8: Sort comments by likes before truncating

**Files:**
- Modify: `app/socialcrawl.py`
- Test: `tests/test_socialcrawl.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_socialcrawl.py`:

```python
@pytest.mark.anyio
async def test_fetch_comments_sorted_by_likes_desc():
    def handler(req):
        return httpx.Response(200, json={"success": True, "data": {"items": [
            {"id": "a", "text": "low", "author": {"username": "u"}, "likes": 1},
            {"id": "b", "text": "high", "author": {"username": "u"}, "likes": 99},
            {"id": "c", "text": "mid", "author": {"username": "u"}, "likes": 50},
        ]}})
    out = await _client(handler).fetch_comments("tiktok", "p1", "https://t/p1", limit=10)
    assert [c.text for c in out] == ["high", "mid", "low"]


@pytest.mark.anyio
async def test_fetch_comments_sort_then_truncate():
    def handler(req):
        return httpx.Response(200, json={"success": True, "data": {"items": [
            {"id": "a", "text": "low", "likes": 1},
            {"id": "b", "text": "high", "likes": 99},
        ]}})
    out = await _client(handler).fetch_comments("tiktok", "p1", "u", limit=1)
    assert [c.text for c in out] == ["high"]   # top-liked survives truncation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_socialcrawl.py -v`
Expected: FAIL — current order is raw API order `["low", "high", "mid"]`, and truncation keeps `"low"`.

- [ ] **Step 3: Sort before truncating**

In `app/socialcrawl.py`, in `fetch_comments`, replace the final return line:

```python
        items = (env.get("data") or {}).get("items") or []
        return [_normalize(i) for i in items][:limit]
```

with:

```python
        items = (env.get("data") or {}).get("items") or []
        comments = sorted((_normalize(i) for i in items),
                          key=lambda c: c.likes, reverse=True)
        return comments[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_socialcrawl.py -v`
Expected: PASS — note `test_fetch_comments_normalizes` still passes because its items are already in likes-desc order (4, then 0).

- [ ] **Step 5: Commit**

```bash
git add app/socialcrawl.py tests/test_socialcrawl.py
git commit -m "fix: sort comments by likes before truncating sample"
```

---

## Task 9: Full suite + deploy

**Files:** none (operational)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest`
Expected: all tests PASS. If any pre-existing test fails, fix before deploying.

- [ ] **Step 2: Confirm the Tavily API key with the user**

Ask the user for the `TAVILY_API_KEY` value to inject (never paste it into the repo or a committed file). The other env vars from prior deploys are:
- `SOCIALCRAWL_API_KEY=sc_024kr5lPcbgR3IvM5GHUmnlfV2ZqwZ8k3lGokHJuAyk`
- `LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`
- `LLM_API_KEY=vn-eu7_niOdmwurfQ9_RaUj_iCO9t-9H59885fdf3e5254d2a97f02bbb6715a4e2Hh3-AXJW2Wipy6KSLw-47t5KTAOZPrU`

- [ ] **Step 3: Rebuild, push, and update the runtime**

Build + push via the CLI and update the existing runtime (`runtime-7dab68fc-c898-4bb3-b086-75932f37fc46`):

```bash
GREENNODE_CLIENT_ID=7882531e-c542-4b03-8681-894c6a95064e \
GREENNODE_CLIENT_SECRET=285e4a36-56bb-4f5c-8073-5f2e4ca5e7e1 \
GREENNODE_REGISTRY_URL=vcr.vngcloud.vn \
GREENNODE_REGISTRY_USERNAME=111480-gui111735 \
GREENNODE_REGISTRY_PASSWORD=<registry-password> \
greennode deploy update "runtime-7dab68fc-c898-4bb3-b086-75932f37fc46" \
  --image-name "111480-abp111735/social-analyze-agent" --tag "latest" \
  --flavor-id "runtime-s2-general-2x4" \
  --image-auth-enabled --image-username "111480-gui111735" --image-password "<registry-password>"
```

- [ ] **Step 4: Patch the env to add `TAVILY_API_KEY`**

Use the `runtime.sh update --from-cr` helper with a temp env file containing all four env vars (`SOCIALCRAWL_API_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, `TAVILY_API_KEY`), then delete the temp file. (Same procedure used for the earlier `LLM_*` patches.)

- [ ] **Step 5: Verify health**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "https://endpoint-e8166de8-cdcd-43f7-ab9d-8fcbefd986f5.agentbase-runtime.aiplatform.vngcloud.vn/health"
```

Expected: `200`.

- [ ] **Step 6: Commit any remaining docs**

```bash
git add -A && git commit -m "chore: tavily fact-check deployment" || true
```

---

## Self-Review Notes

- **Spec coverage:** two-pass flow (T5), `Source`+`Claim.sources` (T2), `TavilyClient` (T3), config knobs (T1), context wiring (T4/T7), report sources (T6), drop `cross_reference` from factcheck (T5 — no longer imported/called), degradation to `unverifiable` (T3 best-effort + T5 forced-unverifiable), comment sort fix (T8), deployment + env var (T9). Threads-no-comments remains a documented known limitation (not in scope).
- **Type consistency:** `search() -> list[Source]`; `ClaimExtraction.claims: list[str]`; `VerificationResult.verdicts: list[ClaimVerdict]`; `AnalysisContext.tv/settings`; `run_job(..., tv=None, settings=None)`. Names match across tasks.
- **Refinement flagged:** deterministic source attachment instead of LLM echo (header note).
