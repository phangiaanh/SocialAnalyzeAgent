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
