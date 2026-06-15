from app.schemas import (AnalyzeRequest, FactCheckResult, Claim, AttitudeResult, Theme,
                         Prediction)
from app.report import format_report
from app.profiles import DEFAULT_PROFILE
from tests.test_schemas import SAMPLE


def _req():
    return AnalyzeRequest.model_validate(SAMPLE)


def test_report_has_all_sections_and_fits():
    results = {
        "factcheck": FactCheckResult(
            claims=[Claim(text="AURORA won", label="disputed", confidence="medium",
                          evidence="3 bài đồng tình")], overall_confidence="medium"),
        "attitude": AttitudeResult(sampled=212, positive_pct=64, neutral_pct=21,
                                   negative_pct=15, themes=[Theme(name="hype", count=88)],
                                   quotes=["insane clutch"]),
        "predict": Prediction(direction="up", text="tiếp tục trending", risk="tranh cãi",
                              momentum="rising"),
    }
    text = format_report(_req(), results, DEFAULT_PROFILE)
    assert "KIỂM CHỨNG" in text
    assert "THÁI ĐỘ BÌNH LUẬN" in text
    assert "DỰ ĐOÁN PHẢN ỨNG" in text
    assert "64%" in text
    assert len(text) <= 4096


def test_report_degrades_missing_sections():
    text = format_report(_req(), {}, DEFAULT_PROFILE)
    assert "không thể phân tích" in text.lower()
    assert len(text) <= 4096


def test_report_renders_claim_sources():
    from app.schemas import Source
    results = {
        "factcheck": FactCheckResult(
            claims=[Claim(text="AURORA won", label="supported", confidence="high",
                          evidence="xác nhận bởi 2 nguồn",
                          sources=[Source(title="VnExpress", url="https://vn/1",
                                          snippet="won"),
                                   Source(title="Reuters", url="https://r/2",
                                          snippet="confirmed")])],
            overall_confidence="high"),
    }
    text = format_report(_req(), results, DEFAULT_PROFILE)
    assert "https://vn/1" in text
    assert "VnExpress" in text
    assert len(text) <= 4096
