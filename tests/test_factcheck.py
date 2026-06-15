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
