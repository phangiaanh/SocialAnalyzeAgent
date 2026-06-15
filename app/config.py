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

    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "basic"
    tavily_max_results: int = 5
    factcheck_max_claims: int = 5

    request_timeout: float = 15.0


def get_settings() -> Settings:
    return Settings()
