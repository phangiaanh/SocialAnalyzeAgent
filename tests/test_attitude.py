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
