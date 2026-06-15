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
