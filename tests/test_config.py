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


def test_tavily_defaults(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_BASE_URL", raising=False)
    monkeypatch.delenv("TAVILY_SEARCH_DEPTH", raising=False)
    monkeypatch.delenv("TAVILY_MAX_RESULTS", raising=False)
    monkeypatch.delenv("FACTCHECK_MAX_CLAIMS", raising=False)
    s = Settings()
    assert s.tavily_api_key == ""
    assert s.tavily_base_url == "https://api.tavily.com"
    assert s.tavily_search_depth == "basic"
    assert s.tavily_max_results == 5
    assert s.factcheck_max_claims == 5


def test_tavily_env_override(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-123")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "10")
    monkeypatch.setenv("FACTCHECK_MAX_CLAIMS", "3")
    s = Settings()
    assert s.tavily_api_key == "tv-123"
    assert s.tavily_max_results == 10
    assert s.factcheck_max_claims == 3
