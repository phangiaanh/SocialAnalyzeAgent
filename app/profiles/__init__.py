from pydantic import BaseModel, Field


class AnalysisProfile(BaseModel):
    domain_hint: str = "chủ đề xã hội"
    comment_sample_size: int = 200
    steps: list[str] = Field(default_factory=lambda: ["factcheck", "attitude", "predict"])
    language: str = "vi"
    prompt_overrides: dict[str, str] = Field(default_factory=dict)


DEFAULT_PROFILE = AnalysisProfile()

# mode_id -> profile. New modes work with zero entries (fall back to DEFAULT_PROFILE).
PROFILES: dict[str, AnalysisProfile] = {
    "esports": AnalysisProfile(domain_hint="esports/gaming"),
}


def resolve_profile(mode_id: str) -> AnalysisProfile:
    return PROFILES.get(mode_id, DEFAULT_PROFILE)
