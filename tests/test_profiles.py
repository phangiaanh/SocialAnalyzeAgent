from app.profiles import AnalysisProfile, DEFAULT_PROFILE, resolve_profile, PROFILES


def test_unknown_mode_uses_default():
    p = resolve_profile("does-not-exist")
    assert p is DEFAULT_PROFILE
    assert p.steps == ["factcheck", "attitude", "predict"]
    assert p.language == "vi"


def test_known_mode_uses_its_profile():
    PROFILES["finance"] = AnalysisProfile(domain_hint="tài chính",
                                          comment_sample_size=120)
    p = resolve_profile("finance")
    assert p.domain_hint == "tài chính"
    assert p.comment_sample_size == 120
    # still defaults the rest
    assert p.steps == ["factcheck", "attitude", "predict"]
