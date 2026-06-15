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
