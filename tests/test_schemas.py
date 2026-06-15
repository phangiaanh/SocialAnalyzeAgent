from app.schemas import AnalyzeRequest, CallbackPayload

SAMPLE = {
    "job_id": "j1",
    "mode": {"id": "esports", "label": "Esports", "icon": "🎯"},
    "topic": {"id": "esports", "label": "Esports", "icon": "🎯"},
    "tick_id": "1781489278",
    "post": {
        "platform": "tiktok", "post_id": "p1", "url": "https://t/p1",
        "text": "hello", "author": "@a", "language": "en",
        "likes": 10, "views": 100, "comments": 5, "shares": 2,
        "score": 0.04, "age_hours": 1.5,
    },
    "delivery": {"chat_id": 717110884, "message_id": 1234},
    "callback": {"url": "https://oc.example", "token": "tok"},
}


def test_parse_analyze_request():
    req = AnalyzeRequest.model_validate(SAMPLE)
    assert req.post.platform == "tiktok"
    assert req.delivery.chat_id == 717110884
    assert req.mode.label == "Esports"


def test_callback_payload_roundtrip():
    p = CallbackPayload(job_id="j1", status="ok", report_text="hi",
                        delivery={"chat_id": 1, "message_id": 2})
    assert p.model_dump()["status"] == "ok"


def test_claim_has_sources_default_empty():
    from app.schemas import Claim, Source
    c = Claim(text="x", label="supported", confidence="high")
    assert c.sources == []
    c2 = Claim(text="y", label="disputed", confidence="low",
               sources=[Source(title="T", url="https://u", snippet="s")])
    assert c2.sources[0].url == "https://u"


def test_two_pass_models():
    from app.schemas import ClaimExtraction, ClaimVerdict, VerificationResult
    assert ClaimExtraction().claims == []
    assert ClaimExtraction(claims=["a", "b"]).claims == ["a", "b"]
    v = VerificationResult(verdicts=[ClaimVerdict(label="supported",
                                                  confidence="high", evidence="e")],
                           overall_confidence="high")
    assert v.verdicts[0].label == "supported"
    assert v.overall_confidence == "high"
