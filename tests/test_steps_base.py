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


def test_context_holds_tv_and_settings():
    ctx = AnalysisContext(request=None, profile=None, comments=[], results={},
                          tv="TVCLIENT", settings="SETTINGS")
    assert ctx.tv == "TVCLIENT"
    assert ctx.settings == "SETTINGS"


def test_context_tv_and_settings_default_none():
    ctx = AnalysisContext(request=None, profile=None, comments=[], results={})
    assert ctx.tv is None
    assert ctx.settings is None
