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
